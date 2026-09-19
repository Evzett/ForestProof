import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import AppShell from "./components/AppShell";
import Welcome from "./pages/Welcome/Welcome";
import Overview from "./pages/Overview/Overview";
import Areas from "./pages/Areas/Areas";
import Compare from "./pages/Compare/Compare";
import ClaimProjects from "./pages/ClaimProjects/ClaimProjects";
import Plot from "./pages/Plot/Plot";
import Research from "./pages/Research/Research";
import { Calculations, Methodology, Monitoring } from "./pages/Sections/Sections";
import { ContourCard, Contours } from "./pages/Contours/Contours";

/* Роутинг по структуре из docs/05-frontend-user-flow.md.

   Карточка участка — отдельный роут, а не вложенная вкладка: на неё ведут
   каталог, сравнение, журнал расчётов и наблюдение, и у неё должен быть
   свой адрес, который можно отправить проверяющему.

   Старые адреса /app/projects и /app/plot/:id остались от версии с реестром
   и переадресуются: ссылки из документации и Jira не должны ломаться. */

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Welcome />} />
        <Route path="/app" element={<AppShell />}>
          <Route index element={<Navigate to="overview" replace />} />
          <Route path="overview" element={<Overview />} />
          <Route path="areas" element={<Areas />} />
          <Route path="area/:id" element={<Plot />} />
          <Route path="compare" element={<Compare />} />
          <Route path="projects" element={<ClaimProjects />} />
          <Route path="contours" element={<Contours />} />
          <Route path="contours/:id" element={<ContourCard />} />
          <Route path="calculations" element={<Calculations />} />
          <Route path="monitoring" element={<Monitoring />} />
          <Route path="research" element={<Research />} />
          <Route path="methodology" element={<Methodology />} />
          <Route path="plot/:id" element={<Navigate to="/app/areas" replace />} />
          <Route path="territories" element={<Navigate to="/app/areas" replace />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
