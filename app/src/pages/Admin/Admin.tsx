/* Панель администратора. KAN-78.

   Раньше пункт меню был, а страницы за ним не было: роут отсутствовал,
   и «Администрирование» уводило на стартовый экран. Здесь — то, ради
   чего роль администратора вообще существует.

   Две части. Люди: кто заведён, что за ним числится, какая роль, не
   заблокирован ли, и сброс пароля. Источники: что настроено, сколько
   занимает кэш и как его почистить — когда расчёт по чужому контуру
   падает, первый вопрос именно к ним, и раньше ответ жил в логах
   контейнера.

   Удаления учётной записи здесь нет. За человеком остаются расчёты, и
   удаление оборвало бы подписи в журнале. Блокировка закрывает вход и
   сохраняет следы. */

import { useCallback, useEffect, useState } from "react";
import { PageHead } from "../../components/AppShell";
import { Avatar } from "../../components/TopBar";
import { Card, plural } from "../../components/ui";
import { useSession } from "../../data/session";
import {
  clearSourceCache,
  getRoles,
  getSources,
  getUsers,
  resetUserPassword,
  updateUser,
} from "../../api";
import type { AdminUser, RoleInfo, RoleName, SourceState } from "../../api";
import "./Admin.css";

export default function Admin() {
  const { session, ready } = useSession();

  const [users, setUsers] = useState<AdminUser[]>([]);
  const [roles, setRoles] = useState<RoleInfo[]>([]);
  const [sources, setSources] = useState<SourceState | null>(null);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [resetting, setResetting] = useState<string | null>(null);
  const [newPassword, setNewPassword] = useState("");

  const load = useCallback(() => {
    getUsers()
      .then((r) => setUsers(r.users))
      .catch((err) => setError(err instanceof Error ? err.message : "Список не загрузился."));
    getSources()
      .then(setSources)
      .catch(() => setSources(null));
  }, []);

  useEffect(() => {
    if (!session.can.manage) return;
    getRoles()
      .then((r) => setRoles(r.roles))
      .catch(() => setRoles([]));
    load();
  }, [session.can.manage, load]);

  if (!ready) return null;

  /* Отказ показывается страницей, а не пустотой: человек пришёл по
     ссылке и должен понять, почему здесь ничего нет. Настоящее
     ограничение всё равно на сервере — он ответит 403 и без этого. */
  if (!session.can.manage) {
    return (
      <>
        <PageHead
          title="Администрирование"
          subtitle="Учётные записи, роли и обслуживание источников данных."
        />
        <Card title="Раздел доступен администратору">
          <p className="ad-note">
            Ваша роль — «{session.role_label}». {session.role_note} Управление учётными
            записями в неё не входит: раздавать права может только администратор, иначе роль
            перестаёт что-либо ограничивать.
          </p>
        </Card>
      </>
    );
  }

  const changeRole = async (user: AdminUser, role: RoleName) => {
    setError("");
    setNote("");
    try {
      await updateUser(user.login, { role });
      setUsers((list) =>
        list.map((u) =>
          u.login === user.login
            ? { ...u, role, role_label: roles.find((r) => r.value === role)?.label ?? role }
            : u
        )
      );
      setNote(`Роль «${user.display_name}» изменена.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Роль не изменена.");
    }
  };

  const toggleBlock = async (user: AdminUser) => {
    setError("");
    setNote("");
    try {
      await updateUser(user.login, { blocked: !user.blocked });
      setUsers((list) =>
        list.map((u) => (u.login === user.login ? { ...u, blocked: !u.blocked } : u))
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось.");
    }
  };

  const submitReset = async (login: string) => {
    setError("");
    setNote("");
    try {
      await resetUserPassword(login, newPassword);
      setResetting(null);
      setNewPassword("");
      setNote(`Пароль для «${login}» назначен. Передайте его лично — сервис писем не шлёт.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Пароль не изменён.");
    }
  };

  const purge = async () => {
    setError("");
    try {
      const result = await clearSourceCache();
      setNote(`Кэш очищен, освобождено ${result.freed_mb} МБ.`);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось очистить кэш.");
    }
  };

  return (
    <>
      <PageHead
        title="Администрирование"
        subtitle="Учётные записи, роли и обслуживание источников данных."
      />

      {(error || note) && (
        <p className={error ? "ad-flash ad-flash--err" : "ad-flash"} role="status">
          {error || note}
        </p>
      )}

      <Card
        title="Учётные записи"
        note={`${users.length} ${plural(users.length, ["запись", "записи", "записей"])}`}
        className="ad-card"
      >
        <table className="ad-table">
          <thead>
            <tr>
              <th>кто</th>
              <th>роль</th>
              <th>контуры</th>
              <th>расчёты</th>
              <th>доступ</th>
              <th>пароль</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.login} className={user.blocked ? "ad-row--off" : undefined}>
                <td>
                  <span className="ad-who">
                    <Avatar initials={user.avatar.initials} color={user.avatar.color} size={30} />
                    <span>
                      <b>{user.display_name}</b>
                      <span className="ad-sub">{user.login}</span>
                    </span>
                  </span>
                </td>
                <td>
                  <select
                    className="ad-select"
                    value={user.role}
                    onChange={(e) => changeRole(user, e.target.value as RoleName)}
                    aria-label={`роль ${user.login}`}
                  >
                    {roles.map((r) => (
                      <option key={r.value} value={r.value}>
                        {r.label}
                      </option>
                    ))}
                  </select>
                </td>
                {/* Счётчики стоят рядом с выбором роли не для красоты:
                    перед понижением видно, сколько работы за человеком. */}
                <td className="tabular">{user.contours}</td>
                <td className="tabular">{user.calculations}</td>
                <td>
                  <button
                    type="button"
                    className={user.blocked ? "ad-flag ad-flag--off" : "ad-flag"}
                    onClick={() => toggleBlock(user)}
                    disabled={user.login === session.login}
                    title={
                      user.login === session.login
                        ? "Себя заблокировать нельзя"
                        : user.blocked
                          ? "Вернуть доступ"
                          : "Закрыть вход, сохранив расчёты"
                    }
                  >
                    {user.blocked ? "заблокирован" : "открыт"}
                  </button>
                </td>
                <td>
                  {resetting === user.login ? (
                    <span className="ad-reset">
                      <input
                        type="password"
                        value={newPassword}
                        onChange={(e) => setNewPassword(e.target.value)}
                        placeholder="новый пароль"
                        minLength={8}
                        autoFocus
                      />
                      <button
                        className="link-btn"
                        type="button"
                        onClick={() => submitReset(user.login)}
                        disabled={newPassword.length < 8}
                      >
                        назначить
                      </button>
                      <button
                        className="link-btn"
                        type="button"
                        onClick={() => {
                          setResetting(null);
                          setNewPassword("");
                        }}
                      >
                        отмена
                      </button>
                    </span>
                  ) : (
                    <button
                      className="link-btn"
                      type="button"
                      onClick={() => {
                        setResetting(user.login);
                        setNewPassword("");
                      }}
                    >
                      сбросить
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <div className="ad-roles">
          {roles.map((r) => (
            <p key={r.value}>
              <b>{r.label}</b> — {r.note}
            </p>
          ))}
        </div>
      </Card>

      <Card title="Источники данных" className="ad-card">
        {sources === null ? (
          <p className="ad-note">Состояние источников не загрузилось.</p>
        ) : (
          <>
            <table className="ad-table">
              <thead>
                <tr>
                  <th>источник</th>
                  <th>что даёт</th>
                  <th>доступ</th>
                  <th>состояние</th>
                </tr>
              </thead>
              <tbody>
                {sources.sources.map((s) => (
                  <tr key={s.name}>
                    <td>
                      <b>{s.name}</b>
                      <span className="ad-sub">{s.note}</span>
                    </td>
                    <td>{s.kind}</td>
                    <td>{s.auth}</td>
                    <td>
                      <span className={s.ready ? "ad-dot ad-dot--on" : "ad-dot"} />
                      {s.ready ? "настроен" : "не настроен"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {/* «Настроен» — это не «работает»: проверять второе значило бы
                ходить в сеть при каждом открытии панели. Говорим то,
                что знаем. */}
            <p className="ad-note">
              «Настроен» означает, что ключ на месте и запрос уйдёт. Доступность самого
              каталога здесь не проверяется — это потребовало бы обращения в сеть на каждое
              открытие страницы.
            </p>

            <div className="ad-cache">
              {sources.cache.map((c) => (
                <div key={c.path} className="ad-cache__item">
                  <b>{c.size_mb} МБ</b>
                  <span>{c.name}</span>
                </div>
              ))}
              <div className="ad-cache__item">
                <b>{sources.contour_maps.size_mb} МБ</b>
                <span>
                  карты контуров ·{" "}
                  {sources.contour_maps.count}{" "}
                  {plural(sources.contour_maps.count, ["участок", "участка", "участков"])}
                </span>
              </div>
            </div>

            <div className="ad-actions">
              <button className="btn btn--outline btn--inline" type="button" onClick={purge}>
                <span>Очистить кэш скачанного</span>
              </button>
              <span className="ad-note">
                Кэш — копия того, что лежит в сети: следующий расчёт скачает заново, потеряв
                только время. Карты уже посчитанных контуров не трогаются — иначе страницы
                сохранённых участков стали бы пустыми.
              </span>
            </div>
          </>
        )}
      </Card>
    </>
  );
}
