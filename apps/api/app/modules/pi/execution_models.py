# ruff: noqa: E501
"""One row per controlled-execution run (Level 3): the sealed snapshot, see `execution_flow.to_json`.

The snapshot carries the HMAC-sealed scope and tasks, the execution records, the consumed approvals and
the hash-chained audit log; `head_hash` is the audit head kept outside the JSON as an anchor, so a
snapshot with entries dropped from the end fails to load. Read and written only when
`response_rules.brain.level3_exec` is on.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, Index, Integer, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import WorkspaceRow, workspace_args

STATUSES = ("proposed", "approved", "in_progress", "implemented", "failed")


class PiExecutionRun(WorkspaceRow):
    __tablename__ = "pi_execution_runs"
    __table_args__ = workspace_args(
        "pi_execution_runs",
        Index("ix_pi_execution_runs_customer", "tenant_id", "environment_id", "customer_id"),
        CheckConstraint(f"status IN ({', '.join(repr(v) for v in STATUSES)})", name="status"),
    )
    run_ref: Mapped[str] = mapped_column(String(40))
    customer_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    conversation_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="proposed", server_default="proposed")
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    head_hash: Mapped[str] = mapped_column(String(64), default="", server_default="")
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
