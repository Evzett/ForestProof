/* Вход и регистрация. KAN-78.

   Форма намеренно не стоит на пути к демо: сервис открывается
   наблюдателем, и всё содержимое видно сразу. Вход предлагается ровно
   там, где начинается запись, — и объясняет, зачем он нужен, а не просто
   требует логин.

   Регистрация открыта и даёт роль аналитика: этого хватает, чтобы
   загрузить свой контур и посчитать его, и не хватает, чтобы тронуть
   чужое. Роли выше выдаёт администратор — в форме их нет вовсе.

   Оформление берётся из дизайн-системы: кнопки — общий `.btn`, поля и
   радиусы — общие токены. Собственных цветов здесь нет. */

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useSession } from "../data/session";
import "./SignIn.css";

type Mode = "in" | "up";

export function SignInDialog({
  onClose,
  reason,
  start = "in",
}: {
  onClose: () => void;
  /** Зачем понадобился вход: показывается над формой. */
  reason?: string;
  /** С какой вкладки открыть — вход или регистрация. */
  start?: Mode;
}) {
  const { signIn, signUp, offline } = useSession();
  const [mode, setMode] = useState<Mode>(start);
  const [loginName, setLoginName] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const firstField = useRef<HTMLInputElement>(null);

  useEffect(() => {
    firstField.current?.focus();
  }, [mode]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (mode === "in") await signIn(loginName.trim(), password);
      else await signUp(loginName.trim(), displayName.trim(), password);
      onClose();
    } catch (err) {
      // Причина приходит от сервера и одинакова для неизвестного логина
      // и неверного пароля — по ответу нельзя перебрать существующие.
      setError(err instanceof Error ? err.message : "Не удалось.");
    } finally {
      setBusy(false);
    }
  };

  const switchTo = (next: Mode) => {
    setMode(next);
    setError("");
  };

  /* Окно рисуется в корне документа, а не там, где стоит кнопка.
     Иначе оно остаётся внутри боковой панели и карточек каталога: у них
     свои слои, и никакой z-index не поднимает потомка выше соседа его
     родителя. Из-за этого окно входа уезжало под карточки на каждом
     каталоге. Портал выносит его из всех этих слоёв разом. */
  return createPortal(
    <div className="signin" role="dialog" aria-modal="true" aria-label="Вход">
      <div className="signin__back" onClick={onClose} />
      <form className="signin__card" onSubmit={submit}>
        <div className="signin__tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={mode === "in"}
            className={mode === "in" ? "signin__tab signin__tab--on" : "signin__tab"}
            onClick={() => switchTo("in")}
          >
            Вход
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === "up"}
            className={mode === "up" ? "signin__tab signin__tab--on" : "signin__tab"}
            onClick={() => switchTo("up")}
          >
            Регистрация
          </button>
        </div>

        <p className="signin__lead">
          {mode === "up"
            ? "Новая учётная запись получает роль аналитика: можно загружать свои контуры и запускать расчёты. Роли выше выдаёт администратор."
            : (reason ??
              "Просмотр участков, расчётов и отчётов открыт без входа. Вход нужен, чтобы загрузить свой контур и запустить расчёт: у расчёта появляется владелец.")}
        </p>

        {offline && (
          <p className="signin__note signin__note--warn">
            Сервис расчёта сейчас недоступен — войти не получится. Просмотр участков набора
            работает и без него.
          </p>
        )}

        <label className="signin__field">
          <span>логин</span>
          <input
            ref={firstField}
            value={loginName}
            onChange={(e) => setLoginName(e.target.value)}
            autoComplete="username"
            required
          />
        </label>

        {mode === "up" && (
          <label className="signin__field">
            <span>как вас показывать</span>
            <input
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              autoComplete="name"
              placeholder="Имя Фамилия"
              required
            />
          </label>
        )}

        <label className="signin__field">
          <span>пароль{mode === "up" ? " · не короче восьми символов" : ""}</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={mode === "up" ? "new-password" : "current-password"}
            minLength={mode === "up" ? 8 : undefined}
            required
          />
        </label>

        {error && (
          <p className="signin__note signin__note--err" role="alert">
            {error}
          </p>
        )}

        <div className="signin__actions">
          <button className="btn btn--dark btn--inline" type="submit" disabled={busy}>
            <span>
              {busy ? "Проверяем…" : mode === "up" ? "Зарегистрироваться" : "Войти"}
            </span>
          </button>
          <button className="btn btn--outline btn--inline" type="button" onClick={onClose}>
            <span>Остаться наблюдателем</span>
          </button>
        </div>

        <p className="signin__note">
          Пароль хранится только хешем — восстановить его нельзя, можно назначить новый.
          Роль в форме регистрации не выбирается: её назначает сервер.
        </p>
      </form>
    </div>,
    document.body
  );
}
