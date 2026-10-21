import { useEffect, useState } from "react";
import { useProject } from "../context/ProjectContext.jsx";
import { fetchAnalytics } from "../services/api.js";

function StatCard({ label, value, sub, color = "text-sky-300" }) {
  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900/60 p-4 flex flex-col gap-1">
      <p className="text-[10px] text-slate-500 uppercase tracking-wide">{label}</p>
      <p className={`text-2xl font-bold ${color}`}>{value}</p>
      {sub && <p className="text-[10px] text-slate-500">{sub}</p>}
    </div>
  );
}

function BarRow({ label, value, max, color }) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-slate-400 w-28 shrink-0 truncate capitalize">{label}</span>
      <div className="flex-1 h-2 rounded-full bg-slate-800">
        <div className={`h-2 rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-slate-400 w-8 text-right">{value}</span>
    </div>
  );
}

export default function AnalyticsPage() {
  const { activeProject } = useProject();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!activeProject) return;
    setLoading(true);
    fetchAnalytics(activeProject.id)
      .then(setData)
      .catch(() => setError("Failed to load analytics."))
      .finally(() => setLoading(false));
  }, [activeProject]);

  if (!activeProject) {
    return (
      <div className="p-6 flex flex-col items-center justify-center h-64 text-slate-500">
        <p className="text-4xl mb-3">📊</p>
        <p className="text-sm">Select a project to view analytics.</p>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <h2 className="text-lg font-semibold text-slate-100 mb-1">Analytics</h2>
      <p className="text-xs text-slate-500 mb-5">
        Stats for <span className="text-emerald-400">{activeProject.name}</span>
      </p>

      {loading ? (
        <p className="text-sm text-slate-500">Loading analytics...</p>
      ) : error ? (
        <p className="text-sm text-rose-400">{error}</p>
      ) : !data ? null : (
        <div className="space-y-6">
          {/* KPI cards */}
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            <StatCard label="Total Runs" value={data.total_runs} color="text-sky-300" />
            <StatCard
              label="Successful Runs"
              value={data.successful_runs}
              sub={`${data.total_runs > 0 ? Math.round((data.successful_runs / data.total_runs) * 100) : 0}% success rate`}
              color="text-emerald-300"
            />
            <StatCard label="Failed Runs" value={data.failed_runs} color="text-rose-300" />
            <StatCard
              label="Test Pass Rate"
              value={`${data.test_pass_rate}%`}
              sub="across completed runs"
              color="text-violet-300"
            />
            <StatCard
              label="Avg Exec Time"
              value={`${data.avg_execution_time}s`}
              sub="per agent call"
              color="text-amber-300"
            />
            <StatCard
              label="Total Tasks"
              value={data.total_tasks}
              sub="planned across all runs"
              color="text-sky-300"
            />
          </div>

          {/* Pipeline health bar */}
          {data.total_runs > 0 && (
            <div className="rounded-xl border border-slate-700 bg-slate-900/60 p-4">
              <h3 className="text-sm font-semibold text-slate-300 mb-3">Pipeline Health</h3>
              <div className="flex rounded-full overflow-hidden h-3">
                <div
                  className="bg-emerald-500 transition-all"
                  style={{ width: `${(data.successful_runs / data.total_runs) * 100}%` }}
                />
                <div
                  className="bg-rose-500 transition-all"
                  style={{ width: `${(data.failed_runs / data.total_runs) * 100}%` }}
                />
                <div className="bg-slate-700 flex-1" />
              </div>
              <div className="flex gap-4 mt-2 text-[10px] text-slate-500">
                <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-emerald-500 inline-block" /> Completed</span>
                <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-rose-500 inline-block" /> Failed</span>
                <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-slate-700 inline-block" /> Other</span>
              </div>
            </div>
          )}

          {/* Per-agent stats */}
          {data.agent_stats?.length > 0 && (
            <div className="rounded-xl border border-slate-700 bg-slate-900/60 p-4">
              <h3 className="text-sm font-semibold text-slate-300 mb-4">Agent Performance</h3>
              <div className="space-y-4">
                {data.agent_stats.map((agent) => {
                  const maxRuns = Math.max(...data.agent_stats.map((a) => a.total_runs), 1);
                  return (
                    <div key={agent.agent_name} className="space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-medium text-slate-300 capitalize">{agent.agent_name}</span>
                        <div className="flex gap-3 text-[10px] text-slate-500">
                          <span className="text-emerald-400">{agent.successful} ✓</span>
                          <span className="text-rose-400">{agent.failed} ✗</span>
                          <span>{agent.avg_execution_time}s avg</span>
                        </div>
                      </div>
                      <BarRow
                        label="runs"
                        value={agent.total_runs}
                        max={maxRuns}
                        color={agent.failed > agent.successful ? "bg-rose-500" : "bg-sky-500"}
                      />
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {data.total_runs === 0 && (
            <div className="rounded-xl border border-dashed border-slate-700 p-8 text-center">
              <p className="text-slate-500 text-sm">No pipeline runs yet. Start one in the Pipeline page.</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
