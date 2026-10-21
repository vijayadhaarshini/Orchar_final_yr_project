import { useState } from "react";

export default function ProjectForm({ onCreated }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    setIsSubmitting(true);
    try {
      await onCreated({ name: name.trim(), description: description.trim() || null });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="space-y-3 rounded-xl border border-slate-700 bg-slate-900/60 p-4 shadow"
    >
      <h2 className="text-lg font-semibold text-slate-50">1. Create Project</h2>
      <div className="space-y-1">
        <label className="block text-sm text-slate-300">Project Name</label>
        <input
          className="w-full rounded-md border border-slate-600 bg-slate-800 px-3 py-2 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-emerald-500"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="AI Orchestrator Demo"
        />
      </div>
      <div className="space-y-1">
        <label className="block text-sm text-slate-300">Description (optional)</label>
        <textarea
          className="w-full rounded-md border border-slate-600 bg-slate-800 px-3 py-2 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-emerald-500"
          rows={3}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="High-level context for this project..."
        />
      </div>
      <button
        type="submit"
        disabled={isSubmitting || !name.trim()}
        className="inline-flex items-center rounded-md bg-emerald-500 px-4 py-2 text-sm font-medium text-slate-950 hover:bg-emerald-400 disabled:cursor-not-allowed disabled:bg-emerald-800"
      >
        {isSubmitting ? "Creating..." : "Create Project"}
      </button>
    </form>
  );
}

