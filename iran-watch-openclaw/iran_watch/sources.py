from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from iran_watch.utils import load_yaml


class Source(BaseModel):
    id: str
    name: str
    type: Literal["rss", "gdelt"]
    enabled: bool = True
    optional: bool = False
    tier: Literal["A", "B", "C"] = "C"
    domain: str
    url: str | None = None
    query: str | None = None
    language: str | None = None
    max_records: int = Field(default=100, ge=1, le=500)

    @model_validator(mode="after")
    def check_fields(self) -> "Source":
        if self.type == "rss" and not self.url:
            raise ValueError(f"rss source {self.id} requires url")
        if self.type == "gdelt" and not self.query:
            raise ValueError(f"gdelt source {self.id} requires query")
        return self


class SourcesConfig(BaseModel):
    sources: list[Source]


def load_sources_config(path: Path) -> SourcesConfig:
    return SourcesConfig.model_validate(load_yaml(path))


def source_map_by_id(sources: list[Source]) -> dict[str, Source]:
    return {s.id: s for s in sources}


def enabled_sources(sources: list[Source]) -> list[Source]:
    return [s for s in sources if s.enabled]
