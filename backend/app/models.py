from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class KeyInfo(BaseModel):
    description: str
    source: str
    group: str


class AnalysisResponse(BaseModel):
    generated_at: str
    keys: Dict[str, Any] = Field(default_factory=dict)
    registry: Dict[str, KeyInfo] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)
    tables: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BootstrapTemplateResponse(BaseModel):
    generated_at: str
    records: List[Dict[str, Any]]
