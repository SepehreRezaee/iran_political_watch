from iran_watch.slm import blend_probs, run_slm_analysis


def test_blend_probs_normalized() -> None:
    base = {"S1": 0.4, "S2": 0.3, "S3": 0.2, "S4": 0.1}
    slm = {"S1": 0.1, "S2": 0.1, "S3": 0.3, "S4": 0.5}
    out = blend_probs(base, slm, weight=0.2)
    assert abs(sum(out.values()) - 1.0) < 1e-8
    assert out["S1"] < base["S1"]
    assert out["S4"] > base["S4"]


def test_slm_disabled_fast_path() -> None:
    res = run_slm_analysis(
        {"enabled": False, "provider": "airllm", "model": "Qwen/Qwen3-30B-A3B-Thinking-2507-FP8"},
        {"indicators": {"I1": 5}},
    )
    assert res.enabled is False
    assert res.used is False
    assert res.scenario_probs is None
