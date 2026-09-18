import type { ReactNode } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { AREAS, GENERATED_FROM } from "../data/case";
import { WizardProvider, useWizard } from "./Wizard";
import "./AppShell.css";

/* Каркас приложения: постоянная навигация из шести разделов.
   Требования FR-02 — FR-04.
   Элементов авторизации здесь нет и не появится: одно рабочее
   пространство, состояние на сервере (NFR-05).

   Раздел «Проекты» переименован в «Участки»: в наборе кейса это
   исследовательские участки, а не зарегистрированные климатические
   проекты, и называть их проектами значит подменять статус данных. */

const NAV = [
  { to: "/app/overview", label: "Обзор" },
  { to: "/app/areas", label: "Участки" },
  { to: "/app/compare", label: "Сравнение" },
  { to: "/app/calculations", label: "Расчёты" },
  { to: "/app/monitoring", label: "Наблюдение" },
  { to: "/app/methodology", label: "Методика" },
];

/* Кнопка добавления участка. Главное действие продукта,
   поэтому доступна из любого раздела (FR-03). */
export function AddPlotButton({ className = "", label = "Задать контур" }) {
  const { open } = useWizard();
  return (
    <button className={`add-btn ${className}`.trim()} type="button" onClick={() => open()}>
      <span aria-hidden="true">+</span> {label}
    </button>
  );
}

function Shell() {
  return (
    <div className="shell">
      <aside className="sidebar">
        <NavLink to="/" className="sidebar__logo">
          <span className="sidebar__brand">ForestProof</span>
          <span className="sidebar__tagline">проверка климатических проектов</span>
        </NavLink>

        <AddPlotButton className="sidebar__add" />

        <nav className="sidebar__nav">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                isActive ? "sidebar__item sidebar__item--active" : "sidebar__item"
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar__foot">
          <span>набор данных</span>
          <span className="sidebar__foot-strong">
            {AREAS.length} участка · 2019—2024
          </span>
          <span>{GENERATED_FROM}</span>
        </div>
      </aside>

      <main className="shell__main">
        <Outlet />
      </main>
    </div>
  );
}

export default function AppShell() {
  return (
    <WizardProvider>
      <Shell />
    </WizardProvider>
  );
}

/* Шапка раздела: заголовок, подпись и место под действие справа. */
export function PageHead({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
}) {
  return (
    <header className="page-head">
      <div>
        <h1 className="page-head__title">{title}</h1>
        {subtitle && <p className="page-head__sub">{subtitle}</p>}
      </div>
      {action && <div className="page-head__action">{action}</div>}
    </header>
  );
}
