/**
 * SupervisionPage — full pipeline run trace for project presentations.
 *
 * Shows, for each run:
 *   1. Overview: status, duration, persona, request type
 *   2. Overseer Decision: what stages were planned, checkpoints, reasoning
 *   3. Stage-by-Stage Execution Trace: each agent's output, timing, score
 *   4. [Level 5] Debate Log: Developer ↔ Critic back-and-forth per round
 *   5. [Level 5] Recovery Log: auto test-failure fix attempts
 *   6. [Level 5] Evolved Prompts: per-agent structural instruction evolution
 *   7. Self-Evolution / Memory: ChromaDB learned patterns
 *   8. Raw JSON timeline: for technical review
 */

import { useEffect, useState } from "react";
import { useProject } from "../context/ProjectContext.jsx";
import {
  fetchEvolvedPrompts,
  fetchExecutions,
  fetchMemory,
  fetchPipelineRun,
  listPipelineRuns,
} from "../services/api.js";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STAGE_META = {
  planner:    { icon: "📋", label: "Planner",    color: "sky" },
  designer:   { icon: "🏗️",  label: "Designer",   color: "violet" },
  developer:  { icon: "💻",  label: "Developer",  color: "emerald" },
  critic:     { icon: "🔍",  label: "Critic",     color: "amber" },
  tester:     { icon: "🧪",  label: "Tester",     color: "rose" },
  self_evolve:{ icon: "🧠",  label: "Self-Evolve", color: "purple" },
  overseer:   { icon: "🤖",  label: "Overseer",   color: "indigo" },
};

const STATUS_STYLE = {
  completed: "text-emerald-400 bg-emerald-500/10 border-emerald-500/30",
  failed:    "text-rose-400 bg-rose-500/10 border-rose-500/30",
  skipped:   "text-slate-500 bg-slate-800/40 border-slate-700/30",
  learned:   "text-purple-400 bg-purple-500/10 border-purple-500/30",
  running:   "text-sky-400 bg-sky-500/10 border-sky-500/30",
};

// ---------------------------------------------------------------------------
// Shared sub-components
// ---------------------------------------------------------------------------

function SectionHeader({ icon, title, subtitle }) {
  return (
    <div className="flex items-center gap-2 mb-3">
      <span className="text-xl">{icon}</span>
      <div>
        <h3 className="text-sm font-semibold text-slate-200">{title}</h3>
        {subtitle && <p className="text-[11px] text-slate-500">{subtitle}</p>}
      </div>
    </div>
  );
}

function Badge({ children, style }) {
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${style || STATUS_STYLE.completed}`}>
      {children}
    </span>
  );
}

function ExpandToggle({ open, onToggle, label }) {
  return (
    <button
      onClick={onToggle}
      className="mt-1.5 flex items-center gap-1 text-[11px] text-slate-500 hover:text-slate-300 transition-colors"
    >
      <span>{open ? "▾" : "▸"}</span>
      {label}
    </button>
  );
}

function ScoreBar({ score, max = 10 }) {
  const pct = Math.round((score / max) * 100);
  const color = score >= 7 ? "bg-emerald-500" : score >= 5 ? "bg-amber-500" : "bg-rose-500";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 rounded-full bg-slate-700 overflow-hidden">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className={`text-xs font-bold tabular-nums ${score >= 7 ? "text-emerald-400" : score >= 5 ? "text-amber-400" : "text-rose-400"}`}>
        {score}/{max}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Overview card
// ---------------------------------------------------------------------------
function OverviewCard({ run }) {
  const started = run.created_at ? new Date(run.created_at) : null;
  const ended   = run.completed_at ? new Date(run.completed_at) : null;
  const duration = started && ended ? Math.round((ended - started) / 1000) : null;

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900/60 p-4">
      <SectionHeader icon="📌" title="Run Overview" />
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { label: "Status",   value: run.status,       badge: STATUS_STYLE[run.status] || STATUS_STYLE.running },
          { label: "Request",  value: run.request_type, badge: null },
          { label: "Persona",  value: run.persona,      badge: null },
          { label: "Duration", value: duration ? `${duration}s` : "—", badge: null },
        ].map(({ label, value, badge }) => (
          <div key={label} className="rounded-lg bg-slate-800/50 px-3 py-2">
            <p className="text-[10px] text-slate-500 uppercase tracking-wide">{label}</p>
            {badge
              ? <Badge style={badge}>{value}</Badge>
              : <p className="text-sm text-slate-200 font-medium capitalize mt-0.5">{value || "—"}</p>
            }
          </div>
        ))}
      </div>
      <div className="mt-3 rounded-md bg-slate-800/40 px-3 py-2">
        <p className="text-[10px] text-slate-500 uppercase tracking-wide mb-1">Request</p>
        <p className="text-xs text-slate-300 leading-relaxed">{run.feature_description}</p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Overseer card
// ---------------------------------------------------------------------------
function OverseerCard({ plan }) {
  if (!plan) return (
    <div className="rounded-xl border border-slate-700 bg-slate-900/60 p-4">
      <SectionHeader icon="🤖" title="Overseer Decision" />
      <p className="text-xs text-slate-500">No overseer plan recorded for this run.</p>
    </div>
  );

  return (
    <div className="rounded-xl border border-indigo-700/40 bg-indigo-950/20 p-4">
      <SectionHeader icon="🤖" title="Overseer Decision"
        subtitle="AI-decided pipeline order and checkpoint strategy" />
      <div className="rounded-md bg-indigo-950/40 border border-indigo-700/30 px-3 py-2 mb-3">
        <p className="text-xs text-indigo-200 leading-relaxed italic">"{plan.reason}"</p>
      </div>
      <div className="space-y-2">
        <div>
          <p className="text-[10px] text-slate-500 uppercase tracking-wide mb-1.5">Planned Stages</p>
          <div className="flex flex-wrap gap-1.5">
            {plan.stages?.map((s, i) => {
              const meta = STAGE_META[s] || { icon: "▸", label: s };
              const hasCheckpoint = plan.checkpoints?.includes(`after_${s}`);
              return (
                <span key={s + i}
                  className="flex items-center gap-1 rounded-full bg-slate-800 border border-slate-700 px-2.5 py-0.5 text-[11px] text-slate-300">
                  <span>{meta.icon}</span>
                  {meta.label}
                  {hasCheckpoint && <span className="text-amber-400 ml-0.5" title="Human checkpoint">⏸</span>}
                </span>
              );
            })}
          </div>
        </div>
        {plan.skip?.length > 0 && (
          <p className="text-[11px] text-slate-500">
            <span className="text-slate-600">Skipped: </span>{plan.skip.join(", ")}
          </p>
        )}
        {plan.checkpoints?.length > 0 && (
          <p className="text-[11px] text-amber-400/80">
            ⏸ {plan.checkpoints.length} human checkpoint{plan.checkpoints.length > 1 ? "s" : ""}: {plan.checkpoints.join(", ")}
          </p>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Level 5: Debate Log card
// ---------------------------------------------------------------------------
function DebateLogCard({ timeline }) {
  const [open, setOpen] = useState(true);

  // Pull debate_round entries from the timeline
  const debateRounds = timeline.filter(e => e.type === "debate_round");
  const revisions    = timeline.filter(e => e.type === "revision");

  if (debateRounds.length === 0) return null;

  const finalScore = debateRounds[debateRounds.length - 1]?.score ?? 0;
  const passed = finalScore >= 7;

  return (
    <div className="rounded-xl border border-amber-700/40 bg-amber-950/10 p-4">
      <div className="flex items-center justify-between mb-1">
        <SectionHeader
          icon="⚔️"
          title="Developer ↔ Critic Debate Loop"
          subtitle={`${debateRounds.length} critic round${debateRounds.length !== 1 ? "s" : ""} · ${revisions.length} developer revision${revisions.length !== 1 ? "s" : ""}`}
        />
        <button onClick={() => setOpen(!open)}
          className="text-[11px] text-slate-500 hover:text-slate-300">
          {open ? "▲ collapse" : "▼ expand"}
        </button>
      </div>

      {/* Score progression */}
      <div className="flex items-center gap-3 mb-3">
        <p className="text-[10px] text-slate-500 uppercase tracking-wide shrink-0">Score progression</p>
        <div className="flex items-center gap-1.5 flex-wrap">
          {debateRounds.map((r, i) => (
            <div key={i} className="flex items-center gap-1">
              <span className={`text-xs font-bold tabular-nums
                ${r.score >= 7 ? "text-emerald-400" : r.score >= 5 ? "text-amber-400" : "text-rose-400"}`}>
                R{r.round}: {r.score}/10
              </span>
              {i < debateRounds.length - 1 && <span className="text-slate-600 text-[10px]">→</span>}
            </div>
          ))}
          <span className={`ml-1 text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded border
            ${passed ? "text-emerald-400 bg-emerald-500/10 border-emerald-500/30" : "text-rose-400 bg-rose-500/10 border-rose-500/30"}`}>
            {passed ? "✓ passed" : "✗ max rounds"}
          </span>
        </div>
      </div>

      {open && (
        <div className="space-y-2">
          {debateRounds.map((round, i) => {
            const revision = revisions.find(r => r.round === round.round);
            return (
              <div key={i} className="rounded-lg border border-slate-700/60 bg-slate-900/60 p-3">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-sm">🔍</span>
                    <span className="text-xs font-semibold text-slate-200">Critic Round {round.round}</span>
                    <Badge style={round.action === "pass" ? STATUS_STYLE.completed : "text-amber-400 bg-amber-500/10 border-amber-500/30"}>
                      {round.action === "pass" ? "passed" : "revise"}
                    </Badge>
                  </div>
                  <span className="text-[10px] text-slate-500">{round.time}s</span>
                </div>
                <ScoreBar score={round.score} />
                {round.critique && (
                  <p className="mt-2 text-[11px] text-slate-300 leading-relaxed bg-amber-950/20 rounded p-2 border border-amber-700/20">
                    {round.critique}
                  </p>
                )}
                {revision && (
                  <div className="mt-2 flex items-center gap-2 text-[11px] text-emerald-300">
                    <span>💻</span>
                    <span>Developer revised in response ({revision.time}s)</span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Level 5: Recovery Log card
// ---------------------------------------------------------------------------
function RecoveryLogCard({ timeline }) {
  const [open, setOpen] = useState(true);

  const recoveries = timeline.filter(e => e.type === "recovery");
  const retryTests = timeline.filter(e => e.type === "test_attempt");

  if (recoveries.length === 0) return null;

  const lastTest = retryTests[retryTests.length - 1];
  const recovered = lastTest?.status === "completed";

  return (
    <div className={`rounded-xl border p-4 ${recovered ? "border-emerald-700/40 bg-emerald-950/10" : "border-rose-700/40 bg-rose-950/10"}`}>
      <div className="flex items-center justify-between mb-1">
        <SectionHeader
          icon="🔄"
          title="Auto Test-Failure Recovery"
          subtitle={`${recoveries.length} autonomous fix attempt${recoveries.length !== 1 ? "s" : ""} — system self-healed without human intervention`}
        />
        <button onClick={() => setOpen(!open)}
          className="text-[11px] text-slate-500 hover:text-slate-300">
          {open ? "▲ collapse" : "▼ expand"}
        </button>
      </div>

      <div className="flex items-center gap-3 mb-3">
        <p className="text-[10px] text-slate-500 uppercase tracking-wide shrink-0">Recovery outcome</p>
        <Badge style={recovered ? STATUS_STYLE.completed : STATUS_STYLE.failed}>
          {recovered ? "✓ tests eventually passed" : "✗ recovery exhausted"}
        </Badge>
      </div>

      {open && (
        <div className="space-y-2">
          {recoveries.map((rec, i) => {
            const nextTest = retryTests.find(t => t.attempt === rec.attempt + 1);
            return (
              <div key={i} className="rounded-lg border border-slate-700/60 bg-slate-900/60 p-3">
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-2">
                    <span className="text-sm">🔄</span>
                    <span className="text-xs font-semibold text-slate-200">Recovery Attempt {rec.attempt}</span>
                  </div>
                  <span className="text-[10px] text-slate-500">{rec.time}s</span>
                </div>
                <p className="text-[11px] text-slate-400">
                  Developer analysed test failures and rewrote the code autonomously.
                </p>
                {nextTest && (
                  <div className={`mt-2 flex items-center gap-2 text-[11px] font-medium
                    ${nextTest.status === "completed" ? "text-emerald-400" : "text-rose-400"}`}>
                    <span>🧪</span>
                    <span>
                      Re-test attempt {nextTest.attempt}: {nextTest.status === "completed" ? "✓ passed" : "✗ still failing"}
                      {nextTest.time && ` (${nextTest.time}s)`}
                    </span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Level 5: Sub-Agent Spawning card
// ---------------------------------------------------------------------------
function SubAgentCard({ timeline }) {
  const [open, setOpen] = useState(true);
  const spawnEvents = timeline.filter(e => e.type === "sub_agent_spawn" || e.type === "sub_agent_result");
  const spawnDecision = spawnEvents.find(e => e.event === "spawn_decision");
  const agentResults = spawnEvents.filter(e => e.type === "sub_agent_result");
  const fallback = spawnEvents.find(e => e.event === "spawn_fallback");

  if (!spawnDecision) return null;

  const roleColors = {
    database: "border-blue-500/30 text-blue-400 bg-blue-500/10",
    auth: "border-purple-500/30 text-purple-400 bg-purple-500/10",
    cache: "border-yellow-500/30 text-yellow-400 bg-yellow-500/10",
    api: "border-green-500/30 text-green-400 bg-green-500/10",
    notification: "border-orange-500/30 text-orange-400 bg-orange-500/10",
    storage: "border-pink-500/30 text-pink-400 bg-pink-500/10",
    general: "border-slate-500/30 text-slate-400 bg-slate-500/10",
  };

  return (
    <div className="rounded-xl border border-indigo-700/40 bg-indigo-950/10 p-4">
      <div className="flex items-center justify-between mb-1">
        <SectionHeader
          icon="🤖"
          title="Sub-Agent Spawning"
          subtitle={`${agentResults.length} specialist agent${agentResults.length !== 1 ? "s" : ""} spawned dynamically — ${spawnDecision.task_count || 0} tasks, ${(spawnDecision.roles || []).length} specialist roles`}
        />
        <button onClick={() => setOpen(!open)}
          className="text-[11px] text-slate-500 hover:text-slate-300">
          {open ? "▲ collapse" : "▼ expand"}
        </button>
      </div>

      {open && (
        <div className="space-y-3 mt-3">
          {/* Spawn decision banner */}
          <div className="rounded-lg border border-indigo-500/30 bg-indigo-500/10 p-3 text-sm">
            <p className="font-semibold text-indigo-300 mb-1">⚡ Spawn Decision</p>
            <p className="text-indigo-200 text-xs">{spawnDecision.reason}</p>
            <div className="flex flex-wrap gap-2 mt-2">
              {(spawnDecision.roles || []).map(role => (
                <span key={role} className={`px-2 py-0.5 rounded border text-[10px] font-semibold uppercase tracking-wide ${roleColors[role] || roleColors.general}`}>
                  {role}
                </span>
              ))}
            </div>
          </div>

          {fallback && (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-300">
              ⚠️ All sub-agents failed — fell back to standard developer agent
            </div>
          )}

          {/* Per-agent results */}
          {agentResults.length > 0 && (
            <div>
              <p className="text-[10px] text-slate-500 uppercase tracking-wide mb-2">Spawned Agents</p>
              <div className="space-y-2">
                {agentResults.map((agent, i) => (
                  <div key={i} className="rounded-lg border border-slate-700/50 bg-slate-800/40 p-3">
                    <div className="flex items-center justify-between mb-1">
                      <span className={`px-1.5 py-0.5 rounded border text-[10px] font-semibold uppercase tracking-wide ${roleColors[agent.role] || roleColors.general}`}>
                        {agent.label || agent.role}
                      </span>
                      <span className={`text-xs font-semibold ${agent.success ? "text-emerald-400" : "text-rose-400"}`}>
                        {agent.success ? "✓ success" : "✗ failed"}
                      </span>
                    </div>
                    <p className="text-xs text-slate-400 mt-1">{agent.task}</p>
                    {agent.success && (
                      <p className="text-[10px] text-slate-500 mt-1">{agent.code_length} chars generated</p>
                    )}
                    {agent.error && (
                      <p className="text-[10px] text-rose-400 mt-1">{agent.error}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          <p className="text-[10px] text-slate-500 italic">
            Specialist agents ran concurrently; outputs were merged by a Composer agent into a single module.
          </p>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Level 5: Evolved Prompts card
// ---------------------------------------------------------------------------
function EvolvedPromptsCard({ evolvedPrompts }) {
  const [openAgents, setOpenAgents] = useState({});

  if (!evolvedPrompts || evolvedPrompts.total_instructions === 0) {
    return (
      <div className="rounded-xl border border-emerald-700/30 bg-emerald-950/10 p-4">
        <SectionHeader
          icon="🧬"
          title="Structural Prompt Evolution"
          subtitle="Level 5: per-agent instructions written by self-evolve after each run"
        />
        <p className="text-xs text-slate-500">
          No evolved instructions yet. Run a pipeline to start structural self-improvement.
        </p>
      </div>
    );
  }

  const agents = evolvedPrompts.agents || {};
  const agentNames = Object.keys(agents).filter(k => agents[k]?.length > 0);

  return (
    <div className="rounded-xl border border-emerald-700/40 bg-emerald-950/10 p-4">
      <SectionHeader
        icon="🧬"
        title="Structural Prompt Evolution"
        subtitle={`${evolvedPrompts.total_instructions} instruction${evolvedPrompts.total_instructions !== 1 ? "s" : ""} written across ${agentNames.length} agent${agentNames.length !== 1 ? "s" : ""} — these are injected directly into agent prompts on every run`}
      />

      <div className="mb-3 p-2 rounded-md bg-emerald-950/30 border border-emerald-700/30">
        <p className="text-[11px] text-emerald-200 leading-relaxed">
          Unlike ChromaDB context retrieval (which provides hints), these instructions are prepended
          as structural directives — the agents' behaviour permanently changes with each run.
        </p>
      </div>

      <div className="space-y-2">
        {agentNames.map(agent => {
          const meta = STAGE_META[agent] || { icon: "▸", label: agent };
          const instructions = agents[agent] || [];
          const isOpen = openAgents[agent];
          return (
            <div key={agent} className="rounded-lg border border-slate-700/60 bg-slate-900/60 p-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-sm">{meta.icon}</span>
                  <span className="text-xs font-semibold text-slate-200 capitalize">{meta.label || agent}</span>
                  <span className="text-[10px] text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 rounded-full px-1.5 py-0.5">
                    {instructions.length} instruction{instructions.length !== 1 ? "s" : ""}
                  </span>
                </div>
                <button
                  onClick={() => setOpenAgents(prev => ({ ...prev, [agent]: !prev[agent] }))}
                  className="text-[11px] text-slate-500 hover:text-slate-300">
                  {isOpen ? "▲" : "▼"}
                </button>
              </div>
              {isOpen && (
                <div className="mt-2 space-y-1.5">
                  {instructions.map((instr, i) => (
                    <div key={i} className="rounded-md bg-emerald-950/30 border border-emerald-700/20 px-3 py-2">
                      <p className="text-[11px] text-emerald-200 leading-relaxed">{instr}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stage trace card (main timeline)
// ---------------------------------------------------------------------------
function StageTraceCard({ entry, run, executions }) {
  const [expanded, setExpanded] = useState(false);

  // Skip debate/recovery internal entries from the main trace
  if (["debate_round", "revision", "recovery", "test_attempt"].includes(entry.type)) {
    return null;
  }

  const agentKey = entry.agent
    ?.replace("(retrigger)", "")
    .replace("(team)", "")
    .replace("(plan)", "")
    .replace("(code)", "")
    .replace("(repro)", "")
    .replace("(validate)", "");

  const meta = STAGE_META[agentKey] || { icon: "▸", label: entry.agent, color: "slate" };
  const statusStyle = STATUS_STYLE[entry.status] || STATUS_STYLE.running;

  const exec = executions.find((e) => {
    const normalised = e.agent_name
      ?.replace("(retrigger)", "")
      .replace("(team)", "")
      .replace("(plan)", "")
      .replace("(code)", "")
      .replace("(repro)", "")
      .replace("(validate)", "");
    return normalised === agentKey;
  });

  const renderOutput = () => {
    switch (agentKey) {
      case "planner": {
        const tasks = run.planned_tasks || [];
        if (!tasks.length) return <p className="text-xs text-slate-500">No tasks recorded.</p>;
        return (
          <div className="space-y-1">
            <p className="text-[11px] text-slate-400">{tasks.length} task{tasks.length !== 1 ? "s" : ""} created:</p>
            {tasks.map((t, i) => (
              <div key={i} className="flex items-start gap-2 text-xs text-slate-300">
                <span className={`mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-[9px] font-bold uppercase
                  ${t.priority === "high" ? "bg-rose-500/20 text-rose-400"
                    : t.priority === "medium" ? "bg-amber-500/20 text-amber-400"
                    : "bg-slate-700 text-slate-400"}`}>
                  {t.priority}
                </span>
                <span>{t.description}</span>
              </div>
            ))}
          </div>
        );
      }
      case "designer": {
        const design = run.design_artifact;
        if (!design) return <p className="text-xs text-slate-500">No design artifact recorded.</p>;
        return (
          <pre className="text-[11px] text-violet-200 whitespace-pre-wrap font-mono leading-relaxed bg-violet-950/30 rounded-md p-2 max-h-48 overflow-y-auto">
            {design}
          </pre>
        );
      }
      case "developer": {
        const code = run.generated_code || "";
        if (!code) return <p className="text-xs text-slate-500">No code recorded.</p>;
        const lines = code.split("\n");
        const preview = lines.slice(0, 25).join("\n");
        const truncated = lines.length > 25;
        return (
          <div>
            <p className="text-[11px] text-slate-400 mb-1">{lines.length} lines generated (after debate refinement):</p>
            <pre className="text-[11px] text-emerald-200 font-mono bg-slate-950 rounded-md p-2 overflow-x-auto max-h-48 overflow-y-auto">
              {preview}{truncated ? `\n… (+${lines.length - 25} more lines)` : ""}
            </pre>
          </div>
        );
      }
      case "critic": {
        const score = entry.score ?? exec?.output_payload?.score;
        const critique = exec?.output_payload?.critique;
        return (
          <div className="space-y-1.5">
            {score !== undefined && (
              <div className="flex items-center gap-2">
                <p className="text-[11px] text-slate-400">Quality score:</p>
                <div className="flex items-center gap-1">
                  {Array.from({ length: 10 }).map((_, i) => (
                    <div key={i} className={`h-1.5 w-3 rounded-sm ${i < score ? "bg-amber-400" : "bg-slate-700"}`} />
                  ))}
                  <span className="text-xs text-amber-400 font-bold ml-1">{score}/10</span>
                </div>
              </div>
            )}
            {critique && (
              <p className="text-[11px] text-slate-300 leading-relaxed bg-amber-950/20 rounded-md p-2 border border-amber-700/20">
                {critique}
              </p>
            )}
            {!score && !critique && (
              <p className="text-xs text-slate-500">Critic ran — improvements applied silently.</p>
            )}
          </div>
        );
      }
      case "tester": {
        const tr = run.test_result;
        if (!tr || !Object.keys(tr).length)
          return <p className="text-xs text-slate-500">No test result recorded.</p>;
        return (
          <div className="space-y-1.5">
            <div className="flex items-center gap-3">
              <Badge style={tr.status === "pass" ? STATUS_STYLE.completed : STATUS_STYLE.failed}>
                {tr.status === "pass" ? "✓ Tests passed" : "✗ Tests failed"}
              </Badge>
              {tr.coverage > 0 && (
                <span className="text-xs text-slate-300">Coverage: <strong>{tr.coverage}%</strong></span>
              )}
            </div>
            {tr.errors && (
              <pre className="text-[11px] text-rose-300 font-mono bg-rose-950/20 rounded-md p-2 max-h-32 overflow-y-auto whitespace-pre-wrap">
                {tr.errors.slice(0, 600)}{tr.errors.length > 600 ? "\n…" : ""}
              </pre>
            )}
          </div>
        );
      }
      case "self_evolve": {
        return (
          <div className="rounded-md bg-purple-950/30 border border-purple-700/30 p-2">
            <p className="text-[11px] text-purple-300">
              💡 A new instruction was extracted and stored in vector memory AND routed to specific
              agent prompt files. Future runs will structurally change their behaviour.
            </p>
            {exec?.output_payload?.learned && (
              <p className="text-[10px] text-slate-500 mt-1">Status: stored + routed successfully</p>
            )}
          </div>
        );
      }
      default:
        return <p className="text-xs text-slate-500">No detailed output available.</p>;
    }
  };

  const isTeamOrRetrigger = entry.agent?.includes("(team)") || entry.agent?.includes("(retrigger)");

  return (
    <div className="relative pl-6 pb-4">
      <div className="absolute left-[7px] top-6 bottom-0 w-px bg-slate-800" />
      <div className={`absolute left-0 top-1.5 h-3.5 w-3.5 rounded-full border-2 flex items-center justify-center
        ${entry.status === "completed" || entry.status === "learned"
          ? "border-emerald-500 bg-emerald-950"
          : entry.status === "failed"
          ? "border-rose-500 bg-rose-950"
          : entry.status === "skipped"
          ? "border-slate-600 bg-slate-900"
          : "border-sky-500 bg-sky-950"
        }`}
      />
      <div className="rounded-lg border border-slate-700/60 bg-slate-900/60 p-3">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="text-base leading-none">{meta.icon}</span>
            <div>
              <div className="flex items-center gap-1.5">
                <span className="text-sm font-semibold text-slate-100">{meta.label}</span>
                {isTeamOrRetrigger && (
                  <span className="text-[9px] text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded px-1 py-0.5">team</span>
                )}
              </div>
              {entry.time && <p className="text-[10px] text-slate-500">{entry.time}s</p>}
            </div>
          </div>
          <Badge style={statusStyle}>{entry.status}</Badge>
        </div>
        {entry.error && (
          <p className="mt-2 text-[11px] text-rose-300 font-mono bg-rose-950/20 rounded p-1.5">
            {entry.error}
          </p>
        )}
        {entry.status !== "failed" && entry.status !== "skipped" && (
          <>
            <ExpandToggle open={expanded} onToggle={() => setExpanded(!expanded)}
              label={expanded ? "Hide output" : "Show output"} />
            {expanded && (
              <div className="mt-2 border-t border-slate-700/40 pt-2">{renderOutput()}</div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

// Checkpoint event in trace
function CheckpointCard({ checkpoint_stage, checkpoint_prompt }) {
  if (!checkpoint_stage) return null;
  const stageName = checkpoint_stage.replace("after_", "");
  const meta = STAGE_META[stageName] || { label: stageName };
  return (
    <div className="relative pl-6 pb-4">
      <div className="absolute left-0 top-1.5 h-3.5 w-3.5 rounded-full border-2 border-amber-500 bg-amber-950 flex items-center justify-center">
        <span className="text-[7px]">⏸</span>
      </div>
      <div className="absolute left-[7px] top-6 bottom-0 w-px bg-slate-800" />
      <div className="rounded-lg border border-amber-700/40 bg-amber-950/20 p-3">
        <div className="flex items-center gap-2 mb-1.5">
          <span className="text-sm">⏸</span>
          <span className="text-sm font-semibold text-amber-200">Human Checkpoint</span>
          <span className="text-[10px] text-amber-400/60">after {meta.label}</span>
        </div>
        {checkpoint_prompt && (
          <p className="text-[11px] text-slate-300 leading-relaxed whitespace-pre-wrap">
            {checkpoint_prompt}
          </p>
        )}
      </div>
    </div>
  );
}

// Evolution log (ChromaDB)
function EvolutionLog({ memoryEntries }) {
  const learned  = memoryEntries.filter(e => e.metadata?.type === "learned_instruction");
  const features = memoryEntries.filter(e => e.metadata?.type === "feature");
  const code     = memoryEntries.filter(e => e.metadata?.type === "code");

  return (
    <div className="rounded-xl border border-purple-700/40 bg-purple-950/20 p-4">
      <SectionHeader
        icon="🧠"
        title="Vector Memory Log"
        subtitle="ChromaDB learned patterns — used for context retrieval on future runs"
      />
      {memoryEntries.length === 0 ? (
        <p className="text-xs text-slate-500">No memory entries found for this project yet.</p>
      ) : (
        <div className="space-y-3">
          {learned.length > 0 && (
            <div>
              <p className="text-[10px] text-purple-400 uppercase tracking-wide font-semibold mb-2">
                💡 Learned Instructions ({learned.length})
              </p>
              <div className="space-y-1.5">
                {learned.map((e) => (
                  <div key={e.id} className="rounded-md bg-purple-950/40 border border-purple-700/30 px-3 py-2">
                    <p className="text-[11px] text-purple-200 leading-relaxed">{e.document}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
          <div className="flex gap-4 text-[11px] text-slate-400 border-t border-slate-700/40 pt-3">
            <span>📄 {features.length} feature description{features.length !== 1 ? "s" : ""} stored</span>
            <span>💻 {code.length} code snippet{code.length !== 1 ? "s" : ""} stored</span>
            {learned.length > 0 && (
              <span className="text-purple-400">🧠 {learned.length} learned pattern{learned.length !== 1 ? "s" : ""}</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// Raw timeline
function RawTimelineCard({ timeline }) {
  const [open, setOpen] = useState(false);
  if (!timeline.length) return null;
  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900/60 p-4">
      <button onClick={() => setOpen(!open)} className="flex items-center gap-2 w-full text-left">
        <span className="text-base">🗂️</span>
        <span className="text-sm font-semibold text-slate-300">Raw Execution Log</span>
        <span className="ml-auto text-xs text-slate-500">{open ? "▲ hide" : "▼ show"}</span>
      </button>
      {open && (
        <pre className="mt-3 text-[10px] text-slate-400 font-mono bg-slate-950 rounded-md p-3 overflow-x-auto max-h-64 overflow-y-auto">
          {JSON.stringify(timeline, null, 2)}
        </pre>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function SupervisionPage() {
  const { activeProject } = useProject();
  const [runs, setRuns] = useState([]);
  const [selectedRunId, setSelectedRunId] = useState(null);
  const [run, setRun] = useState(null);
  const [executions, setExecutions] = useState([]);
  const [memoryEntries, setMemoryEntries] = useState([]);
  const [evolvedPrompts, setEvolvedPrompts] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!activeProject) return;
    listPipelineRuns(activeProject.id)
      .then(setRuns)
      .catch(() => setRuns([]));
  }, [activeProject]);

  useEffect(() => {
    if (!activeProject || !selectedRunId) return;
    setLoading(true);
    Promise.all([
      fetchPipelineRun(activeProject.id, selectedRunId),
      fetchExecutions(activeProject.id, selectedRunId),
      fetchMemory(activeProject.id),
      fetchEvolvedPrompts(activeProject.id).catch(() => null),
    ])
      .then(([r, execs, mem, evolved]) => {
        setRun(r);
        setExecutions(execs);
        setMemoryEntries(mem);
        setEvolvedPrompts(evolved);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [activeProject, selectedRunId]);

  if (!activeProject) {
    return (
      <div className="p-6 flex flex-col items-center justify-center h-64 text-slate-500">
        <p className="text-4xl mb-3">🔍</p>
        <p className="text-sm">Select a project to inspect its pipeline runs.</p>
      </div>
    );
  }

  const timeline = run?.execution_timeline || [];

  // Main trace: exclude internal debate/recovery entries
  const mainTimeline = timeline.filter(
    e => !["debate_round", "revision", "recovery", "test_attempt"].includes(e.type)
  );

  // Build trace with checkpoints interspersed
  const traceWithCheckpoints = [];
  for (const entry of mainTimeline) {
    traceWithCheckpoints.push({ type: "stage", entry });
    const key = `after_${entry.agent?.replace("(plan)", "").replace("(code)", "")}`;
    if (run?.overseer_plan?.checkpoints?.includes(key)) {
      traceWithCheckpoints.push({ type: "checkpoint" });
    }
  }

  const isPaused = run?.status === "awaiting_human";

  return (
    <div className="p-6 max-w-4xl mx-auto">
      {/* Header */}
      <div className="mb-6">
        <h2 className="text-lg font-semibold text-slate-100">Run Supervisor</h2>
        <p className="text-xs text-slate-500">
          Inspect every agent decision, debate round, recovery attempt, and evolution event for{" "}
          <span className="text-emerald-400">{activeProject.name}</span>
        </p>
      </div>

      {/* Run selector */}
      <div className="mb-6 rounded-xl border border-slate-700 bg-slate-900/60 p-4">
        <label className="block text-sm font-medium text-slate-300 mb-2">
          Select a Pipeline Run to Inspect
        </label>
        <div className="flex items-center gap-3">
          <select
            className="flex-1 rounded-md border border-slate-600 bg-slate-800 px-3 py-2 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-sky-500"
            value={selectedRunId || ""}
            onChange={(e) => setSelectedRunId(e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">— choose a run —</option>
            {runs.map((r) => {
              const date = new Date(r.created_at).toLocaleString();
              return (
                <option key={r.id} value={r.id}>
                  #{r.id} · {r.status} · {r.request_type} · {date}
                </option>
              );
            })}
          </select>
          {selectedRunId && (
            <span className={`text-xs rounded-full px-3 py-1 border font-medium capitalize
              ${run?.status === "completed" ? "text-emerald-300 bg-emerald-500/10 border-emerald-500/20"
                : run?.status === "failed" ? "text-rose-300 bg-rose-500/10 border-rose-500/20"
                : run?.status === "awaiting_human" ? "text-amber-300 bg-amber-500/10 border-amber-500/20"
                : "text-sky-300 bg-sky-500/10 border-sky-500/20"}`}>
              {run?.status || "loading…"}
            </span>
          )}
        </div>
      </div>

      {loading && (
        <div className="flex items-center gap-2 text-sm text-slate-400">
          <div className="h-3 w-3 animate-spin rounded-full border-2 border-sky-400 border-t-transparent" />
          Loading trace…
        </div>
      )}

      {run && !loading && (
        <div className="space-y-5">
          {/* 1. Overview */}
          <OverviewCard run={run} />

          {/* 2. Overseer Decision */}
          <OverseerCard plan={run.overseer_plan} />

          {/* 3. Execution Trace */}
          <div className="rounded-xl border border-slate-700 bg-slate-900/60 p-4">
            <SectionHeader
              icon="⚡"
              title="Execution Trace"
              subtitle={`${mainTimeline.length} stage event${mainTimeline.length !== 1 ? "s" : ""} recorded`}
            />
            {mainTimeline.length === 0 ? (
              <p className="text-xs text-slate-500">No execution events yet.</p>
            ) : (
              <div className="mt-2">
                {traceWithCheckpoints.map((item, i) => {
                  if (item.type === "checkpoint") {
                    return (
                      <CheckpointCard
                        key={"cp-" + i}
                        checkpoint_stage={run.checkpoint_stage || ""}
                        checkpoint_prompt={run.checkpoint_prompt}
                      />
                    );
                  }
                  return (
                    <StageTraceCard
                      key={item.entry.agent + i}
                      entry={item.entry}
                      run={run}
                      executions={executions}
                    />
                  );
                })}
                {isPaused && (
                  <div className="relative pl-6">
                    <div className="absolute left-0 top-1.5 h-3.5 w-3.5 rounded-full border-2 border-amber-500 bg-amber-950 animate-pulse" />
                    <div className="rounded-lg border border-amber-700/40 bg-amber-950/20 p-3">
                      <p className="text-sm text-amber-300 font-medium">⏸ Paused — awaiting human decision</p>
                      {run.checkpoint_prompt && (
                        <p className="text-[11px] text-slate-400 mt-1 whitespace-pre-wrap">{run.checkpoint_prompt}</p>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* 4. Level 5: Sub-Agent Spawning */}
          <SubAgentCard timeline={timeline} />

          {/* 5. Level 5: Debate Log */}
          <DebateLogCard timeline={timeline} />

          {/* 6. Level 5: Recovery Log */}
          <RecoveryLogCard timeline={timeline} />

          {/* 7. Level 5: Evolved Prompts */}
          <EvolvedPromptsCard evolvedPrompts={evolvedPrompts} />

          {/* 8. Vector Memory */}
          <EvolutionLog memoryEntries={memoryEntries} />

          {/* 9. Raw JSON */}
          <RawTimelineCard timeline={timeline} />
        </div>
      )}

      {!run && !loading && selectedRunId && (
        <p className="text-xs text-slate-500">Could not load run details.</p>
      )}
    </div>
  );
}
