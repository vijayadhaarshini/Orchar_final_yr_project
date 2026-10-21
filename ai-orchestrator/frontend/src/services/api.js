import axios from "axios";

const API_BASE_URL = import.meta.env.VITE_BACKEND_URL || "http://localhost:8000";

const client = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
});

// ---- Projects ----

/** Create a new project. */
export async function createProject(payload) {
  const res = await client.post("/project", payload);
  return res.data;
}

/** List all projects. */
export async function listProjects() {
  const res = await client.get("/projects");
  return res.data;
}

/** Delete a project by ID. */
export async function deleteProject(projectId) {
  await client.delete(`/project/${projectId}`);
}

/** Set persona for a project. */
export async function setProjectPersona(projectId, persona) {
  const res = await client.post(`/project/${projectId}/persona`, { persona });
  return res.data;
}

// ---- Pipeline ----

/** Submit a feature/bug request. Returns { run_id, status } immediately. */
export async function submitFeature(projectId, payload) {
  const res = await client.post(`/project/${projectId}/feature`, payload);
  return res.data;
}

/** Poll the pipeline run status (progressive updates). */
export async function fetchPipelineStatus(projectId, runId) {
  const res = await client.get(`/project/${projectId}/pipeline/${runId}`);
  return res.data;
}

/** List all pipeline runs for a project (history). */
export async function listPipelineRuns(projectId) {
  const res = await client.get(`/project/${projectId}/pipeline`);
  return res.data;
}

/** Fetch a single pipeline run's full details. */
export async function fetchPipelineRun(projectId, runId) {
  const res = await client.get(`/project/${projectId}/pipeline/${runId}`);
  return res.data;
}

// ---- Executions ----

/** Agent executions for a project. Pass runId to get one run only. */
export async function fetchExecutions(projectId, runId) {
  const params = runId != null ? { run_id: runId } : undefined;
  const res = await client.get(`/project/${projectId}/executions`, { params });
  return res.data;
}

// ---- Tasks ----

/** List all tasks for a project. */
export async function listTasks(projectId) {
  const res = await client.get(`/project/${projectId}/tasks`);
  return res.data;
}

/** Update the status of a task. */
export async function updateTaskStatus(projectId, taskId, status) {
  const res = await client.patch(`/project/${projectId}/tasks/${taskId}`, { status });
  return res.data;
}

// ---- Analytics ----

/** Get analytics for a project. */
export async function fetchAnalytics(projectId) {
  const res = await client.get(`/project/${projectId}/analytics`);
  return res.data;
}

// ---- Memory ----

/** List ChromaDB memory entries for a project. */
export async function fetchMemory(projectId) {
  const res = await client.get(`/project/${projectId}/memory`);
  return res.data;
}

// ---- Checkpoint ----

/**
 * Respond to a human checkpoint in a pipeline run.
 * payload: { action: "approve"|"modify"|"reject", input?: string }
 */
export async function respondToCheckpoint(projectId, runId, payload) {
  const res = await client.post(
    `/project/${projectId}/pipeline/${runId}/checkpoint/respond`,
    payload
  );
  return res.data;
}

// ---- Team inputs ----

/** Submit a team member input for a specific pipeline stage. */
export async function submitTeamInput(projectId, runId, payload) {
  const res = await client.post(
    `/project/${projectId}/pipeline/${runId}/team-input`,
    payload
  );
  return res.data;
}

/** List team inputs for a pipeline run. */
export async function listTeamInputs(projectId, runId) {
  const res = await client.get(
    `/project/${projectId}/pipeline/${runId}/team-inputs`
  );
  return res.data;
}

/** Retrigger a specific pipeline stage. */
export async function retriggerStage(projectId, runId, stage) {
  const res = await client.post(
    `/project/${projectId}/pipeline/${runId}/retrigger/${stage}`
  );
  return res.data;
}

// ---- Health ----

/** Health check. */
export async function healthCheck() {
  const res = await client.get("/health");
  return res.data;
}

// ---- Evolved prompts (Level 5: structural self-modification) ----

/** Fetch per-agent evolved prompt instructions for a project. */
export async function fetchEvolvedPrompts(projectId) {
  const res = await client.get(`/project/${projectId}/evolved-prompts`);
  return res.data;
}

/** Fetch sub-agent spawn events for a specific pipeline run. */
export async function fetchSubAgentSpawns(runId) {
  const res = await client.get(`/run/${runId}/sub-agents`);
  return res.data;
}

// ---- Level 5 ----

/** Fetch aggregated Level 5 activity for a project (debate rounds, bus messages, dynamic roles, etc). */
export async function fetchLevel5Summary(projectId) {
  const res = await client.get(`/project/${projectId}/level5`);
  return res.data;
}

/** Fetch static + dynamic specialist roles for a project. */
export async function fetchDynamicRoles(projectId) {
  const res = await client.get(`/project/${projectId}/dynamic-roles`);
  return res.data;
}

/** Fetch P2P bus messages logged during a specific pipeline run. */
export async function fetchBusMessages(runId) {
  const res = await client.get(`/run/${runId}/bus-messages`);
  return res.data;
}
