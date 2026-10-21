const STATUS_COLORS = {
  pending: "bg-slate-700 text-slate-100",
  running: "bg-sky-500 text-slate-950",
  completed: "bg-emerald-500 text-slate-950",
  failed: "bg-rose-500 text-slate-950",
};

const STATUS_LABELS = {
  pending: "Pending",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
};

export default function AgentStatusCard({ name, status, latestExecution }) {
  const colorClass = STATUS_COLORS[status] || STATUS_COLORS.pending;
  const label = STATUS_LABELS[status] || STATUS_LABELS.pending;

  return (
    <div className="flex flex-col justify-between rounded-xl border border-slate-700 bg-slate-900/80 p-3 text-sm shadow">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-slate-50">{name}</h3>
        <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${colorClass}`}>
          {label}
        </span>
      </div>
      <div className="mt-2 space-y-1 text-xs text-slate-300">
        {latestExecution ? (
          <>
            <p>
              <span className="font-medium text-slate-200">Last status:</span> {latestExecution.status}
            </p>
            <p className="truncate text-slate-400">
              <span className="font-medium text-slate-200">Created:</span>{" "}
              {new Date(latestExecution.created_at).toLocaleTimeString()}
            </p>
          </>
        ) : (
          <p className="text-slate-400">Awaiting execution...</p>
        )}
      </div>
    </div>
  );
}

