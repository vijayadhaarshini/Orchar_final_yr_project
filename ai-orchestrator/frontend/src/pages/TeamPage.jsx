import { useEffect, useState } from "react";
import CodeViewer from "../components/CodeViewer.jsx";
import TestResultPanel from "../components/TestResultPanel.jsx";
import { useProject } from "../context/ProjectContext.jsx";
import {
  fetchPipelineRun,
  listPipelineRuns,
  listTeamInputs,
  retriggerStage,
  submitTeamInput,
} from "../services/api.js";

// ---- Role definitions ----

const ROLES = {
  manager: {
    label: "Manager",
    icon: "👔",
    stage: "planning",
    color: "sky",
    description: "Review and refine the task plan before development begins.",
    inputPlaceholder: "e.g. Prioritise the authentication task first. Remove the caching task — not needed for MVP.",
    outputLabel: "Current Plan",
  },
  architect: {
    label: "Architect",
    icon: "🏛️",
    stage: "designing",
    color: "violet",
    description: "Review the system design and provide architectural guidance.",
    inputPlaceholder: "e.g. Use a layered architecture. The API should follow REST conventions with versioning.",
    outputLabel: "Design Artifact",
  },
  developer: {
    label: "Developer",
    icon: "💻",
    stage: "developing",
    color: "amber",
    description: "Review the generated code and request changes or improvements.",
    inputPlaceholder: "e.g. Add error handling for edge cases. Use async/await instead of callbacks.",
    outputLabel: "Generated Code",
  },
  tester: {
    label: "Tester / QA",
    icon: "🧪",
    stage: "testing",
    color: "emerald",
    description: "Add specific test cases or request a re-run with additional coverage.",
    inputPlaceholder: "e.g. Add edge case: empty input. Test for null values. Add integration tests for the API.",
    outputLabel: "Test Results",
  },
};

const COLOR_MAP = {
  sky: {
    badge: "bg-sky-500/20 text-sky-300 border-sky-500/30",
    btn: "bg-sky-600 hover:bg-sky-500",
    border: "border-sky-500/30",
    bg: "bg-sky-500/5",
    text: "text-sky-300",
  },
  violet: {
    badge: "bg-violet-500/20 text-violet-300 border-violet-500/30",
    btn: "bg-violet-600 hover:bg-violet-500",
    border: "border-violet-500/30",
    bg: "bg-violet-500/5",
    text: "text-violet-300",
  },
  amber: {
    badge: "bg-amber-500/20 text-amber-300 border-amber-500/30",
    btn: "bg-amber-600 hover:bg-amber-500",
    border: "border-amber-500/30",
    bg: "bg-amber-500/5",
    text: "text-amber-300",
  },
  emerald: {
    badge: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
    btn: "bg-emerald-600 hover:bg-emerald-500",
    border: "border-emerald-500/30",
    bg: "bg-emerald-500/5",
    text: "text-emerald-300",
  },
};

// ---- Role Panel ----

function RolePanel({ role, runId, projectId, pipelineRun, onRetriggered }) {
  const def = ROLES[role];
  const colors = COLOR_MAP[def.color];
  const [content, setContent] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [retriggering, setRetriggering] = useState(false);
  const [message, setMessage] = useState(null);
  const [inputs, setInputs] = useState([]);

  useEffect(() => {
    if (!projectId || !runId) return;
    listTeamInputs(projectId, runId)
      .then((all) => setInputs(all.filter((i) => i.role === role)))
      .catch(() => {});
  }, [projectId, runId, role]);

  const handleSubmit = async () => {
    if (!content.trim() || !runId) return;
    setSubmitting(true);
    setMessage(null);
    try {
      const result = await submitTeamInput(projectId, runId, { role, content: content.trim() });
      setInputs((prev) => [result, ...prev]);
      setContent("");
      setMessage({ type: "success", text: "Input submitted! Click 'Re-run Stage' to apply it." });
    } catch (err) {
      setMessage({ type: "error", text: err?.response?.data?.detail || "Failed to submit." });
    } finally {
      setSubmitting(false);
    }
  };

  const handleRetrigger = async () => {
    if (!runId) return;
    setRetriggering(true);
    setMessage(null);
    try {
      await retriggerStage(projectId, runId, def.stage);
      setMessage({ type: "success", text: `${def.stage} stage re-triggered! Poll the pipeline for updates.` });
      onRetriggered?.();
    } catch (err) {
      setMessage({ type: "error", text: err?.response?.data?.detail || "Failed to retrigger." });
    } finally {
      setRetriggering(false);
    }
  };

  const pendingCount = inputs.filter((i) => i.status === "pending").length;

  // Current output relevant to this role
  const renderOutput = () => {
    if (!pipelineRun) return <p className="text-xs text-slate-500">No pipeline run selected.</p>;
    if (role === "manager") {
      const tasks = pipelineRun.planned_tasks || [];
      if (tasks.length === 0) return <p className="text-xs text-slate-500">No tasks planned yet.</p>;
      return (
        <ul className="space-y-1">
          {tasks.map((t, i) => (
            <li key={i} className="flex gap-2 text-xs text-slate-200">
              <span className={`rounded px-1.5 text-[10px] font-semibold uppercase shrink-0
                ${t.priority === "high" ? "bg-rose-500/20 text-rose-300"
                  : t.priority === "medium" ? "bg-amber-500/20 text-amber-300"
                  : "bg-slate-600/30 text-slate-400"}`}>
                {t.priority}
              </span>
              {t.description}
            </li>
          ))}
        </ul>
      );
    }
    if (role === "architect") {
      if (!pipelineRun.design_artifact) return <p className="text-xs text-slate-500">No design artifact yet.</p>;
      return <pre className="text-xs text-violet-200 whitespace-pre-wrap">{pipelineRun.design_artifact}</pre>;
    }
    if (role === "developer") {
      return <CodeViewer code={pipelineRun.generated_code || ""} />;
    }
    if (role === "tester") {
      return <TestResultPanel result={pipelineRun.test_result} />;
    }
  };

  return (
    <div className={`rounded-xl border ${colors.border} ${colors.bg} p-5 space-y-4`}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xl">{def.icon}</span>
          <div>
            <h3 className={`text-sm font-semibold ${colors.text}`}>{def.label}</h3>
            <p className="text-[10px] text-slate-500">{def.description}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {pendingCount > 0 && (
            <span className={`text-[10px] rounded-full px-2 py-0.5 ${colors.badge} border`}>
              {pendingCount} pending
            </span>
          )}
          <span className="text-[10px] text-slate-600 uppercase">→ {def.stage}</span>
        </div>
      </div>

      {/* Current output */}
      <div>
        <p className="text-[10px] text-slate-500 uppercase tracking-wide mb-2">{def.outputLabel}</p>
        <div className="rounded-lg bg-slate-900/50 border border-slate-700/50 p-3 max-h-48 overflow-y-auto">
          {renderOutput()}
        </div>
      </div>

      {/* Input form */}
      {runId ? (
        <div className="space-y-2">
          <p className="text-[10px] text-slate-500 uppercase tracking-wide">Your Input</p>
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder={def.inputPlaceholder}
            rows={3}
            className="w-full rounded-md bg-slate-800 border border-slate-700 px-3 py-2 text-xs text-slate-100
              placeholder-slate-600 focus:outline-none focus:ring-1 focus:ring-slate-500 resize-none"
          />
          <div className="flex gap-2">
            <button
              onClick={handleSubmit}
              disabled={submitting || !content.trim()}
              className={`px-3 py-1.5 rounded-md text-xs font-medium text-white transition-colors
                disabled:opacity-40 ${colors.btn}`}
            >
              {submitting ? "Submitting..." : "Submit Input"}
            </button>
            <button
              onClick={handleRetrigger}
              disabled={retriggering}
              className="px-3 py-1.5 rounded-md text-xs font-medium border border-slate-600
                text-slate-300 hover:bg-slate-700 transition-colors disabled:opacity-40"
            >
              {retriggering ? "Re-running..." : "⚡ Re-run Stage"}
            </button>
          </div>
          {message && (
            <p className={`text-[10px] ${message.type === "success" ? "text-emerald-400" : "text-rose-400"}`}>
              {message.text}
            </p>
          )}
        </div>
      ) : (
        <p className="text-xs text-slate-600">Select a pipeline run to submit inputs.</p>
      )}

      {/* Past inputs */}
      {inputs.length > 0 && (
        <div>
          <p className="text-[10px] text-slate-500 uppercase tracking-wide mb-2">Past Inputs</p>
          <div className="space-y-1.5 max-h-32 overflow-y-auto">
            {inputs.map((inp) => (
              <div key={inp.id} className="rounded bg-slate-900/50 border border-slate-700/30 px-2 py-1.5">
                <div className="flex items-center justify-between mb-0.5">
                  <span className={`text-[9px] rounded px-1 py-0.5
                    ${inp.status === "applied" ? "bg-emerald-500/20 text-emerald-400"
                      : "bg-amber-500/20 text-amber-400"}`}>
                    {inp.status}
                  </span>
                  <span className="text-[9px] text-slate-600">
                    {new Date(inp.created_at).toLocaleTimeString()}
                  </span>
                </div>
                <p className="text-[10px] text-slate-400 line-clamp-2">{inp.content}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ---- Main TeamPage ----

export default function TeamPage() {
  const { activeProject } = useProject();
  const [runs, setRuns] = useState([]);
  const [selectedRunId, setSelectedRunId] = useState(null);
  const [pipelineRun, setPipelineRun] = useState(null);
  const [activeRole, setActiveRole] = useState("manager");
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    if (!activeProject) return;
    listPipelineRuns(activeProject.id)
      .then((data) => {
        setRuns(data);
        setSelectedRunId(data[0]?.id ?? null); // newest run of the new project
      })
      .catch(() => {});
  }, [activeProject]);

  useEffect(() => {
    if (!activeProject || !selectedRunId) return;
    fetchPipelineRun(activeProject.id, selectedRunId)
      .then(setPipelineRun)
      .catch(() => {});
  }, [activeProject, selectedRunId, refreshKey]);

  const handleRetriggered = () => {
    setTimeout(() => setRefreshKey((k) => k + 1), 3000);
  };

  if (!activeProject) {
    return (
      <div className="p-6 flex flex-col items-center justify-center h-64 text-slate-500">
        <p className="text-4xl mb-3">👥</p>
        <p className="text-sm">Select a project to use the team workspace.</p>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h2 className="text-lg font-semibold text-slate-100">Team Workspace</h2>
          <p className="text-xs text-slate-500">
            Parallel input lanes — each role contributes independently to their stage.
          </p>
        </div>

        {/* Run selector */}
        {runs.length > 0 && (
          <select
            value={selectedRunId || ""}
            onChange={(e) => setSelectedRunId(Number(e.target.value))}
            className="rounded-md bg-slate-800 border border-slate-700 px-3 py-1.5 text-xs text-slate-200
              focus:outline-none focus:ring-1 focus:ring-slate-500"
          >
            {runs.map((r) => (
              <option key={r.id} value={r.id}>
                #{r.id} — {r.feature_description.slice(0, 50)}{r.feature_description.length > 50 ? "…" : ""} ({r.status})
              </option>
            ))}
          </select>
        )}
      </div>

      {/* Role tabs */}
      <div className="flex gap-2 mb-6 flex-wrap">
        {Object.entries(ROLES).map(([key, def]) => {
          const colors = COLOR_MAP[def.color];
          return (
            <button
              key={key}
              onClick={() => setActiveRole(key)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors border
                ${activeRole === key
                  ? `${colors.badge} ${colors.border}`
                  : "text-slate-500 border-slate-700 hover:text-slate-300 hover:border-slate-600"
                }`}
            >
              <span>{def.icon}</span>
              {def.label}
            </button>
          );
        })}
      </div>

      {/* Active role panel — full width */}
      <RolePanel
        key={`${activeRole}-${selectedRunId}-${refreshKey}`}
        role={activeRole}
        runId={selectedRunId}
        projectId={activeProject?.id}
        pipelineRun={pipelineRun}
        onRetriggered={handleRetriggered}
      />

      {/* Flow diagram hint */}
      <div className="mt-6 rounded-xl border border-slate-800 bg-slate-900/30 p-4">
        <p className="text-[10px] text-slate-500 uppercase tracking-wide mb-3">Non-linear flow</p>
        <div className="flex items-center gap-2 flex-wrap text-[10px] text-slate-500">
          {Object.entries(ROLES).map(([key, def], i) => {
            const colors = COLOR_MAP[def.color];
            return (
              <span key={key} className="flex items-center gap-2">
                <span className={`px-2 py-1 rounded ${colors.badge}`}>
                  {def.icon} {def.label} → {def.stage}
                </span>
                {i < Object.keys(ROLES).length - 1 && (
                  <span className="text-slate-700">↔</span>
                )}
              </span>
            );
          })}
        </div>
        <p className="text-[10px] text-slate-600 mt-2">
          Any role can re-trigger their stage at any time. Changes propagate into the pipeline run without restarting the whole pipeline.
        </p>
      </div>
    </div>
  );
}
