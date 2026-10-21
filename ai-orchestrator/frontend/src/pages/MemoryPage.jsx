import { useEffect, useState } from "react";
import { useProject } from "../context/ProjectContext.jsx";
import { fetchMemory } from "../services/api.js";

const TYPE_COLORS = {
  feature: "bg-sky-500/20 text-sky-300",
  code: "bg-violet-500/20 text-violet-300",
  learned_instruction: "bg-emerald-500/20 text-emerald-300",
};

export default function MemoryPage() {
  const { activeProject } = useProject();
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");

  useEffect(() => {
    if (!activeProject) return;
    setLoading(true);
    fetchMemory(activeProject.id)
      .then(setEntries)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [activeProject]);

  const filtered = entries.filter(
    (e) =>
      e.document.toLowerCase().includes(search.toLowerCase()) ||
      (e.metadata?.type || "").toLowerCase().includes(search.toLowerCase())
  );

  if (!activeProject) {
    return (
      <div className="p-6 flex flex-col items-center justify-center h-64 text-slate-500">
        <p className="text-4xl mb-3">🧠</p>
        <p className="text-sm">Select a project to view its memory.</p>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <h2 className="text-lg font-semibold text-slate-100 mb-1">Memory / Context</h2>
      <p className="text-xs text-slate-500 mb-5">
        ChromaDB vector memory for <span className="text-emerald-400">{activeProject.name}</span>
        {" "}— includes features, code, and self-learned instructions.
      </p>

      {/* Search */}
      <input
        type="text"
        placeholder="Search memory entries..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="w-full mb-5 rounded-md bg-slate-800 border border-slate-700 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
      />

      {/* Legend */}
      <div className="flex gap-3 mb-4 flex-wrap">
        {Object.entries(TYPE_COLORS).map(([type, cls]) => (
          <span key={type} className={`text-[10px] rounded-full px-2 py-0.5 capitalize ${cls}`}>
            {type.replace("_", " ")}
          </span>
        ))}
      </div>

      {loading ? (
        <p className="text-sm text-slate-500">Loading memory...</p>
      ) : filtered.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-700 p-8 text-center">
          <p className="text-slate-500 text-sm">
            {entries.length === 0
              ? "No memory yet. Run a pipeline to populate ChromaDB."
              : "No entries match your search."}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-xs text-slate-500">{filtered.length} entries</p>
          {filtered.map((entry) => {
            const type = entry.metadata?.type || "unknown";
            const taskType = entry.metadata?.task_type;
            return (
              <div key={entry.id} className="rounded-xl border border-slate-700 bg-slate-900/40 p-4">
                <div className="flex items-center gap-2 mb-2">
                  <span className={`text-[10px] rounded-full px-2 py-0.5 capitalize font-medium
                    ${TYPE_COLORS[type] || "bg-slate-600/30 text-slate-400"}`}>
                    {type.replace("_", " ")}
                  </span>
                  {taskType && (
                    <span className="text-[10px] text-slate-500">Task: {taskType}</span>
                  )}
                  <span className="text-[10px] text-slate-600 ml-auto font-mono">{entry.id}</span>
                </div>
                <p className="text-xs text-slate-300 whitespace-pre-wrap line-clamp-6 leading-relaxed">
                  {entry.document}
                </p>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
