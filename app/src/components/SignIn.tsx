/* Вход и текущая роль. KAN-78.

   Форма входа намеренно не стоит на пути к демо: сервис открывается
   наблюдателем, и всё содержимое видно сразу. Вход предлагается ровно
   там, где начинается запись, — и объясняет, зачем он нужен, а не просто
   требует логин.

   Оформление берётся из дизайн-системы: пилюля роли построена на тех же
   токенах, что и остальные плашки, кнопки — общий `.btn`, карточка —
   общий `Card`. Собственных цветов здесь нет. */

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useSession } from "../data/session";
import "./SignIn.css";

/* ---------- Пилюля роли в боковой панели ---------- */

export function RoleBadge() {
  const { session, ready, offline, signOut } = useSession();
  const [open, setOpen] = useState(false);

  if (!ready) return null;

  if (!session.authenticated) {
    return (
      <>
        <button className="role" type="button" onClick={() => setOpen(true)}>
          <span className="role__dot" aria-hidden="true" />
          <span className="role__text">
            <b>{session.role_label}</b>
            <span>{offline ? "сервис расчёта недоступен" : "войти для расчёта"}</span>
          </span>
        </button>
        {open && <SignInDialog onClose={() => setOpen(false)} />}
      </>
    );
  }

  return (
    <div className="role role--in">
      <span className="role__dot role__dot--on" aria-hidden="true" />
      <span className="role__text">
        <b>{session.display_name}</b>
        <span>{session.role_label}</span>
      </span>
      <button className="role__out" type="button" onClick={signOut} title="Выйти">
        выйти
      </button>
    </div>
  );
}

/* ---------- Окно входа ---------- */

export function SignInDialog({
  onClose,
  reason,
}: {
  onClose: () => void;
  /** Зачем понадобился вход: показывается над формой. */
  reason?: string;
}) {
  const { signIn, offline } = useSession();
  const [loginName, setLoginName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const firstField = useRef<HTMLInputElement>(null);

  useEffect(() => {
    firstField.current?.focus();
  }, []);

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
      await signIn(loginName.trim(), password);
      onClose();
    } catch (err) {
      // Причина приходит от сервера и одинакова для неизвестного логина
      // и неверного пароля — по ответу нельзя перебрать существующие.
      setError(err instanceof Error ? err.message : "Войти не удалось.");
    } finally {
      setBusy(false);
    }
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
        <h2 className="signin__title">Вход</h2>
        <p className="signin__lead">
          {reason ??
            "Просмотр участков, расчётов и отчётов открыт без входа. Вход нужен, чтобы загрузить свой контур и запустить расчёт: у расчёта появляется владелец."}
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

        <label className="signin__field">
          <span>пароль</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
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
            <span>{busy ? "Проверяем…" : "Войти"}</span>
          </button>
          <button className="btn btn--outline btn--inline" type="button" onClick={onClose}>
            <span>Остаться наблюдателем</span>
          </button>
        </div>

        <p className="signin__note">
          Регистрации нет: учётные записи заводятся администратором заранее. Пароль хранится
          только хешем — восстановить его нельзя, можно назначить новый.
        </p>
      </form>
    </div>,
    document.body
  );
}
