import { useEffect, useState } from "react";
import { useProject } from "../context/ProjectContext.jsx";
import { listTasks, updateTaskStatus } from "../services/api.js";

const STATUSES = ["planned", "in_progress", "completed", "cancelled"];
const STATUS_COLORS = {
  planned: "bg-sky-500/20 text-sky-300",
  in_progress: "bg-amber-500/20 text-amber-300",
  completed: "bg-emerald-500/20 text-emerald-300",
  cancelled: "bg-slate-600/30 text-slate-400",
};
const PRIORITY_COLORS = {
  high: "bg-rose-500/20 text-rose-300",
  medium: "bg-amber-500/20 text-amber-300",
  low: "bg-slate-600/30 text-slate-400",
};

export default function TasksPage() {
  const { activeProject } = useProject();
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");
  const [updating, setUpdating] = useState(null);

  useEffect(() => {
    if (!activeProject) return;
    setLoading(true);
    listTasks(activeProject.id)
      .then(setTasks)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [activeProject]);

  const handleStatusChange = async (taskId, newStatus) => {
    setUpdating(taskId);
    try {
      const updated = await updateTaskStatus(activeProject.id, taskId, newStatus);
      setTasks((prev) => prev.map((t) => (t.id === taskId ? updated : t)));
    } catch {
      // ignore
    } finally {
      setUpdating(null);
    }
  };

  const filtered = filter === "all" ? tasks : tasks.filter((t) => t.status === filter);

  const counts = STATUSES.reduce((acc, s) => {
    acc[s] = tasks.filter((t) => t.status === s).length;
    return acc;
  }, {});

  if (!activeProject) {
    return (
      <div className="p-6 flex flex-col items-center justify-center h-64 text-slate-500">
        <p className="text-4xl mb-3">✅</p>
        <p className="text-sm">Select a project to view tasks.</p>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <h2 className="text-lg font-semibold text-slate-100 mb-1">Tasks</h2>
      <p className="text-xs text-slate-500 mb-5">
        All planned tasks for <span className="text-emerald-400">{activeProject.name}</span>
      </p>

      {/* Filter bar */}
      <div className="flex gap-2 mb-5 flex-wrap">
        <button
          onClick={() => setFilter("all")}
          className={`px-3 py-1.5 rounded-full text-xs transition-colors ${filter === "all" ? "bg-slate-600 text-slate-100" : "text-slate-500 hover:text-slate-300"}`}
        >
          All ({tasks.length})
        </button>
        {STATUSES.map((s) => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className={`px-3 py-1.5 rounded-full text-xs capitalize transition-colors
              ${filter === s ? "bg-slate-600 text-slate-100" : "text-slate-500 hover:text-slate-300"}`}
          >
            {s.replace("_", " ")} ({counts[s] || 0})
          </button>
        ))}
      </div>

      {loading ? (
        <p className="text-sm text-slate-500">Loading tasks...</p>
      ) : filtered.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-700 p-8 text-center">
          <p className="text-slate-500 text-sm">
            {tasks.length === 0 ? "No tasks yet. Run a pipeline to generate tasks." : "No tasks match the current filter."}
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map((task) => (
            <div
              key={task.id}
              className="rounded-lg border border-slate-700 bg-slate-900/40 px-4 py-3 flex items-start justify-between gap-4"
            >
              <div className="flex items-start gap-3 min-w-0">
                <span className={`shrink-0 mt-0.5 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase
                  ${PRIORITY_COLORS[task.priority] || PRIORITY_COLORS.low}`}>
                  {task.priority}
                </span>
                <div className="min-w-0">
                  <p className="text-sm text-slate-200">{task.description}</p>
                  <p className="text-[10px] text-slate-500 mt-0.5">
                    #{task.id} · {new Date(task.created_at).toLocaleDateString()}
                  </p>
                </div>
              </div>
              <div className="shrink-0">
                <select
                  value={task.status}
                  onChange={(e) => handleStatusChange(task.id, e.target.value)}
                  disabled={updating === task.id}
                  className={`rounded px-2 py-1 text-xs border border-slate-700 bg-slate-800 cursor-pointer
                    disabled:opacity-50 focus:outline-none
                    ${STATUS_COLORS[task.status] || ""}`}
                >
                  {STATUSES.map((s) => (
                    <option key={s} value={s} className="bg-slate-800 text-slate-200">
                      {s.replace("_", " ")}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
