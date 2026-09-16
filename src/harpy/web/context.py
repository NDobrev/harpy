"""Trusted request identity. Never constructed from a browser body."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class RequestContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tenant_id: UUID
    actor_id: UUID
    role: Literal["administrator", "reviewer", "viewer"]
    correlation_id: UUID
    authenticated_subject: str
    authorization_version: int
