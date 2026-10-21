import { createContext, useContext, useEffect, useState } from "react";

const ProjectContext = createContext(null);

export function ProjectProvider({ children }) {
  const [activeProject, setActiveProject] = useState(null);
  const [persona, setPersona] = useState("intermediate");

  // Each project saves its own persona. Show that one when the project changes.
  useEffect(() => {
    setPersona(activeProject?.persona ?? "intermediate");
  }, [activeProject]);

  return (
    <ProjectContext.Provider value={{ activeProject, setActiveProject, persona, setPersona }}>
      {children}
    </ProjectContext.Provider>
  );
}

export function useProject() {
  return useContext(ProjectContext);
}
