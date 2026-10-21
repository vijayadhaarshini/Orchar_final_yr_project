import { useEffect, useState } from "react";
import CodeViewer from "../components/CodeViewer.jsx";
import TestResultPanel from "../components/TestResultPanel.jsx";
import { useProject } from "../context/ProjectContext.jsx";
import { fetchPipelineRun, listPipelineRuns } from "../services/api.js";

const STATUS_COLORS = {
  completed: "bg-emerald-500/20 text-emerald-300",
  failed: "bg-rose-500/20 text-rose-300",
  pending: "bg-slate-600/30 text-slate-400",
  planning: "bg-sky-500/20 text-sky-300",
  developing: "bg-amber-500/20 text-amber-300",
  testing: "bg-violet-500/20 text-violet-300",
};

export default function HistoryPage() {
  const { activeProject } = useProject();
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedRun, setSelectedRun] = useState(null);
  const [runDetail, setRunDetail] = useState(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  useEffect(() => {
    if (!activeProject) return;
    setLoading(true);
    listPipelineRuns(activeProject.id)
      .then(setRuns)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [activeProject]);

  const handleSelectRun = async (run) => {
    if (selectedRun?.id === run.id) {
      setSelectedRun(null);
      setRunDetail(null);
      return;
    }
    setSelectedRun(run);
    setLoadingDetail(true);
    try {
      const detail = await fetchPipelineRun(activeProject.id, run.id);
      setRunDetail(detail);
    } catch {
      setRunDetail(null);
    } finally {
      setLoadingDetail(false);
    }
  };

  if (!activeProject) {
    return (
      <div className="p-6 flex flex-col items-center justify-center h-64 text-slate-500">
        <p className="text-4xl mb-3">📜</p>
        <p className="text-sm">Select a project to view pipeline history.</p>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <h2 className="text-lg font-semibold text-slate-100 mb-1">Pipeline History</h2>
      <p className="text-xs text-slate-500 mb-5">
        All runs for <span className="text-emerald-400">{activeProject.name}</span>
      </p>

      {loading ? (
        <p className="text-sm text-slate-500">Loading...</p>
      ) : runs.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-700 p-8 text-center">
          <p className="text-slate-500 text-sm">No pipeline runs yet. Go to Pipeline to start one.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {runs.map((run) => {
            const isSelected = selectedRun?.id === run.id;
            return (
              <div key={run.id} className="rounded-xl border border-slate-700 bg-slate-900/40 overflow-hidden">
                {/* Run header */}
                <button
                  onClick={() => handleSelectRun(run)}
                  className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-slate-800/40 transition-colors"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <span className={`shrink-0 rounded px-2 py-0.5 text-[10px] font-semibold uppercase
                      ${STATUS_COLORS[run.status] || "bg-slate-600/30 text-slate-400"}`}>
                      {run.status}
                    </span>
                    <span className="text-sm text-slate-200 truncate">{run.feature_description}</span>
                  </div>
                  <div className="flex items-center gap-3 shrink-0 ml-4">
                    <span className="text-[10px] text-slate-500">
                      {new Date(run.created_at).toLocaleString()}
                    </span>
                    <span className="text-xs text-slate-500 capitalize bg-slate-800 rounded px-2 py-0.5">
                      {run.request_type}
                    </span>
                    <span className="text-xs text-violet-400 capitalize">{run.persona}</span>
                    <svg
                      className={`w-4 h-4 text-slate-500 transition-transform ${isSelected ? "rotate-180" : ""}`}
                      fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </div>
                </button>

                {/* Expanded detail */}
                {isSelected && (
                  <div className="border-t border-slate-700 px-4 py-4 space-y-4">
                    {loadingDetail ? (
                      <p className="text-xs text-slate-500">Loading details...</p>
                    ) : runDetail ? (
                      <>
                        {/* Execution timeline */}
                        {runDetail.execution_timeline?.length > 0 && (
                          <div>
                            <p className="text-xs font-semibold text-slate-400 uppercase mb-2">Timeline</p>
                            <div className="flex flex-wrap gap-2">
                              {runDetail.execution_timeline.map((step, i) => (
                                <span key={i} className={`text-[10px] rounded px-2 py-1
                                  ${step.status === "completed" ? "bg-emerald-500/10 text-emerald-300"
                                    : "bg-rose-500/10 text-rose-300"}`}>
                                  {step.agent} {step.time ? `(${step.time}s)` : ""}
                                  {step.score ? ` · score ${step.score}` : ""}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Design artifact */}
                        {runDetail.design_artifact && (
                          <div>
                            <p className="text-xs font-semibold text-violet-400 uppercase mb-1">Design Artifact</p>
                            <pre className="text-xs text-violet-200 bg-violet-950/20 rounded p-2 whitespace-pre-wrap">
                              {runDetail.design_artifact}
                            </pre>
                          </div>
                        )}

                        {/* Planned tasks */}
                        {runDetail.planned_tasks?.length > 0 && (
                          <div>
                            <p className="text-xs font-semibold text-slate-400 uppercase mb-2">Tasks ({runDetail.planned_tasks.length})</p>
                            <ul className="space-y-1">
                              {runDetail.planned_tasks.map((t, i) => (
                                <li key={i} className="text-xs text-slate-300 flex gap-2">
                                  <span className={`rounded px-1.5 text-[10px] font-semibold uppercase
                                    ${t.priority === "high" ? "bg-rose-500/20 text-rose-300"
                                      : t.priority === "medium" ? "bg-amber-500/20 text-amber-300"
                                      : "bg-slate-600/30 text-slate-400"}`}>
                                    {t.priority}
                                  </span>
                                  {t.description}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}

                        <CodeViewer code={runDetail.generated_code || ""} />
                        <TestResultPanel result={runDetail.test_result} />
                        {runDetail.test_code && <CodeViewer title="Generated Tests" code={runDetail.test_code} />}
                      </>
                    ) : (
                      <p className="text-xs text-rose-400">Failed to load details.</p>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
