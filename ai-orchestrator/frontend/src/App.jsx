import { useState } from "react";
import Sidebar from "./components/Sidebar.jsx";
import { ProjectProvider } from "./context/ProjectContext.jsx";
import AnalyticsPage from "./pages/AnalyticsPage.jsx";
import HistoryPage from "./pages/HistoryPage.jsx";
import Level5Page from "./pages/Level5Page.jsx";
import MemoryPage from "./pages/MemoryPage.jsx";
import PipelinePage from "./pages/PipelinePage.jsx";
import ProjectsPage from "./pages/ProjectsPage.jsx";
import SupervisionPage from "./pages/SupervisionPage.jsx";
import TasksPage from "./pages/TasksPage.jsx";
import TeamPage from "./pages/TeamPage.jsx";

const PAGES = {
  projects:    ProjectsPage,
  pipeline:    PipelinePage,
  team:        TeamPage,
  supervision: SupervisionPage,
  history:     HistoryPage,
  analytics:   AnalyticsPage,
  tasks:       TasksPage,
  memory:      MemoryPage,
  level5:      Level5Page,
};

export default function App() {
  const [currentPage, setCurrentPage] = useState("projects");
  const PageComponent = PAGES[currentPage] || ProjectsPage;

  return (
    <ProjectProvider>
      <div className="flex min-h-screen bg-slate-950">
        <Sidebar currentPage={currentPage} onNavigate={setCurrentPage} />
        <main className="flex-1 overflow-y-auto">
          <PageComponent onNavigate={setCurrentPage} />
        </main>
      </div>
    </ProjectProvider>
  );
}
