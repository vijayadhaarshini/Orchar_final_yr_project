import { useState } from "react";

export default function FeatureForm({ project, onSubmit, disabled = false }) {
  const [requestType, setRequestType] = useState("feature");
  const [description, setDescription] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!project || !description.trim()) return;
    setIsSubmitting(true);
    try {
      await onSubmit({
        request_type: requestType,
        description: description.trim(),
      });
      setDescription("");
    } finally {
      setIsSubmitting(false);
    }
  };

  const isBusy = isSubmitting || disabled;

  return (
    <form
      onSubmit={handleSubmit}
      className="space-y-3 rounded-xl border border-slate-700 bg-slate-900/60 p-4 shadow"
    >
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-lg font-semibold text-slate-50">Submit Request</h2>
        <span className="text-xs text-slate-400">
          Project ID: {project ? project.id : "—"}
        </span>
      </div>

      <div className="space-y-1">
        <label className="block text-sm text-slate-300">Request Type</label>
        <div className="flex gap-2">
          {["feature", "bug"].map((type) => (
            <button
              key={type}
              type="button"
              onClick={() => setRequestType(type)}
              className={`rounded-md px-4 py-1.5 text-sm font-medium capitalize transition-colors
                ${requestType === type
                  ? "bg-sky-500 text-slate-950"
                  : "border border-slate-600 bg-slate-800 text-slate-300 hover:border-slate-500"
                }`}
            >
              {type}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-1">
        <label className="block text-sm text-slate-300">
          {requestType === "feature"
            ? "Describe the feature you want to build"
            : "Describe the bug and how to reproduce it"}
        </label>
        <textarea
          className="w-full rounded-md border border-slate-600 bg-slate-800 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-emerald-500"
          rows={5}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder={
            requestType === "feature"
              ? "e.g. Add a REST endpoint that returns paginated user records..."
              : "e.g. The login form throws a 500 error when the email contains a + sign..."
          }
          disabled={isBusy}
        />
      </div>

      <button
        type="submit"
        disabled={!project || !description.trim() || isBusy}
        className="inline-flex items-center gap-2 rounded-md bg-emerald-500 px-5 py-2 text-sm font-semibold text-slate-950 hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
      >
        {isBusy ? (
          <>
            <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-slate-950 border-t-transparent" />
            Pipeline running…
          </>
        ) : (
          <>
            <span>▶</span>
            {requestType === "feature" ? "Build Feature" : "Fix Bug"}
          </>
        )}
      </button>

      {!project && (
        <p className="text-xs text-amber-300">
          Select or create a project first.
        </p>
      )}
    </form>
  );
}
