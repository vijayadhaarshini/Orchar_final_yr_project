import { useCallback, useEffect, useState } from "react";
import { useProject } from "../context/ProjectContext.jsx";
import {
  fetchBusMessages,
  fetchLevel5Summary,
} from "../services/api.js";

// ─────────────────────────────────────────────────────────────────────────────
// Colour helpers
// ─────────────────────────────────────────────────────────────────────────────

const C = {
  sky:     { border: "border-sky-500/40",     bg: "bg-sky-950/30",     text: "text-sky-300",     dot: "bg-sky-400",     badge: "bg-sky-500/20 text-sky-300"      },
  violet:  { border: "border-violet-500/40",  bg: "bg-violet-950/30",  text: "text-violet-300",  dot: "bg-violet-400",  badge: "bg-violet-500/20 text-violet-300" },
  amber:   { border: "border-amber-500/40",   bg: "bg-amber-950/30",   text: "text-amber-300",   dot: "bg-amber-400",   badge: "bg-amber-500/20 text-amber-300"   },
  emerald: { border: "border-emerald-500/40", bg: "bg-emerald-950/30", text: "text-emerald-300", dot: "bg-emerald-400", badge: "bg-emerald-500/20 text-emerald-300"},
  rose:    { border: "border-rose-500/40",    bg: "bg-rose-950/30",    text: "text-rose-300",    dot: "bg-rose-400",    badge: "bg-rose-500/20 text-rose-300"     },
  fuchsia: { border: "border-fuchsia-500/40", bg: "bg-fuchsia-950/30", text: "text-fuchsia-300", dot: "bg-fuchsia-400", badge: "bg-fuchsia-500/20 text-fuchsia-300"},
  teal:    { border: "border-teal-500/40",    bg: "bg-teal-950/30",    text: "text-teal-300",    dot: "bg-teal-400",    badge: "bg-teal-500/20 text-teal-300"     },
  slate:   { border: "border-slate-700",      bg: "bg-slate-900/60",   text: "text-slate-300",   dot: "bg-slate-500",   badge: "bg-slate-700/60 text-slate-300"   },
};

// ─────────────────────────────────────────────────────────────────────────────
// Small shared components
// ─────────────────────────────────────────────────────────────────────────────

function Badge({ label, color = "slate" }) {
  return (
    <span className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-medium ${C[color].badge}`}>
      {label}
    </span>
  );
}

function Pulse({ color = "emerald" }) {
  return (
    <span className="relative flex h-2 w-2 shrink-0">
      <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${C[color].dot} opacity-60`} />
      <span className={`relative inline-flex rounded-full h-2 w-2 ${C[color].dot}`} />
    </span>
  );
}

function StatCard({ label, value, sub, color = "sky", icon }) {
  const c = C[color];
  return (
    <div className={`rounded-xl border p-4 flex flex-col gap-1 ${c.border} ${c.bg}`}>
      <div className="flex items-center justify-between">
        <p className="text-[10px] text-slate-500 uppercase tracking-wide">{label}</p>
        {icon && <span className="text-base">{icon}</span>}
      </div>
      <p className={`text-2xl font-bold ${c.text}`}>{value ?? "—"}</p>
      {sub && <p className="text-[10px] text-slate-500">{sub}</p>}
    </div>
  );
}

function EmptyState({ icon, message, sub }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-700 p-10 text-center">
      <p className="text-3xl mb-2">{icon}</p>
      <p className="text-sm text-slate-400">{message}</p>
      {sub && <p className="text-xs text-slate-600 mt-1">{sub}</p>}
    </div>
  );
}

function Spinner() {
  return <p className="text-sm text-slate-500 py-8 text-center">Loading…</p>;
}

// ─────────────────────────────────────────────────────────────────────────────
// Tab 1 — Overview (aggregated stats + per-run breakdown)
// ─────────────────────────────────────────────────────────────────────────────

function OverviewTab({ summary, onSelectRun, selectedRun }) {
  if (!summary) return <Spinner />;

  const { totals, recent_runs } = summary;

  const stats = [
    { label: "Debate Rounds",       value: totals.debate_rounds,       icon: "⟳",  color: "rose",    sub: "Developer ↔ Critic loops" },
    { label: "Bus Messages",        value: totals.bus_messages,        icon: "📡", color: "violet",  sub: "P2P messages across runs" },
    { label: "Sub-Agents Spawned",  value: totals.spawned_agents,      icon: "🌿", color: "sky",     sub: "Specialist agents spawned" },
    { label: "Roles Discovered",    value: totals.role_discoveries,    icon: "🔬", color: "fuchsia", sub: "New dynamic roles created" },
    { label: "Evolved Instructions",value: totals.evolved_instructions,icon: "💉", color: "emerald", sub: "Injected into agent prompts" },
    { label: "Dynamic Roles",       value: totals.dynamic_roles,       icon: "🤖", color: "amber",   sub: "In dynamic_roles.json" },
  ];

  return (
    <div className="space-y-6">
      {/* KPI grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {stats.map((s) => <StatCard key={s.label} {...s} />)}
      </div>

      {/* Per-run breakdown */}
      <div className="rounded-xl border border-slate-700 bg-slate-900/40 overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-800">
          <p className="text-xs font-semibold text-slate-300">Recent Runs — Level 5 Activity</p>
          <p className="text-[10px] text-slate-500 mt-0.5">Click a run to inspect its bus messages</p>
        </div>

        {recent_runs.length === 0 ? (
          <div className="p-6 text-center text-slate-500 text-sm">
            No pipeline runs yet. Submit a feature to see Level 5 data.
          </div>
        ) : (
          <div className="divide-y divide-slate-800">
            {recent_runs.map((run) => {
              const isSelected = selectedRun?.run_id === run.run_id;
              const statusColor = run.status === "completed" ? "emerald" : run.status === "failed" ? "rose" : "amber";
              return (
                <button
                  key={run.run_id}
                  onClick={() => onSelectRun(isSelected ? null : run)}
                  className={`w-full text-left px-4 py-3 transition-colors hover:bg-slate-800/40
                    ${isSelected ? "bg-slate-800/60" : ""}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className={`text-[10px] font-medium ${C[statusColor].text}`}>
                          #{run.run_id} · {run.status}
                        </span>
                        <span className="text-[10px] text-slate-600">
                          {run.created_at ? new Date(run.created_at).toLocaleString() : ""}
                        </span>
                      </div>
                      <p className="text-xs text-slate-400 truncate">{run.feature_description}</p>
                    </div>
                    <div className="flex items-center gap-3 shrink-0 text-[10px] text-slate-500">
                      {run.debate_rounds > 0 && <span className="text-rose-400">⟳ {run.debate_rounds}</span>}
                      {run.spawned_agents?.length > 0 && <span className="text-sky-400">🌿 {run.spawned_agents.length}</span>}
                      {run.bus_messages > 0 && <span className="text-violet-400">📡 {run.bus_messages}</span>}
                      {run.role_discoveries?.length > 0 && <span className="text-fuchsia-400">🔬 {run.role_discoveries.length}</span>}
                    </div>
                  </div>

                  {/* Expanded: sub-agent details */}
                  {isSelected && run.spawned_agents?.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {run.spawned_agents.map((a, i) => (
                        <span key={i} className={`text-[10px] rounded px-2 py-0.5 border
                          ${a.success ? "border-emerald-500/30 text-emerald-300 bg-emerald-950/20"
                                      : "border-rose-500/30 text-rose-300 bg-rose-950/20"}`}>
                          {a.label || a.role} {a.success ? "✓" : "✗"}
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Expanded: role discoveries */}
                  {isSelected && run.role_discoveries?.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-2">
                      {run.role_discoveries.map((r, i) => (
                        <span key={i} className="text-[10px] rounded px-2 py-0.5 border border-fuchsia-500/30 text-fuchsia-300 bg-fuchsia-950/20">
                          🔬 {r.label || r.role} discovered
                        </span>
                      ))}
                    </div>
                  )}
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Tab 2 — P2P Message Bus (real bus messages from selected run)
// ─────────────────────────────────────────────────────────────────────────────

function BusTab({ summary }) {
  const [selectedRunId, setSelectedRunId] = useState(null);
  const [busData, setBusData] = useState(null);
  const [loading, setLoading] = useState(false);

  // Keep the chosen run if it is still in the list. Otherwise (first load,
  // or a different project) pick the newest run that has bus messages.
  useEffect(() => {
    if (!summary) return;
    setSelectedRunId((current) => {
      if (summary.recent_runs.some((r) => r.run_id === current)) return current;
      return summary.recent_runs.find((r) => r.bus_messages > 0)?.run_id ?? null;
    });
  }, [summary]);

  useEffect(() => {
    if (!selectedRunId) return;
    setLoading(true);
    fetchBusMessages(selectedRunId)
      .then(setBusData)
      .catch(() => setBusData(null))
      .finally(() => setLoading(false));
  }, [selectedRunId]);

  const TYPE_COLOR = {
    detailed_critique: "rose",
    sub_agent_code:    "sky",
    test_failure:      "amber",
    sub_agent_spawn:   "teal",
  };

  // Inbox summary from messages
  const inboxCounts = {};
  (busData?.messages || []).forEach((m) => {
    inboxCounts[m.to_agent] = (inboxCounts[m.to_agent] || 0) + 1;
  });

  const runsWithBus = (summary?.recent_runs || []).filter((r) => r.bus_messages > 0);

  return (
    <div className="space-y-5">
      {/* Run selector */}
      <div className="flex items-center gap-3">
        <p className="text-xs text-slate-500 shrink-0">Run:</p>
        {runsWithBus.length === 0 ? (
          <p className="text-xs text-slate-600">No runs with bus messages yet</p>
        ) : (
          <div className="flex gap-2 flex-wrap">
            {runsWithBus.map((r) => (
              <button
                key={r.run_id}
                onClick={() => setSelectedRunId(r.run_id)}
                className={`text-[11px] rounded-lg border px-2.5 py-1.5 transition-colors
                  ${selectedRunId === r.run_id
                    ? "border-violet-500/60 bg-violet-950/30 text-violet-300"
                    : "border-slate-700 text-slate-500 hover:text-slate-300 hover:border-slate-600"}`}
              >
                #{r.run_id} · {r.bus_messages} msg{r.bus_messages !== 1 ? "s" : ""}
              </button>
            ))}
          </div>
        )}
      </div>

      {!selectedRunId ? (
        <EmptyState icon="📡" message="No bus activity yet" sub="Submit a feature to start seeing real P2P messages" />
      ) : loading ? (
        <Spinner />
      ) : !busData || busData.total === 0 ? (
        <EmptyState icon="📭" message="No messages in this run's bus log" />
      ) : (
        <>
          {/* Inbox breakdown */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {Object.entries(inboxCounts).map(([agent, count]) => {
              const color = agent === "developer" ? "emerald" : agent === "composer" ? "sky" : "violet";
              return (
                <div key={agent} className={`rounded-xl border p-3 ${C[color].border} ${C[color].bg}`}>
                  <p className={`text-xs font-semibold capitalize ${C[color].text}`}>{agent}</p>
                  <p className="text-2xl font-bold text-white mt-1">{count}</p>
                  <p className="text-[10px] text-slate-500">messages received</p>
                </div>
              );
            })}
          </div>

          {/* Message feed */}
          <div className="rounded-xl border border-slate-700 bg-slate-900/40 overflow-hidden">
            <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-800">
              <Pulse color="violet" />
              <p className="text-xs font-medium text-slate-300">
                {busData.total} message{busData.total !== 1 ? "s" : ""} · Run #{selectedRunId}
              </p>
            </div>
            <div className="divide-y divide-slate-800 max-h-96 overflow-y-auto">
              {busData.messages.map((msg, i) => {
                const color = TYPE_COLOR[msg.message_type] || "slate";
                return (
                  <div key={i} className="px-4 py-3 flex items-start gap-3">
                    <div className={`h-1.5 w-1.5 rounded-full shrink-0 mt-1.5 ${C[color].dot}`} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap mb-1">
                        <span className={`text-[10px] font-semibold ${C[color].text}`}>{msg.message_type}</span>
                        <span className="text-[10px] text-slate-500">{msg.from_agent} → {msg.to_agent}</span>
                        <span className="text-[10px] text-slate-700 ml-auto">
                          {msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString() : ""}
                        </span>
                      </div>
                      {msg.content && typeof msg.content === "object" && (
                        <div className="flex gap-3 flex-wrap">
                          {msg.content.score !== undefined && (
                            <span className={`text-[10px] font-bold ${msg.content.score >= 7 ? "text-emerald-400" : "text-rose-400"}`}>
                              score {msg.content.score}/10
                            </span>
                          )}
                          {msg.content.critique && (
                            <span className="text-[10px] text-slate-400 truncate max-w-xs">{msg.content.critique}</span>
                          )}
                          {msg.content.role && (
                            <span className="text-[10px] text-slate-400">{msg.content.label || msg.content.role}</span>
                          )}
                          {msg.content.code_length !== undefined && (
                            <span className="text-[10px] text-slate-500">{msg.content.code_length} chars of code</span>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Tab 3 — Dynamic Roles (static 6 + runtime-discovered)
// ─────────────────────────────────────────────────────────────────────────────

const ROLE_ICONS = {
  database: "🗄️", auth: "🔐", cache: "⚡", api: "🔌",
  notification: "📨", storage: "📦",
};

function RoleCard({ role, dynamic = false }) {
  return (
    <div className={`rounded-xl border p-3 ${dynamic ? "border-fuchsia-500/40 bg-fuchsia-950/10" : "border-slate-700 bg-slate-900/50"}`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-xl">{ROLE_ICONS[role.name] || "🤖"}</span>
          <span className={`text-xs font-semibold ${dynamic ? "text-fuchsia-300" : "text-slate-300"}`}>{role.label}</span>
        </div>
        <Badge label={dynamic ? "dynamic" : "static"} color={dynamic ? "fuchsia" : "slate"} />
      </div>
      <div className="flex flex-wrap gap-1">
        {(role.keywords || []).slice(0, 5).map((kw) => (
          <span key={kw} className={`text-[10px] rounded px-1.5 py-0.5 ${dynamic ? "bg-fuchsia-900/40 text-fuchsia-400" : "bg-slate-800 text-slate-500"}`}>
            {kw}
          </span>
        ))}
      </div>
    </div>
  );
}

function DynamicRolesTab({ summary }) {
  const staticRoles = [
    { name: "database", label: "Database Agent", keywords: ["database", "db", "orm", "sqlalchemy"] },
    { name: "auth",     label: "Auth Agent",     keywords: ["auth", "jwt", "login", "token"] },
    { name: "cache",    label: "Cache Agent",    keywords: ["cache", "redis", "lru", "ttl"] },
    { name: "api",      label: "API Agent",      keywords: ["api", "endpoint", "route", "fastapi"] },
    { name: "notification", label: "Notification Agent", keywords: ["email", "smtp", "webhook"] },
    { name: "storage",  label: "Storage Agent",  keywords: ["file", "upload", "s3", "bucket"] },
  ];

  const dynamicRoles = summary?.dynamic_roles || [];

  // Which runs discovered new roles?
  const discoveryRuns = (summary?.recent_runs || []).filter((r) => r.role_discoveries?.length > 0);

  return (
    <div className="space-y-6">
      {/* Static roles */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <p className="text-[10px] text-slate-500 uppercase tracking-wide">Built-in Static Roles</p>
          <Badge label="6 fixed" color="slate" />
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {staticRoles.map((r) => <RoleCard key={r.name} role={r} />)}
        </div>
      </div>

      {/* Dynamic roles */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <p className="text-[10px] text-slate-500 uppercase tracking-wide">Runtime-Discovered Roles</p>
          <Badge label={`${dynamicRoles.length} in dynamic_roles.json`} color="fuchsia" />
        </div>

        {dynamicRoles.length === 0 ? (
          <EmptyState
            icon="🔬"
            message="No dynamic roles discovered yet"
            sub='Run a feature with novel task types (GraphQL, WebSocket, ML, etc.) to trigger role discovery'
          />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {dynamicRoles.map((r) => <RoleCard key={r.name} role={r} dynamic />)}
          </div>
        )}
      </div>

      {/* Discovery history */}
      {discoveryRuns.length > 0 && (
        <div className="rounded-xl border border-fuchsia-500/20 bg-fuchsia-950/10 p-4">
          <p className="text-xs font-semibold text-fuchsia-300 mb-3">Discovery History</p>
          <div className="space-y-2">
            {discoveryRuns.map((run) =>
              run.role_discoveries.map((rd, i) => (
                <div key={`${run.run_id}-${i}`} className="flex items-center gap-3 text-[11px]">
                  <span className="text-fuchsia-400">🔬</span>
                  <span className="text-fuchsia-300 font-medium">{rd.label || rd.role}</span>
                  <span className="text-slate-500">discovered in run #{run.run_id}</span>
                  <span className="text-slate-600 ml-auto text-[10px] truncate max-w-[200px]">{run.feature_description}</span>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Tab 4 — Self-Evolution (real evolved prompts + debate scores)
// ─────────────────────────────────────────────────────────────────────────────

function SelfEvolutionTab({ summary }) {
  const evolvedPrompts = summary?.evolved_prompts || {};
  const agentNames = Object.keys(evolvedPrompts);

  const AGENT_COLORS = {
    developer: "emerald", critic: "rose", tester: "blue",
    planner: "sky", designer: "violet", self_evolve: "fuchsia",
  };

  // Debate score trend across runs
  const runsWithDebate = (summary?.recent_runs || [])
    .filter((r) => r.debate_rounds > 0)
    .slice(0, 8);

  return (
    <div className="space-y-6">
      {/* Evolved prompts per agent */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <p className="text-[10px] text-slate-500 uppercase tracking-wide">Evolved Agent Instructions</p>
          <Badge label={`${summary?.totals?.evolved_instructions || 0} total`} color="emerald" />
          <Badge label="Track 1 · Prompt Level" color="violet" />
        </div>

        {agentNames.length === 0 ? (
          <EmptyState
            icon="💉"
            message="No evolved instructions yet"
            sub="Complete a pipeline run — SelfEvolve will generate and inject instructions for future runs"
          />
        ) : (
          <div className="space-y-3">
            {agentNames.map((agent) => {
              const instrs = evolvedPrompts[agent] || [];
              const color = AGENT_COLORS[agent] || "slate";
              return (
                <div key={agent} className={`rounded-xl border p-3 ${C[color].border} ${C[color].bg}`}>
                  <div className="flex items-center gap-2 mb-2">
                    <span className={`text-xs font-semibold capitalize ${C[color].text}`}>{agent}</span>
                    <Badge label={`${instrs.length} instruction${instrs.length !== 1 ? "s" : ""}`} color={color} />
                  </div>
                  <div className="space-y-1.5">
                    {instrs.map((instr, i) => (
                      <p key={i} className="text-[11px] text-slate-400 leading-relaxed border-l-2 border-slate-700 pl-2">
                        {instr}
                      </p>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Debate score history */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <p className="text-[10px] text-slate-500 uppercase tracking-wide">Debate Round Scores</p>
          <Badge label="Developer ↔ Critic" color="rose" />
        </div>

        {runsWithDebate.length === 0 ? (
          <EmptyState
            icon="⟳"
            message="No debate rounds yet"
            sub="The debate loop fires when the Developer's initial code is scored below the threshold"
          />
        ) : (
          <div className="space-y-3">
            {runsWithDebate.map((run) => (
              <div key={run.run_id} className="rounded-xl border border-slate-700 bg-slate-900/40 p-3">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-[10px] text-slate-500">Run #{run.run_id}</span>
                  <span className="text-[10px] text-slate-600 truncate">{run.feature_description}</span>
                  <span className="text-[10px] text-rose-400 ml-auto">{run.debate_rounds} round{run.debate_rounds !== 1 ? "s" : ""}</span>
                </div>
                <div className="flex items-end gap-1.5 h-10">
                  {(run.debate_scores || []).map((score, i) => {
                    const h = Math.max(4, (score / 10) * 40);
                    const color = score >= 7 ? "bg-emerald-500" : score >= 5 ? "bg-amber-500" : "bg-rose-500";
                    return (
                      <div key={i} className="flex flex-col items-center gap-0.5">
                        <span className="text-[9px] text-slate-600">{score}</span>
                        <div className={`w-4 rounded-t ${color}`} style={{ height: `${h}px` }} />
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Code-level self-modification */}
      <div className="rounded-xl border border-fuchsia-500/30 bg-fuchsia-950/10 p-4">
        <div className="flex items-center gap-2 mb-2">
          <p className="text-xs font-semibold text-fuchsia-300">Code-Level Self-Modification</p>
          <Badge label="Track 2 · Role Generation" color="fuchsia" />
        </div>
        <div className="grid grid-cols-2 gap-4 text-[11px]">
          <div>
            <p className="text-slate-400 mb-1">Dynamic roles created by SelfEvolve</p>
            <p className="text-fuchsia-300 text-2xl font-bold">{summary?.totals?.dynamic_roles ?? 0}</p>
            <p className="text-slate-600 mt-0.5">written to dynamic_roles.json</p>
          </div>
          <div>
            <p className="text-slate-400 mb-1">Role discoveries across all runs</p>
            <p className="text-fuchsia-300 text-2xl font-bold">{summary?.totals?.role_discoveries ?? 0}</p>
            <p className="text-slate-600 mt-0.5">new specialist types invented</p>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main page
// ─────────────────────────────────────────────────────────────────────────────

const TABS = [
  { id: "overview",   label: "Overview",        icon: "📊" },
  { id: "bus",        label: "P2P Message Bus",  icon: "📡" },
  { id: "roles",      label: "Dynamic Roles",   icon: "🌿" },
  { id: "evolution",  label: "Self-Evolution",  icon: "🧠" },
];

export default function Level5Page({ onNavigate }) {
  const { activeProject } = useProject();
  const [tab, setTab] = useState("overview");
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selectedRun, setSelectedRun] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async (quiet = false) => {
    if (!activeProject) return;
    if (!quiet) setLoading(true);
    else setRefreshing(true);
    setError(null);
    try {
      const data = await fetchLevel5Summary(activeProject.id);
      setSummary(data);
    } catch {
      setError("Failed to load Level 5 data.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [activeProject]);

  useEffect(() => { load(); }, [load]);

  // Refresh every 8s while any run is still going. "Going" means anything
  // except finished or waiting for a human. Listing the busy statuses one by
  // one missed some (testing, debating_round_2, recovering_attempt_1, ...).
  useEffect(() => {
    const hasActiveRun = summary?.recent_runs?.some(
      (r) => !["completed", "failed", "awaiting_human"].includes(r.status)
    );
    if (!hasActiveRun) return;
    const t = setInterval(() => load(true), 8000);
    return () => clearInterval(t);
  }, [summary, load]);

  if (!activeProject) {
    return (
      <div className="p-6 flex flex-col items-center justify-center h-64 text-slate-500">
        <p className="text-4xl mb-3">🚀</p>
        <p className="text-sm mb-2">Select a project to view its Level 5 activity.</p>
        <button
          onClick={() => onNavigate?.("projects")}
          className="text-xs text-sky-400 hover:underline mt-1"
        >
          Go to Projects →
        </button>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-start justify-between mb-5">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <h2 className="text-lg font-semibold text-slate-100">Level 5 Tracker</h2>
            <Badge label="Live data" color="emerald" />
            {refreshing && <span className="text-[10px] text-slate-500 animate-pulse">Refreshing…</span>}
          </div>
          <p className="text-xs text-slate-500">
            Real activity from <span className="text-emerald-400">{activeProject.name}</span>
          </p>
        </div>
        <button
          onClick={() => load()}
          disabled={loading}
          className="text-[11px] border border-slate-700 rounded-lg px-3 py-1.5 text-slate-400 hover:text-slate-200 hover:border-slate-600 transition-colors disabled:opacity-40"
        >
          ↻ Refresh
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 border-b border-slate-800">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-t-lg border-b-2 transition-colors
              ${tab === t.id
                ? "border-sky-500 text-sky-300 bg-sky-950/20"
                : "border-transparent text-slate-500 hover:text-slate-300 hover:bg-slate-800/40"}`}
          >
            <span>{t.icon}</span> {t.label}
          </button>
        ))}
      </div>

      {/* Content */}
      {loading ? (
        <Spinner />
      ) : error ? (
        <p className="text-sm text-rose-400">{error}</p>
      ) : (
        <>
          {tab === "overview"  && <OverviewTab  summary={summary} onSelectRun={setSelectedRun} selectedRun={selectedRun} />}
          {tab === "bus"       && <BusTab       summary={summary} />}
          {tab === "roles"     && <DynamicRolesTab summary={summary} />}
          {tab === "evolution" && <SelfEvolutionTab summary={summary} />}
        </>
      )}
    </div>
  );
}
