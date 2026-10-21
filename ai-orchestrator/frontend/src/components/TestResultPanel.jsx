import { useState } from "react";

export default function TestResultPanel({ result }) {
  const [showErrors, setShowErrors] = useState(false);

  const status = result?.status || "pending";
  const coverage = result?.coverage ?? 0;
  const hasErrors = !!result?.errors;

  const statusColor =
    status === "pass"
      ? "bg-emerald-500 text-slate-950"
      : status === "fail"
      ? "bg-rose-500 text-slate-950"
      : "bg-slate-700 text-slate-100";

  const statusLabel = status === "pass" ? "Pass" : status === "fail" ? "Fail" : "Pending";

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900/60 p-4 text-sm">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-slate-50">Test Results</h2>
        <span className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold ${statusColor}`}>
          {statusLabel}
        </span>
      </div>
      <div className="space-y-2 text-sm text-slate-200">
        <p>
          <span className="text-slate-400">Coverage:</span>{" "}
          <span className="font-mono text-emerald-300">{coverage.toFixed(1)}%</span>
        </p>
        <button
          type="button"
          disabled={!hasErrors}
          onClick={() => setShowErrors((prev) => !prev)}
          className="text-xs font-medium text-sky-300 hover:text-sky-200 disabled:cursor-not-allowed disabled:text-slate-500"
        >
          {hasErrors ? (showErrors ? "Hide error logs" : "Show error logs") : "No error logs"}
        </button>
        {hasErrors && showErrors && (
          <pre className="mt-2 max-h-56 overflow-auto rounded-md bg-slate-950/80 p-3 text-xs text-rose-200">
            {result.errors}
          </pre>
        )}
      </div>
    </div>
  );
}

