import { useCallback, useEffect, useState } from "react";
import { useProject } from "../context/ProjectContext.jsx";
import { createProject, deleteProject, listProjects } from "../services/api.js";

export default function ProjectsPage({ onNavigate }) {
  const { activeProject, setActiveProject } = useProject();
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState(null);
  const [creating, setCreating] = useState(false);

  const loadProjects = useCallback(async () => {
    try {
      const data = await listProjects();
      setProjects(data);
    } catch (err) {
      setError("Failed to load projects.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadProjects(); }, [loadProjects]);

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const created = await createProject({ name: name.trim(), description: description.trim() || null });
      setProjects((prev) => [created, ...prev]);
      setActiveProject(created);
      setName("");
      setDescription("");
    } catch (err) {
      setError(err?.response?.data?.detail || err.message);
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Delete this project and all its data?")) return;
    try {
      await deleteProject(id);
      setProjects((prev) => prev.filter((p) => p.id !== id));
      if (activeProject?.id === id) setActiveProject(null);
    } catch (err) {
      setError("Failed to delete project.");
    }
  };

  const handleSelect = (project) => {
    setActiveProject(project);
    onNavigate("pipeline");
  };

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h2 className="text-lg font-semibold text-slate-100 mb-1">Projects</h2>
      <p className="text-xs text-slate-500 mb-6">Create and manage your Orchar projects.</p>

      {/* Create form */}
      <form onSubmit={handleCreate} className="rounded-xl border border-slate-700 bg-slate-900/60 p-5 mb-6">
        <h3 className="text-sm font-semibold text-slate-300 mb-3">New Project</h3>
        <div className="flex flex-col gap-3">
          <input
            type="text"
            placeholder="Project name *"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full rounded-md bg-slate-800 border border-slate-700 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
            required
          />
          <input
            type="text"
            placeholder="Description (optional)"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="w-full rounded-md bg-slate-800 border border-slate-700 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
          />
          <button
            type="submit"
            disabled={creating || !name.trim()}
            className="self-start rounded-md bg-sky-600 hover:bg-sky-500 disabled:opacity-50 px-4 py-2 text-sm font-medium text-white transition-colors"
          >
            {creating ? "Creating..." : "Create Project"}
          </button>
        </div>
        {error && (
          <p className="mt-3 text-xs text-rose-400">{error}</p>
        )}
      </form>

      {/* Projects list */}
      {loading ? (
        <p className="text-sm text-slate-500">Loading projects...</p>
      ) : projects.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-700 p-8 text-center">
          <p className="text-slate-500 text-sm">No projects yet. Create one above.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {projects.map((project) => {
            const isActive = activeProject?.id === project.id;
            return (
              <div
                key={project.id}
                className={`rounded-xl border p-4 flex items-center justify-between transition-colors
                  ${isActive
                    ? "border-emerald-500/40 bg-emerald-500/5"
                    : "border-slate-700 bg-slate-900/40 hover:border-slate-600"
                  }`}
              >
                <div className="flex items-center gap-3 min-w-0">
                  {isActive && (
                    <span className="shrink-0 h-2 w-2 rounded-full bg-emerald-400" />
                  )}
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-100 truncate">{project.name}</p>
                    {project.description && (
                      <p className="text-xs text-slate-500 truncate">{project.description}</p>
                    )}
                    <p className="text-[10px] text-slate-600 mt-0.5">
                      #{project.id} · {new Date(project.created_at).toLocaleDateString()} · {project.persona}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0 ml-4">
                  <button
                    onClick={() => handleSelect(project)}
                    className="rounded-md bg-sky-600/20 hover:bg-sky-600/40 border border-sky-500/30 px-3 py-1.5 text-xs text-sky-300 transition-colors"
                  >
                    {isActive ? "Open →" : "Select"}
                  </button>
                  <button
                    onClick={() => handleDelete(project.id)}
                    className="rounded-md bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/20 px-3 py-1.5 text-xs text-rose-400 transition-colors"
                  >
                    Delete
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
