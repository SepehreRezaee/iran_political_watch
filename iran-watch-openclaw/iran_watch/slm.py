from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from iran_watch.utils import clamp, serialize_error

logger = logging.getLogger(__name__)


SCENARIOS = ["S1", "S2", "S3", "S4"]
_AIRLLM_CACHE: dict[str, Any] = {}
_AIRLLM_LOCK = threading.Lock()


@dataclass(frozen=True)
class SLMResult:
    enabled: bool
    used: bool
    provider: str
    model: str
    scenario_probs: dict[str, float] | None
    narrative: list[str]
    rationale: str | None
    error: dict[str, str] | None


def _normalize_probs(probs: dict[str, float]) -> dict[str, float]:
    out = {k: max(float(probs.get(k, 0.0)), 0.0) for k in SCENARIOS}
    total = sum(out.values())
    if total <= 0:
        return {k: 0.25 for k in SCENARIOS}
    return {k: round(v / total, 8) for k, v in out.items()}


def blend_probs(base_probs: dict[str, float], slm_probs: dict[str, float], weight: float) -> dict[str, float]:
    w = clamp(float(weight), 0.0, 1.0)
    blended = {k: (1.0 - w) * base_probs[k] + w * slm_probs[k] for k in SCENARIOS}
    return _normalize_probs(blended)


def _extract_json_block(text: str) -> str:
    text = (text or "").strip()
    if not text:
        raise ValueError("empty response")
    if text.startswith("{") and text.endswith("}"):
        return text
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("response did not contain JSON object")
    return text[start : end + 1]


def _build_prompt(payload: dict[str, Any]) -> str:
    return (
        "You are a geopolitical risk reasoning model. Use only the provided evidence. "
        "Return strictly valid JSON with keys: scenario_probs, narrative, rationale. "
        "scenario_probs must include S1,S2,S3,S4 and sum to 1. "
        "narrative must be exactly 3 short paragraphs grounded in evidence. "
        "Do not include markdown.\n\n"
        f"INPUT_JSON:\n{json.dumps(payload, ensure_ascii=False)}\n"
    )


def _extract_generation_text(raw_text: str, prompt: str) -> str:
    text = (raw_text or "").strip()
    if text.startswith(prompt):
        return text[len(prompt) :].strip()
    return text


def _move_input_ids(input_ids: Any, device: str) -> Any:
    dev = (device or "auto").lower()
    if dev in {"", "auto"}:
        return input_ids
    if hasattr(input_ids, "to"):
        return input_ids.to(dev)
    if dev == "cuda" and hasattr(input_ids, "cuda"):
        return input_ids.cuda()
    return input_ids


def _load_airllm_model(config: dict[str, Any]) -> Any:
    try:
        from airllm import AutoModel  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise ImportError(
            "airllm provider selected but package is not available. Install optional deps from "
            "requirements-slm-airllm.txt"
        ) from exc

    model_id = str(config.get("model", "Qwen/Qwen3-30B-A3B-Thinking-2507-FP8"))
    cache_key = json.dumps(
        {
            "model": model_id,
            "compression": config.get("compression"),
            "layer_shards_saving_path": config.get("layer_shards_saving_path"),
            "prefetching": config.get("prefetching", True),
            "profiling_mode": config.get("profiling_mode", False),
            "delete_original": config.get("delete_original", False),
            "hf_token_env": config.get("hf_token_env", "HF_TOKEN"),
        },
        sort_keys=True,
    )

    with _AIRLLM_LOCK:
        if cache_key in _AIRLLM_CACHE:
            return _AIRLLM_CACHE[cache_key]

        kwargs: dict[str, Any] = {
            "profiling_mode": bool(config.get("profiling_mode", False)),
            "prefetching": bool(config.get("prefetching", True)),
            "delete_original": bool(config.get("delete_original", False)),
        }
        compression = config.get("compression")
        if compression in {"4bit", "8bit"}:
            kwargs["compression"] = compression
        layer_path = config.get("layer_shards_saving_path")
        if layer_path:
            kwargs["layer_shards_saving_path"] = str(layer_path)

        hf_token = config.get("hf_token")
        if not hf_token:
            env_key = str(config.get("hf_token_env", "HF_TOKEN"))
            hf_token = os.getenv(env_key)
        if hf_token:
            kwargs["hf_token"] = str(hf_token)

        model = AutoModel.from_pretrained(model_id, **kwargs)
        _AIRLLM_CACHE[cache_key] = model
        return model


def _call_airllm(config: dict[str, Any], prompt: str, temperature: float) -> dict[str, Any]:
    model = _load_airllm_model(config)
    tokenizer = model.tokenizer

    max_input_tokens = int(config.get("max_input_tokens", 8192))
    max_new_tokens = int(config.get("max_new_tokens", 1400))
    top_p = float(config.get("top_p", 0.95))
    do_sample = bool(config.get("do_sample", temperature > 0.0))
    device = str(config.get("input_device", "auto"))

    encoded = tokenizer(
        [prompt],
        return_tensors="pt",
        return_attention_mask=False,
        truncation=True,
        max_length=max_input_tokens,
        padding=False,
    )
    input_ids = _move_input_ids(encoded["input_ids"], device=device)

    generate_kwargs = {
        "max_new_tokens": max_new_tokens,
        "use_cache": True,
        "return_dict_in_generate": True,
        "do_sample": do_sample,
        "temperature": max(temperature, 1e-5) if do_sample else 1.0,
        "top_p": top_p if do_sample else 1.0,
    }
    generation_output = model.generate(input_ids, **generate_kwargs)
    sequences = generation_output.sequences
    text = tokenizer.decode(sequences[0], skip_special_tokens=True)
    generated = _extract_generation_text(text, prompt)
    return json.loads(_extract_json_block(generated))


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError, ValueError)),
    reraise=True,
)
def _call_ollama(
    endpoint: str,
    model: str,
    prompt: str,
    timeout_sec: float,
    temperature: float,
) -> dict[str, Any]:
    with httpx.Client(timeout=timeout_sec, follow_redirects=True) as client:
        resp = client.post(
            endpoint,
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": temperature},
            },
        )
        resp.raise_for_status()
        data = resp.json()

    raw = data.get("response")
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        raise ValueError("ollama response missing 'response' string")
    return json.loads(_extract_json_block(raw))


def _sanitize_narrative(value: Any) -> list[str]:
    if isinstance(value, list):
        out = [str(v).strip() for v in value if str(v).strip()]
    elif isinstance(value, str) and value.strip():
        out = [value.strip()]
    else:
        out = []
    return out[:3]


def run_slm_analysis(config: dict[str, Any], context_payload: dict[str, Any]) -> SLMResult:
    enabled = bool(config.get("enabled", False))
    provider = str(config.get("provider", "ollama"))
    model = str(config.get("model", "deepseek-r1:32b"))
    if not enabled:
        return SLMResult(
            enabled=False,
            used=False,
            provider=provider,
            model=model,
            scenario_probs=None,
            narrative=[],
            rationale=None,
            error=None,
        )

    prompt = _build_prompt(context_payload)
    endpoint = str(config.get("endpoint", "http://localhost:11434/api/generate"))
    timeout_sec = float(config.get("timeout_sec", 60))
    temperature = float(config.get("temperature", 0.0))

    try:
        if provider == "ollama":
            result = _call_ollama(
                endpoint=endpoint,
                model=model,
                prompt=prompt,
                timeout_sec=timeout_sec,
                temperature=temperature,
            )
        elif provider == "airllm":
            result = _call_airllm(config=config, prompt=prompt, temperature=temperature)
        else:
            raise ValueError(f"unsupported SLM provider: {provider}")
        probs_raw = result.get("scenario_probs", {})
        if not isinstance(probs_raw, dict):
            raise ValueError("scenario_probs missing or invalid")
        scenario_probs = _normalize_probs({k: float(v) for k, v in probs_raw.items()})
        narrative = _sanitize_narrative(result.get("narrative"))
        rationale = str(result.get("rationale", "")).strip() or None

        return SLMResult(
            enabled=True,
            used=True,
            provider=provider,
            model=model,
            scenario_probs=scenario_probs,
            narrative=narrative,
            rationale=rationale,
            error=None,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("slm_analysis_failed")
        return SLMResult(
            enabled=True,
            used=False,
            provider=provider,
            model=model,
            scenario_probs=None,
            narrative=[],
            rationale=None,
            error=serialize_error(exc),
        )
