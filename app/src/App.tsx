import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import AppShell from "./components/AppShell";
import Welcome from "./pages/Welcome/Welcome";
import Overview from "./pages/Overview/Overview";
import Projects from "./pages/Projects/Projects";
import Compare from "./pages/Compare/Compare";
import Plot from "./pages/Plot/Plot";
import { Calculations, Methodology, Monitoring, Territories } from "./pages/Sections/Sections";

/* Роутинг по структуре из docs/05-frontend-user-flow.md.
   Карточка участка открывается из каталога, территорий, наблюдения
   и журнала расчётов — поэтому она отдельный роут, а не вложенная вкладка. */

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Welcome />} />
        <Route path="/app" element={<AppShell />}>
          <Route index element={<Navigate to="overview" replace />} />
          <Route path="overview" element={<Overview />} />
          <Route path="projects" element={<Projects />} />
          <Route path="compare" element={<Compare />} />
          <Route path="plot/:id" element={<Plot />} />
          <Route path="territories" element={<Territories />} />
          <Route path="monitoring" element={<Monitoring />} />
          <Route path="calculations" element={<Calculations />} />
          <Route path="methodology" element={<Methodology />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
