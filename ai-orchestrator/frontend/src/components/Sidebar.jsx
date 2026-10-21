import { useProject } from "../context/ProjectContext.jsx";
import { setProjectPersona } from "../services/api.js";

const NAV_ITEMS = [
  { id: "projects",    label: "Projects",    icon: "🏠" },
  { id: "pipeline",    label: "Pipeline",    icon: "⚡" },
  { id: "team",        label: "Team",        icon: "👥" },
  { id: "supervision", label: "Supervision", icon: "🔍" },
  { id: "history",     label: "History",     icon: "📜" },
  { id: "analytics",   label: "Analytics",   icon: "📊" },
  { id: "tasks",       label: "Tasks",       icon: "✅" },
  { id: "memory",      label: "Memory",      icon: "🧠" },
  { id: "level5",      label: "Level 5",     icon: "🚀" },
];

const PERSONAS = ["simple", "intermediate", "expert"];

export default function Sidebar({ currentPage, onNavigate }) {
  const { activeProject, setActiveProject, persona, setPersona } = useProject();

  // Save the persona on the project only when the user picks one here.
  // (It used to be saved on every project switch, which overwrote each
  // project's own choice with whatever was selected before.)
  const choosePersona = async (choice) => {
    setPersona(choice);
    if (!activeProject) return;
    try {
      setActiveProject(await setProjectPersona(activeProject.id, choice));
    } catch {
      setPersona(activeProject.persona); // saving failed, so show the saved value again
    }
  };

  return (
    <aside className="flex flex-col w-56 min-h-screen bg-slate-950 border-r border-slate-800 px-3 py-5 shrink-0">
      {/* Logo */}
      <div className="mb-6 px-2">
        <h1 className="text-base font-bold text-slate-50 tracking-tight">Orchar</h1>
        <p className="text-[10px] text-slate-500 mt-0.5">Multi-Agentic Orchestrator</p>
      </div>

      {/* Active project badge */}
      {activeProject ? (
        <div className="mb-4 rounded-lg bg-emerald-500/10 border border-emerald-500/20 px-3 py-2">
          <p className="text-[10px] text-emerald-400 uppercase tracking-wide font-semibold">Active Project</p>
          <p className="text-xs text-emerald-200 font-medium truncate mt-0.5">{activeProject.name}</p>
          <p className="text-[10px] text-slate-500">#{activeProject.id}</p>
        </div>
      ) : (
        <div className="mb-4 rounded-lg bg-slate-800/40 border border-slate-700/40 px-3 py-2">
          <p className="text-[10px] text-slate-500">No project selected</p>
          <p className="text-[10px] text-slate-600 mt-0.5">Go to Projects →</p>
        </div>
      )}

      {/* Navigation */}
      <nav className="flex flex-col gap-1 flex-1">
        {NAV_ITEMS.map((item) => {
          const isActive = currentPage === item.id;
          const requiresProject = ["pipeline", "supervision", "history", "analytics", "tasks", "memory"].includes(item.id);  // level5 is always accessible
          const disabled = requiresProject && !activeProject;
          return (
            <button
              key={item.id}
              onClick={() => !disabled && onNavigate(item.id)}
              disabled={disabled}
              className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors text-left w-full
                ${isActive
                  ? "bg-sky-500/20 text-sky-300 font-medium"
                  : disabled
                  ? "text-slate-600 cursor-not-allowed"
                  : "text-slate-400 hover:bg-slate-800 hover:text-slate-200"
                }`}
            >
              <span className="text-base leading-none">{item.icon}</span>
              {item.label}
            </button>
          );
        })}
      </nav>

      {/* Persona switcher */}
      <div className="mt-4 pt-4 border-t border-slate-800">
        <p className="text-[10px] text-slate-500 uppercase tracking-wide px-2 mb-2">Output Mode</p>
        <div className="flex flex-col gap-1">
          {PERSONAS.map((p) => (
            <button
              key={p}
              onClick={() => choosePersona(p)}
              className={`rounded-md px-3 py-1.5 text-xs capitalize text-left transition-colors
                ${persona === p
                  ? "bg-violet-500/20 text-violet-300 font-medium"
                  : "text-slate-500 hover:text-slate-300 hover:bg-slate-800"
                }`}
            >
              {p === "simple" ? "🟢" : p === "intermediate" ? "🟡" : "🔴"} {p}
            </button>
          ))}
        </div>
      </div>
    </aside>
  );
}
