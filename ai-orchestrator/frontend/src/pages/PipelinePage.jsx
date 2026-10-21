import { useCallback, useEffect, useState } from "react";
import CodeViewer from "../components/CodeViewer.jsx";
import ExecutionTimeline from "../components/ExecutionTimeline.jsx";
import FeatureForm from "../components/FeatureForm.jsx";
import TestResultPanel from "../components/TestResultPanel.jsx";
import { useProject } from "../context/ProjectContext.jsx";
import {
  fetchExecutions,
  fetchPipelineStatus,
  listPipelineRuns,
  respondToCheckpoint,
  submitFeature,
} from "../services/api.js";

const POLL_INTERVAL_MS = 2500;
const FINISHED_STATUSES = new Set(["completed", "failed"]);

// All possible pipeline stages in display order
const ALL_STAGES = ["planner", "designer", "developer", "critic", "tester", "self_evolve"];

const STAGE_LABELS = {
  planner: "Planner",
  designer: "Designer",
  developer: "Developer",
  critic: "Critic",
  tester: "Tester",
  self_evolve: "Self-Evolve",
};

const STAGE_ICONS = {
  planner: "📋",
  designer: "🏗️",
  developer: "💻",
  critic: "🔍",
  tester: "🧪",
  self_evolve: "🧠",
};

const STAGE_DESC = {
  planner: "Breaks request into tasks",
  designer: "Designs architecture & APIs",
  developer: "Writes the code",
  critic: "Reviews & improves code",
  tester: "Runs tests & checks coverage",
  self_evolve: "Stores learned patterns",
};

const STATUS_COLOR = {
  pending: "text-slate-500 border-slate-700 bg-slate-900",
  running: "text-sky-300 border-sky-500/50 bg-sky-950/30",
  completed: "text-emerald-300 border-emerald-500/40 bg-emerald-950/20",
  failed: "text-rose-300 border-rose-500/40 bg-rose-950/20",
  skipped: "text-slate-500 border-slate-700/50 bg-slate-900/40",
};

// Status of the stage at `position` in the plan.
// The backend keeps next_stage_index = the first stage that has not finished,
// so everything before it is done and everything after it has not started.
function stageStatusAt(run, position, isRunning) {
  const next = run?.next_stage_index ?? 0;
  if (position > next) return "pending";
  if (position < next) {
    // A finished stage may have been skipped (for example, no code to test yet).
    // We can only tell when the stage appears once in the plan.
    const stage = run.overseer_plan.stages[position];
    const appearsOnce = run.overseer_plan.stages.filter((s) => s === stage).length === 1;
    const skipped = run.execution_timeline?.some((e) => e.agent === stage && e.status === "skipped");
    return appearsOnce && skipped ? "skipped" : "completed";
  }
  if (run?.status === "failed") return "failed";
  return isRunning ? "running" : "pending";
}

const STAGE_STATUS_TEXT = {
  completed: "text-emerald-400",
  running: "text-sky-400",
  failed: "text-rose-400",
};

// ---- Overseer Plan Card ----
function OverseerPlanCard({ plan }) {
  if (!plan) return null;
  return (
    <div className="rounded-xl border border-violet-600/40 bg-violet-950/20 p-4">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-lg">🤖</span>
        <h3 className="text-sm font-semibold text-violet-200">Overseer Decision</h3>
      </div>
      <p className="text-xs text-violet-300 mb-3 leading-relaxed">{plan.reason}</p>
      <div className="flex flex-wrap gap-1.5">
        {plan.stages?.map((s, i) => (
          <span key={s + i} className="flex items-center gap-1 rounded-full bg-violet-900/40 border border-violet-700/40 px-2.5 py-0.5 text-[11px] text-violet-300">
            <span>{STAGE_ICONS[s] || "▸"}</span>
            {STAGE_LABELS[s] || s}
            {plan.checkpoints?.includes(`after_${s}`) && (
              <span className="ml-0.5 text-amber-400" title="Human checkpoint">⏸</span>
            )}
          </span>
        ))}
      </div>
      {plan.skip?.length > 0 && (
        <p className="text-[10px] text-slate-500 mt-2">
          Skipped: {plan.skip.join(", ")}
        </p>
      )}
    </div>
  );
}

// ---- Stage Step Card ----
function StageStepCard({ name, stageStatus }) {
  const isSkipped = stageStatus === "skipped";
  const isRunning = stageStatus === "running";
  return (
    <div className={`rounded-lg border px-3 py-2.5 flex items-center gap-3 transition-all
      ${STATUS_COLOR[stageStatus] || STATUS_COLOR.pending} ${isRunning ? "ring-2 ring-sky-500/60" : ""}`}>
      <span className="text-lg flex-shrink-0">{isSkipped ? "⊘" : STAGE_ICONS[name]}</span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-medium truncate">{STAGE_LABELS[name]}</span>
          <span className={`text-[10px] font-semibold uppercase tracking-wide flex-shrink-0
            ${STAGE_STATUS_TEXT[stageStatus] || "text-slate-600"}`}>
            {stageStatus}
          </span>
        </div>
        <p className="text-[11px] text-slate-500 mt-0.5 truncate">{STAGE_DESC[name]}</p>
      </div>
      {isRunning && <div className="h-2 w-2 rounded-full bg-sky-400 animate-pulse flex-shrink-0" />}
    </div>
  );
}

// ---- Human Checkpoint Card ----
function CheckpointCard({ run, onRespond, isResponding }) {
  const [action, setAction] = useState("approve");
  const [inputText, setInputText] = useState("");

  if (!run || run.status !== "awaiting_human") return null;

  const handleSubmit = () => {
    onRespond({
      action,
      input: action === "modify" ? inputText.trim() : undefined,
    });
  };

  const stageName = run.checkpoint_stage?.replace("after_", "") || "stage";

  return (
    <div className="rounded-xl border-2 border-amber-500/50 bg-amber-950/20 p-4 space-y-3">
      <div className="flex items-start gap-2">
        <span className="text-xl mt-0.5">⏸</span>
        <div>
          <h3 className="text-sm font-semibold text-amber-200">Human Review Required</h3>
          <p className="text-xs text-amber-400/80 mt-0.5">
            After <span className="font-medium capitalize">{STAGE_LABELS[stageName] || stageName}</span>
          </p>
        </div>
      </div>

      {run.checkpoint_prompt && (
        <p className="text-xs text-slate-200 leading-relaxed bg-slate-800/60 rounded-md p-3 whitespace-pre-wrap">
          {run.checkpoint_prompt}
        </p>
      )}

      <div className="space-y-2">
        <div className="flex gap-2">
          {[
            { id: "approve", label: "✓ Approve", desc: "Continue to next stage" },
            { id: "modify", label: "✏ Modify", desc: "Inject guidance" },
            { id: "reject", label: "✗ Reject", desc: "Abort pipeline" },
          ].map(({ id, label, desc }) => (
            <button
              key={id}
              type="button"
              onClick={() => setAction(id)}
              className={`flex-1 rounded-md px-2 py-1.5 text-xs font-medium transition-colors
                ${action === id
                  ? id === "approve" ? "bg-emerald-500 text-slate-950"
                    : id === "modify" ? "bg-amber-500 text-slate-950"
                    : "bg-rose-500 text-white"
                  : "border border-slate-600 bg-slate-800 text-slate-300 hover:border-slate-500"
                }`}
            >
              <div>{label}</div>
              <div className="text-[10px] opacity-70">{desc}</div>
            </button>
          ))}
        </div>

        {action === "modify" && (
          <textarea
            className="w-full rounded-md border border-amber-600/40 bg-slate-800 px-3 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-amber-500"
            rows={3}
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            placeholder="Provide instructions for the next stage (e.g. add error handling, change the architecture to…)"
          />
        )}
      </div>

      <button
        onClick={handleSubmit}
        disabled={isResponding || (action === "modify" && !inputText.trim())}
        className="w-full rounded-md bg-amber-500 py-2 text-sm font-semibold text-slate-950 hover:bg-amber-400 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        {isResponding ? "Resuming…" : "Submit Response"}
      </button>
    </div>
  );
}

// ---- Main Page ----
export default function PipelinePage() {
  const { activeProject, persona } = useProject();
  const [executions, setExecutions] = useState([]);
  const [pipelineRun, setPipelineRun] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isResponding, setIsResponding] = useState(false);
  const [error, setError] = useState(null);
  const [runId, setRunId] = useState(null);

  // Work out the page state from the run's status instead of keeping a
  // separate "is running" flag. Two sources of truth can disagree, and when
  // they did, polling stopped and the page froze after a checkpoint.
  const status = pipelineRun?.status;
  const isFinished = FINISHED_STATUSES.has(status);
  const isAwaiting = status === "awaiting_human";
  const isRunning = isSubmitting || (runId !== null && !isFinished && !isAwaiting);

  // When the page opens (or the project changes), pick up a run that is
  // still going, so leaving the page and coming back does not lose it.
  const projectId = activeProject?.id;
  useEffect(() => {
    setRunId(null);
    setPipelineRun(null);
    setExecutions([]);
    if (!projectId) return;
    let cancelled = false;
    listPipelineRuns(projectId)
      .then((runs) => {
        const latest = runs[0]; // newest first
        if (!cancelled && latest && !FINISHED_STATUSES.has(latest.status)) setRunId(latest.id);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  // Poll until the run finishes. We keep polling while it waits for a human
  // too, so the page notices if the review is answered from another tab.
  useEffect(() => {
    if (!projectId || runId === null || isFinished) return;
    const poll = async () => {
      try {
        const [pipeline, execs] = await Promise.all([
          fetchPipelineStatus(projectId, runId),
          fetchExecutions(projectId, runId),
        ]);
        setPipelineRun(pipeline);
        setExecutions(execs);
      } catch {
        // A failed poll is retried on the next tick.
      }
    };
    poll();
    const interval = setInterval(poll, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [projectId, runId, isFinished]);

  const handleSubmitFeature = useCallback(async (payload) => {
    if (!activeProject) return;
    setError(null);
    setPipelineRun(null);
    setRunId(null);
    setIsSubmitting(true);
    try {
      const res = await submitFeature(activeProject.id, { ...payload, persona });
      setRunId(res.run_id);
    } catch (err) {
      const msg = err?.response?.data?.detail?.message || err?.response?.data?.detail || err.message || "Unknown error";
      setError(msg);
    } finally {
      setIsSubmitting(false);
    }
  }, [activeProject, persona]);

  const handleCheckpointRespond = useCallback(async (payload) => {
    if (!activeProject || !runId) return;
    setIsResponding(true);
    setError(null);
    try {
      const res = await respondToCheckpoint(activeProject.id, runId, payload);
      // Show the new status ("resuming" or "failed") right away instead of
      // waiting for the next poll, so the review card does not stay on screen.
      setPipelineRun((run) => (run ? { ...run, status: res.status } : run));
    } catch (err) {
      const msg = err?.response?.data?.detail || err.message || "Failed to respond to checkpoint";
      setError(msg);
    } finally {
      setIsResponding(false);
    }
  }, [activeProject, runId]);

  if (!activeProject) {
    return (
      <div className="p-6 flex flex-col items-center justify-center h-64 text-slate-500">
        <p className="text-4xl mb-3">⚡</p>
        <p className="text-sm">Select or create a project first.</p>
      </div>
    );
  }

  const overseerPlan = pipelineRun?.overseer_plan || null;
  const plannedStages = overseerPlan?.stages || ALL_STAGES;

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div>
          <h2 className="text-lg font-semibold text-slate-100">Pipeline</h2>
          <p className="text-xs text-slate-500">
            Run the agent pipeline on{" "}
            <span className="text-emerald-400">{activeProject.name}</span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-violet-300 bg-violet-500/10 border border-violet-500/20 rounded-full px-3 py-1 capitalize">
            Mode: {persona}
          </span>
          {status && (
            <span className={`text-xs rounded-full px-3 py-1 border font-medium capitalize
              ${status === "completed" ? "text-emerald-300 bg-emerald-500/10 border-emerald-500/20"
                : status === "failed" ? "text-rose-300 bg-rose-500/10 border-rose-500/20"
                : status === "awaiting_human" ? "text-amber-300 bg-amber-500/10 border-amber-500/20"
                : "text-sky-300 bg-sky-500/10 border-sky-500/20"}`}>
              {status === "awaiting_human" ? "⏸ Awaiting You" : status}
            </span>
          )}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* LEFT COLUMN */}
        <div className="space-y-4">
          {/* Show form only when not actively running or awaiting */}
          {!isRunning && !isAwaiting && !pipelineRun && (
            <FeatureForm
              project={activeProject}
              onSubmit={handleSubmitFeature}
              disabled={isRunning}
            />
          )}

          {/* Show overseer planning state */}
          {status === "planning_overseer" && (
            <div className="rounded-xl border border-violet-700/40 bg-violet-950/20 p-4 flex items-center gap-3">
              <div className="h-3 w-3 animate-spin rounded-full border-2 border-violet-400 border-t-transparent" />
              <p className="text-sm text-violet-300">Overseer is analysing your request…</p>
            </div>
          )}

          {/* Overseer Plan */}
          <OverseerPlanCard plan={overseerPlan} />

          {/* Human Checkpoint Card */}
          {isAwaiting && (
            <CheckpointCard
              run={pipelineRun}
              onRespond={handleCheckpointRespond}
              isResponding={isResponding}
            />
          )}

          {/* Error */}
          {error && (
            <div className="rounded-md border border-rose-500/40 bg-rose-950/40 p-3 text-xs text-rose-200">
              <span className="font-semibold">Error:</span> {error}
            </div>
          )}

          {/* Pipeline step-by-step display */}
          {pipelineRun && (
            <div className="rounded-xl border border-slate-700 bg-slate-900/60 p-4 space-y-2">
              <div className="flex items-center justify-between mb-1">
                <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-300">
                  Agent Stages
                </h3>
                {isRunning && (
                  <span className="flex items-center gap-1.5 text-xs text-sky-300">
                    <span className="h-1.5 w-1.5 rounded-full bg-sky-400 animate-pulse" />
                    Running…
                  </span>
                )}
              </div>
              {plannedStages.map((stage, i) => (
                <StageStepCard
                  key={`${stage}-${i}`}
                  name={stage}
                  stageStatus={overseerPlan ? stageStatusAt(pipelineRun, i, isRunning) : "pending"}
                />
              ))}
            </div>
          )}

          {/* Planned Tasks */}
          {pipelineRun?.planned_tasks?.length > 0 && (
            <div className="rounded-xl border border-slate-700 bg-slate-900/60 p-4">
              <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-300">
                Planned Tasks
              </h3>
              <ul className="space-y-1">
                {pipelineRun.planned_tasks.map((t, i) => (
                  <li key={t.id || i} className="flex items-start gap-2 text-xs text-slate-200">
                    <span className={`mt-0.5 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase
                      ${t.priority === "high" ? "bg-rose-500/20 text-rose-300"
                        : t.priority === "medium" ? "bg-amber-500/20 text-amber-300"
                        : "bg-slate-600/30 text-slate-300"}`}>
                      {t.priority}
                    </span>
                    <span>{t.description}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Design Artifact */}
          {pipelineRun?.design_artifact && (
            <div className="rounded-xl border border-violet-700/40 bg-violet-950/20 p-4">
              <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-violet-300">
                Design Artifact
              </h3>
              <pre className="text-xs text-violet-200 whitespace-pre-wrap font-mono leading-relaxed">
                {pipelineRun.design_artifact}
              </pre>
            </div>
          )}

          {/* Start new run button after completion/failure */}
          {isFinished && (
            <button
              onClick={() => {
                setPipelineRun(null);
                setRunId(null);
                setError(null);
              }}
              className="w-full rounded-md border border-slate-600 bg-slate-800 py-2 text-sm text-slate-300 hover:border-slate-500 hover:text-slate-100 transition-colors"
            >
              ＋ Start New Run
            </button>
          )}
        </div>

        {/* RIGHT COLUMN */}
        <div className="space-y-4">
          <ExecutionTimeline executions={executions} />
          <CodeViewer code={pipelineRun?.generated_code || ""} />
          <TestResultPanel result={pipelineRun?.test_result} />
          <CodeViewer
            title="Generated Tests"
            code={pipelineRun?.test_code || ""}
            emptyText="Tests appear here after the tester runs."
          />
        </div>
      </div>
    </div>
  );
}
