from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utc_now() -> datetime:
    """The current time in UTC, with the timezone attached (the columns store timezones)."""
    return datetime.now(UTC)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    persona: Mapped[str] = mapped_column(String(50), nullable=False, default="intermediate")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    tasks: Mapped[list["Task"]] = relationship("Task", back_populates="project", cascade="all, delete-orphan")
    executions: Mapped[list["AgentExecution"]] = relationship(
        "AgentExecution", back_populates="project", cascade="all, delete-orphan"
    )
    conversation_logs: Mapped[list["ConversationLog"]] = relationship(
        "ConversationLog", back_populates="project", cascade="all, delete-orphan"
    )
    pipeline_runs: Mapped[list["PipelineRun"]] = relationship(
        "PipelineRun", back_populates="project", cascade="all, delete-orphan"
    )


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    project: Mapped[Project] = relationship("Project", back_populates="tasks")


class AgentExecution(Base):
    __tablename__ = "agent_executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    # Empty for executions saved before runs were linked to their executions.
    pipeline_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    input_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    execution_time: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    project: Mapped[Project] = relationship("Project", back_populates="executions")


class ConversationLog(Base):
    __tablename__ = "conversation_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    project: Mapped[Project] = relationship("Project", back_populates="conversation_logs")


class PipelineRun(Base):
    """Tracks the overall state of a feature/bug pipeline execution."""

    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    feature_description: Mapped[str] = mapped_column(Text, nullable=False)
    request_type: Mapped[str] = mapped_column(String(20), nullable=False, default="feature")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    planned_tasks: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=list)
    generated_code: Mapped[str | None] = mapped_column(Text, nullable=True, default="")
    test_code: Mapped[str | None] = mapped_column(Text, nullable=True, default="")
    test_result: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    execution_timeline: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=list)
    design_artifact: Mapped[str | None] = mapped_column(Text, nullable=True, default="")
    persona: Mapped[str] = mapped_column(String(50), nullable=False, default="intermediate")
    current_agent: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, default="")
    # Overseer-driven pipeline
    overseer_plan: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    checkpoint_stage: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    checkpoint_prompt: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    # First stage in overseer_plan["stages"] that has not finished yet.
    # Used to resume after a checkpoint, and by the UI to show progress.
    next_stage_index: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Project] = relationship("Project", back_populates="pipeline_runs")
    team_inputs: Mapped[list["TeamInput"]] = relationship(
        "TeamInput", back_populates="pipeline_run", cascade="all, delete-orphan"
    )


class TeamInput(Base):
    """Stores role-based inputs submitted independently by team members.

    Each team member (manager, architect, developer, tester) can submit
    feedback or modified content for their stage at any time. The orchestrator
    uses this input when re-triggering that specific stage.
    """

    __tablename__ = "team_inputs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    pipeline_run_id: Mapped[int] = mapped_column(
        ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False)   # manager|architect|developer|tester
    stage: Mapped[str] = mapped_column(String(50), nullable=False)  # planning|designing|developing|testing
    content: Mapped[str] = mapped_column(Text, nullable=False)       # the feedback / modified content
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")  # pending|applied
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    pipeline_run: Mapped[PipelineRun] = relationship("PipelineRun", back_populates="team_inputs")
