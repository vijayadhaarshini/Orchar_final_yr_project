export default function ExecutionTimeline({ executions }) {
  if (!executions || executions.length === 0) {
    return (
      <div className="rounded-xl border border-slate-700 bg-slate-900/60 p-4 text-sm text-slate-400">
        No executions yet. Run a feature or bug request to see the pipeline.
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900/60 p-4 text-sm">
      <h2 className="mb-2 text-lg font-semibold text-slate-50">Execution Timeline</h2>
      <ol className="space-y-3">
        {executions.map((exe) => (
          <li key={exe.id} className="flex items-start gap-3">
            <div className="mt-1 h-2 w-2 flex-shrink-0 rounded-full bg-emerald-400" />
            <div className="flex-1 space-y-1">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="text-xs uppercase tracking-wide text-emerald-300">
                    {exe.agent_name}
                  </span>
                  <span
                    className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                      exe.status === "completed"
                        ? "bg-emerald-500/20 text-emerald-300"
                        : exe.status === "running"
                        ? "bg-sky-500/20 text-sky-300"
                        : exe.status === "failed"
                        ? "bg-rose-500/20 text-rose-300"
                        : "bg-slate-600/40 text-slate-200"
                    }`}
                  >
                    {exe.status}
                  </span>
                </div>
                <span className="text-[10px] text-slate-400">
                  {new Date(exe.created_at).toLocaleTimeString()}
                </span>
              </div>
              {exe.output_payload?.error && (
                <p className="text-xs text-rose-300">
                  Error: <span className="font-mono">{exe.output_payload.error}</span>
                </p>
              )}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

