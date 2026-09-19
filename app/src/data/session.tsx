/* Роль текущего пользователя. KAN-78.

   По умолчанию сервис открыт наблюдателем, и формы входа на пути к демо
   нет: открыл ссылку — видно всё. Вход появляется только там, где
   начинается запись: загрузка контура, запуск расчёта, удаление.

   Права здесь — подсказка для отрисовки, а не ограничение. Настоящее
   ограничение стоит на сервере: скрытая кнопка не мешает послать запрос
   мимо интерфейса. Поэтому список прав приходит с сервера, а не
   повторяется тут — иначе правила разошлись бы при первой же правке.

   Если сервис недоступен, остаёмся наблюдателем: демо по участкам
   набора работает вообще без бэкенда, и падать здесь нечему. */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { getSession, login as apiLogin, logout as apiLogout, setToken } from "../api";
import type { Session } from "../api";

const VIEWER: Session = {
  authenticated: false,
  login: null,
  display_name: null,
  role: "viewer",
  role_label: "наблюдатель",
  can: { view: true, calculate: false, upload: false, manage: false },
};

type SessionValue = {
  session: Session;
  /** Сервис ответил хотя бы раз: до этого роль ещё не выяснена. */
  ready: boolean;
  /** Бэкенд не отвечает — вход невозможен, просмотр работает. */
  offline: boolean;
  signIn: (login: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
};

const Ctx = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session>(VIEWER);
  const [ready, setReady] = useState(false);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getSession()
      .then((value) => {
        if (!cancelled) {
          setSession(value);
          setOffline(false);
        }
      })
      .catch(() => {
        // Бэкенда нет — это штатный режим демо, а не сбой: участки
        // набора посчитаны заранее и открываются без него.
        if (!cancelled) {
          setSession(VIEWER);
          setOffline(true);
        }
      })
      .finally(() => {
        if (!cancelled) setReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const signIn = useCallback(async (loginName: string, password: string) => {
    const value = await apiLogin(loginName, password);
    setToken(value.token ?? null);
    setSession(value);
    setOffline(false);
  }, []);

  const signOut = useCallback(async () => {
    try {
      await apiLogout();
    } finally {
      // Токен снимаем в любом случае: если сервер не ответил, держать
      // его у себя — значит считать себя вошедшим без оснований.
      setToken(null);
      setSession(VIEWER);
    }
  }, []);

  const value = useMemo(
    () => ({ session, ready, offline, signIn, signOut }),
    [session, ready, offline, signIn, signOut]
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSession(): SessionValue {
  const value = useContext(Ctx);
  if (value === null) throw new Error("useSession вне SessionProvider");
  return value;
}
