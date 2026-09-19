import { useState } from "react";
import type { ReactNode } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { AREAS, GENERATED_FROM } from "../data/case";
import { plural } from "./ui";
import { WizardProvider, useWizard } from "./Wizard";
import { RoleBadge, SignInDialog } from "./SignIn";
import { SessionProvider, useSession } from "../data/session";
import { ScenarioProvider } from "../data/scenario";
import "./AppShell.css";

/* Каркас приложения: постоянная навигация из шести разделов.
   Требования FR-02 — FR-04.
   Роль показана пилюлей внизу панели (KAN-78). Формы входа на пути к
   демо нет: сервис открывается наблюдателем, и всё содержимое видно
   сразу. Вход предлагается там, где начинается запись, — прежнее
   «регистрации нет» (NFR-05) принималось именно из-за риска, что форма
   входа на старте сломает защиту, и этот риск снят, а не принят.

   Раздел «Проекты» переименован в «Участки»: в наборе кейса это
   исследовательские участки, а не зарегистрированные климатические
   проекты, и называть их проектами значит подменять статус данных. */

/* Иконки — экспорт из макета, лежат в public/icons.
   Подключены CSS-маской, а не <img>: у экспортированных файлов цвет
   вшит в разметку, а маске он безразличен — цвет берётся от состояния
   пункта, и активный пункт не требует второго файла. */
const NAV = [
  { to: "/app/overview", label: "Обзор", icon: "overview" },
  { to: "/app/areas", label: "Участки", icon: "areas" },
  /* В макете иконки «Сравнения» нет — разделов у нас семь, а значков
     там шесть. Взят carbon:compare из той же библиотеки Carbon, откуда
     в макете взята «Методика», поэтому рисунок не выбивается из ряда. */
  { to: "/app/compare", label: "Сравнение", icon: "compare" },
  { to: "/app/projects", label: "Проекты", icon: "projects" },
  { to: "/app/contours", label: "Мои контуры", icon: "areas" },
  { to: "/app/calculations", label: "Расчёты", icon: "calc" },
  { to: "/app/monitoring", label: "Что изменилось", icon: "monitoring" },
  { to: "/app/research", label: "Исследование", icon: "calc" },
  { to: "/app/methodology", label: "Методика", icon: "method" },
];

/* Кнопка добавления участка. Главное действие продукта,
   поэтому доступна из любого раздела (FR-03). */
export function AddPlotButton({ className = "", label = "Задать контур" }) {
  const { open } = useWizard();
  const { session, ready } = useSession();
  const [askLogin, setAskLogin] = useState(false);

  /* Наблюдателю кнопка видна, но ведёт к объяснению, а не к мастеру.
     Прятать её нельзя: тогда непонятно, что продукт вообще это умеет,
     и непонятно, чего не хватает. Доступ всё равно закрывает сервер —
     кнопка только объясняет. */
  const allowed = !ready || session.can.upload;

  return (
    <>
      <button
        className={`add-btn ${className}`.trim()}
        type="button"
        onClick={() => (allowed ? open() : setAskLogin(true))}
      >
        <i className="ic ic--plus" aria-hidden="true" /> {label}
      </button>
      {askLogin && (
        <SignInDialog
          onClose={() => setAskLogin(false)}
          reason="Загрузка своего контура и расчёт по нему доступны аналитику: у расчёта появляется владелец, и он попадает в журнал. Просмотр участков набора остаётся открытым без входа."
        />
      )}
    </>
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
              <i className={`ic ic--${item.icon}`} aria-hidden="true" />
              {item.label}
            </NavLink>
          ))}
        </nav>

        <RoleBadge />

        <div className="sidebar__foot">
          <span>набор данных</span>
          <span className="sidebar__foot-strong">
            {AREAS.length} {plural(AREAS.length, ["участок", "участка", "участков"])} · 2019—2024
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
    <SessionProvider>
      <ScenarioProvider>
        <WizardProvider>
          <Shell />
        </WizardProvider>
      </ScenarioProvider>
    </SessionProvider>
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
