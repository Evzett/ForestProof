/* Верхняя панель с аватаркой. KAN-78.

   Роль переехала сюда из боковой панели. Причина простая: снизу слева
   она читалась как ещё один пункт навигации, и понять, под кем открыт
   сервис, можно было только присмотревшись. Наверху справа — место, где
   этот ответ ищут не думая.

   Аватар — буквы имени на цветном круге. Загрузки картинок нет
   намеренно: это хранилище, проверка содержимого и модерация, а узнать
   себя в списке хватает и цвета.

   Все цвета, кроме цвета аватара, — из токенов. Цвет аватара приходит с
   сервера из палитры, собранной из тех же токенов. */

import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useSession } from "../data/session";
import { SignInDialog } from "./SignIn";
import "./TopBar.css";

export function Avatar({
  initials,
  color,
  size = 34,
}: {
  initials: string;
  color: string;
  size?: number;
}) {
  return (
    <span
      className="avatar"
      style={{ background: color, width: size, height: size, fontSize: size * 0.38 }}
      aria-hidden="true"
    >
      {initials}
    </span>
  );
}

export default function TopBar() {
  const { session, ready, offline, signOut, enterDemo } = useSession();
  const [menu, setMenu] = useState(false);
  const [auth, setAuth] = useState<"in" | "up" | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  // Меню закрывается по клику мимо и по Escape. Без этого оно остаётся
  // висеть поверх страницы, по которой человек уже кликнул дальше.
  useEffect(() => {
    if (!menu) return;
    const onDown = (event: MouseEvent) => {
      if (box.current && !box.current.contains(event.target as Node)) setMenu(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenu(false);
    };
    document.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [menu]);

  const go = (to: string) => {
    setMenu(false);
    navigate(to);
  };

  return (
    <header className="topbar">
      <div className="topbar__left">
        <span className="topbar__scope">набор данных 2019—2024</span>
        {offline && ready && (
          <span className="topbar__offline" title="Расчёты недоступны, просмотр работает">
            сервис расчёта недоступен
          </span>
        )}
      </div>

      <div className="topbar__right" ref={box}>
        {!ready ? null : !session.authenticated ? (
          <>
            <button className="topbar__link" type="button" onClick={() => setAuth("up")}>
              Регистрация
            </button>
            <button className="topbar__signin" type="button" onClick={() => setAuth("in")}>
              Войти
            </button>
            {/* Наблюдатель — это роль, а не отсутствие роли: так и
                подписываем, чтобы человек понимал, что он уже внутри. */}
            <span className="topbar__role" title="Просмотр открыт без входа">
              наблюдатель
            </span>
            {/* Кнопка появляется только там, где демонстрационный режим
                есть. На проде его нет, и обещать возврат было бы враньём. */}
            {session.demo_available && (
              <button
                className="topbar__link"
                type="button"
                onClick={() => void enterDemo()}
                title="Снова открыть сервис администратором, как в демонстрации"
              >
                демо-режим
              </button>
            )}
          </>
        ) : (
          <>
            <button
              className="topbar__user"
              type="button"
              onClick={() => setMenu((v) => !v)}
              aria-expanded={menu}
              aria-haspopup="menu"
            >
              <Avatar
                initials={session.avatar?.initials ?? "?"}
                color={session.avatar?.color ?? "#2f6b4f"}
              />
              <span className="topbar__who">
                <b>{session.display_name}</b>
                <span>{session.role_label}</span>
              </span>
              <i className="topbar__chev" aria-hidden="true" />
            </button>

            {menu && (
              <div className="topbar__menu" role="menu">
                <div className="topbar__menu-head">
                  <Avatar
                    initials={session.avatar?.initials ?? "?"}
                    color={session.avatar?.color ?? "#2f6b4f"}
                    size={42}
                  />
                  <div>
                    <b>{session.display_name}</b>
                    <span>{session.login}</span>
                  </div>
                </div>
                <p className="topbar__menu-note">{session.role_note}</p>

                <button
                  className="topbar__menu-item"
                  type="button"
                  role="menuitem"
                  onClick={() => go("/app/profile")}
                >
                  Профиль
                </button>
                <button
                  className="topbar__menu-item"
                  type="button"
                  role="menuitem"
                  onClick={() => go("/app/calculations?mine=1")}
                >
                  Мои расчёты
                </button>
                {session.can.manage && (
                  <button
                    className="topbar__menu-item"
                    type="button"
                    role="menuitem"
                    onClick={() => go("/app/admin")}
                  >
                    Панель администратора
                  </button>
                )}
                <button
                  className="topbar__menu-item topbar__menu-item--out"
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setMenu(false);
                    void signOut();
                  }}
                >
                  Выйти
                </button>
              </div>
            )}
          </>
        )}
      </div>

      {auth && <SignInDialog start={auth} onClose={() => setAuth(null)} />}
    </header>
  );
}

/** Пилюля роли для мест, где нужен только знак доступа, без меню. */
export function RolePill() {
  const { session, ready } = useSession();
  if (!ready) return null;
  return (
    <Link className="rolepill" to="/app/profile" title={session.role_note}>
      {session.role_label}
    </Link>
  );
}
