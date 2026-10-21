from datetime import datetime
from typing import ClassVar, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProjectCreate(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None


class ProjectRead(BaseModel):
    id: int
    name: str
    description: Optional[str]
    persona: str = "intermediate"
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PersonaSet(BaseModel):
    persona: str = Field(..., pattern="^(simple|intermediate|expert)$")


class TaskRead(BaseModel):
    id: int
    project_id: int
    description: str
    status: str
    priority: str = "medium"
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskUpdate(BaseModel):
    status: str = Field(..., pattern="^(planned|in_progress|completed|cancelled)$")


class AgentExecutionRead(BaseModel):
    id: int
    project_id: int
    pipeline_run_id: Optional[int] = None
    agent_name: str
    input_payload: Optional[dict] = None
    output_payload: Optional[dict] = None
    status: str
    execution_time: float = 0.0
    tokens_used: int = 0
    error_message: Optional[str] = ""
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PlannerTaskItem(BaseModel):
    # LLMs often write "id": 1 instead of "id": "1". Accept both.
    model_config = ConfigDict(coerce_numbers_to_str=True)

    id: str
    description: str
    priority: str = "medium"

    @field_validator("priority", mode="before")
    @classmethod
    def normalise_priority(cls, value: object) -> str:
        """Turn "High" or "urgent" into one of low / medium / high."""
        text = str(value).strip().lower()
        return text if text in ("low", "medium", "high") else "medium"


class PlannerOutput(BaseModel):
    tasks: List[PlannerTaskItem]


class FeatureRequest(BaseModel):
    request_type: str = Field(default="feature", pattern="^(feature|bug)$")
    description: str
    persona: Optional[str] = "intermediate"


class TestResult(BaseModel):
    # The name starts with "Test", so pytest would try to collect it as a test class.
    __test__: ClassVar[bool] = False

    status: str
    coverage: float
    errors: str | None = None


class PipelineStartResponse(BaseModel):
    """Returned immediately when a feature request is submitted."""
    run_id: int
    status: str = "pending"


class OverseerPlan(BaseModel):
    """The pipeline execution plan produced by the Overseer agent."""
    stages: List[str]
    checkpoints: List[str]
    skip: List[str] = []
    reason: str


class CheckpointResponse(BaseModel):
    """Human response to a pipeline checkpoint."""
    action: str = Field(..., pattern="^(approve|modify|reject)$")
    # Optional human input / instructions injected into the next stage
    input: Optional[str] = None


class PipelineRunRead(BaseModel):
    """Current state of a pipeline run, polled by the frontend."""
    id: int
    project_id: int
    feature_description: str
    request_type: str
    status: str
    planned_tasks: Optional[List[dict]] = []
    generated_code: Optional[str] = ""
    test_code: Optional[str] = ""
    test_result: Optional[dict] = {}
    execution_timeline: Optional[List[dict]] = []
    design_artifact: Optional[str] = ""
    persona: Optional[str] = "intermediate"
    current_agent: str = ""
    error_message: Optional[str] = ""
    overseer_plan: Optional[dict] = None
    checkpoint_stage: Optional[str] = None
    checkpoint_prompt: Optional[str] = None
    next_stage_index: Optional[int] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class PipelineRunListItem(BaseModel):
    """Summary of a pipeline run for the history list."""
    id: int
    feature_description: str
    request_type: str
    status: str
    persona: Optional[str] = "intermediate"
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class AgentStat(BaseModel):
    agent_name: str
    total_runs: int
    successful: int
    failed: int
    avg_execution_time: float


class AnalyticsResponse(BaseModel):
    total_runs: int
    successful_runs: int
    failed_runs: int
    total_tasks: int
    avg_execution_time: float
    test_pass_rate: float
    agent_stats: List[AgentStat]


class MemoryEntry(BaseModel):
    id: str
    document: str
    metadata: dict


class DesignOutput(BaseModel):
    architecture: str
    components: List[str]
    api_contracts: str


# ---------------------------------------------------------------------------
# Team collaboration schemas
# ---------------------------------------------------------------------------

ROLE_STAGE_MAP = {
    "manager": "planning",
    "architect": "designing",
    "developer": "developing",
    "tester": "testing",
}


class TeamInputCreate(BaseModel):
    role: str = Field(..., pattern="^(manager|architect|developer|tester)$")
    content: str = Field(..., min_length=1)
    # stage is derived from role automatically


class TeamInputRead(BaseModel):
    id: int
    project_id: int
    pipeline_run_id: int
    role: str
    stage: str
    content: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RetriggerResponse(BaseModel):
    message: str
    stage: str
    role: str
