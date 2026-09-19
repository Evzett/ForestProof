/* Профиль. KAN-78.

   Три вещи, которые человек должен мочь сделать со своей учётной
   записью, не обращаясь к администратору: посмотреть, что ему открыто,
   поменять имя и цвет аватара, сменить пароль.

   Четвёртой — сменить себе роль — здесь нет и быть не может: роль
   выдаётся, а не выбирается. Форма, в которой поле роли доступно
   владельцу записи, — это не профиль, а раздача прав.

   Свои контуры и расчёты показаны тут же: «что я успел сделать» —
   вопрос к профилю, и гонять за ответом в каталог незачем. */

import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { PageHead } from "../../components/AppShell";
import { Avatar } from "../../components/TopBar";
import { Card, formatArea, formatNumber, plural } from "../../components/ui";
import { useSession } from "../../data/session";
import {
  changePassword,
  deleteContour,
  getCalculations,
  getContours,
  getPalette,
  publishContour,
  updateProfile,
} from "../../api";
import type { JournalEntry, SavedContour } from "../../api";
import "./Profile.css";

export default function Profile() {
  const { session, ready, refresh } = useSession();

  const [colors, setColors] = useState<string[]>([]);
  const [name, setName] = useState("");
  const [color, setColor] = useState<string | null>(null);
  const [saved, setSaved] = useState("");
  const [profileError, setProfileError] = useState("");

  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [passNote, setPassNote] = useState("");
  const [passError, setPassError] = useState("");

  const [contours, setContours] = useState<SavedContour[]>([]);
  const [calcs, setCalcs] = useState<JournalEntry[]>([]);

  useEffect(() => {
    setName(session.display_name ?? "");
    setColor(session.avatar?.color ?? null);
  }, [session.display_name, session.avatar?.color]);

  useEffect(() => {
    if (!session.authenticated) return;
    getPalette()
      .then((r) => setColors(r.colors))
      .catch(() => setColors([]));
    getContours(true)
      .then((r) => setContours(r.contours))
      .catch(() => setContours([]));
    getCalculations(true)
      .then((r) => setCalcs(r.calculations))
      .catch(() => setCalcs([]));
  }, [session.authenticated, session.login]);

  const stats = useMemo(() => {
    const published = contours.filter((c) => c.published).length;
    const area = contours.reduce((sum, c) => sum + c.area_ha, 0);
    return { published, area };
  }, [contours]);

  if (!ready) return null;

  if (!session.authenticated) {
    return (
      <>
        <PageHead
          title="Профиль"
          subtitle="Страница своей учётной записи. Сейчас сервис открыт наблюдателем — входа нет, и показывать нечего."
        />
        <Card title="Вы смотрите сервис без входа">
          <p className="pf-note">
            Наблюдателю открыт просмотр участков, расчётов и журнала. Чтобы загрузить свой
            контур и запустить расчёт, нужен вход — кнопка в верхней панели справа. Там же
            регистрация: новая учётная запись получает роль аналитика.
          </p>
        </Card>
      </>
    );
  }

  const saveProfile = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaved("");
    setProfileError("");
    try {
      const value = await updateProfile({
        display_name: name.trim(),
        ...(color ? { avatar_color: color } : {}),
      });
      refresh(value);
      setSaved("Сохранено.");
    } catch (err) {
      setProfileError(err instanceof Error ? err.message : "Сохранить не удалось.");
    }
  };

  const savePassword = async (event: React.FormEvent) => {
    event.preventDefault();
    setPassNote("");
    setPassError("");
    try {
      await changePassword(current, next);
      setCurrent("");
      setNext("");
      setPassNote("Пароль изменён. Текущий вход остаётся действительным.");
    } catch (err) {
      setPassError(err instanceof Error ? err.message : "Сменить пароль не удалось.");
    }
  };

  const togglePublish = async (contour: SavedContour) => {
    try {
      const updated = await publishContour(contour.contour_id, !contour.published);
      setContours((list) =>
        list.map((c) => (c.contour_id === contour.contour_id ? { ...c, ...updated } : c))
      );
    } catch {
      /* отказ придёт с сервера и уже показан там, где это важно */
    }
  };

  const handleDeleteContour = async (contour: SavedContour) => {
    if (
      window.confirm(
        `Вы действительно хотите удалить контур «${contour.name}»? Это действие нельзя отменить.`
      )
    ) {
      try {
        await deleteContour(contour.contour_id);
        setContours((list) => list.filter((c) => c.contour_id !== contour.contour_id));
      } catch (err) {
        alert(err instanceof Error ? err.message : "Не удалось удалить контур.");
      }
    }
  };

  return (
    <>
      <PageHead
        title="Профиль"
        subtitle="Учётная запись, права роли и то, что за вами числится."
      />

      <div className="pf-grid">
        <Card title="Учётная запись" className="pf-card">
          <div className="pf-head">
            <Avatar
              initials={session.avatar?.initials ?? "?"}
              color={color ?? session.avatar?.color ?? "#2f6b4f"}
              size={64}
            />
            <div>
              <b className="pf-name">{session.display_name}</b>
              <span className="pf-login">{session.login}</span>
              <span className="pf-role">{session.role_label}</span>
            </div>
          </div>
          <p className="pf-note">{session.role_note}</p>

          <form onSubmit={saveProfile}>
            <label className="pf-field">
              <span>как вас показывать</span>
              <input value={name} onChange={(e) => setName(e.target.value)} required />
            </label>

            <div className="pf-field">
              <span>цвет аватара</span>
              <div className="pf-colors">
                {colors.map((c) => (
                  <button
                    key={c}
                    type="button"
                    className={c === color ? "pf-color pf-color--on" : "pf-color"}
                    style={{ background: c }}
                    onClick={() => setColor(c)}
                    aria-label={`цвет ${c}`}
                  />
                ))}
              </div>
            </div>

            <div className="pf-actions">
              <button className="btn btn--dark btn--inline" type="submit">
                <span>Сохранить</span>
              </button>
              {saved && <span className="pf-ok">{saved}</span>}
              {profileError && <span className="pf-err">{profileError}</span>}
            </div>
          </form>
        </Card>

        <Card title="Пароль" className="pf-card">
          <p className="pf-note">
            Текущий пароль спрашивается обязательно: токен входа живёт сутки, и одного
            украденного токена не должно хватать, чтобы забрать учётную запись насовсем.
          </p>
          <form onSubmit={savePassword}>
            <label className="pf-field">
              <span>текущий пароль</span>
              <input
                type="password"
                value={current}
                onChange={(e) => setCurrent(e.target.value)}
                autoComplete="current-password"
                required
              />
            </label>
            <label className="pf-field">
              <span>новый пароль · не короче восьми символов</span>
              <input
                type="password"
                value={next}
                onChange={(e) => setNext(e.target.value)}
                autoComplete="new-password"
                minLength={8}
                required
              />
            </label>
            <div className="pf-actions">
              <button className="btn btn--dark btn--inline" type="submit">
                <span>Сменить пароль</span>
              </button>
              {passNote && <span className="pf-ok">{passNote}</span>}
              {passError && <span className="pf-err">{passError}</span>}
            </div>
          </form>
        </Card>

        <Card
          title="Мои контуры"
          note={`${contours.length} ${plural(contours.length, ["контур", "контура", "контуров"])} · ${formatArea(stats.area)} га · опубликовано ${stats.published}`}
          className="pf-card pf-card--wide"
        >
          {contours.length === 0 ? (
            <p className="pf-note">
              Пока ничего не загружено. Кнопка «Задать контур» в левой панели открывает мастер:
              файл, координаты, таблица или обводка по карте.
            </p>
          ) : (
            <table className="pf-table">
              <thead>
                <tr>
                  <th>контур</th>
                  <th>площадь</th>
                  <th>период</th>
                  <th>единицы</th>
                  <th>видно</th>
                  <th>действие</th>
                </tr>
              </thead>
              <tbody>
                {contours.map((c) => (
                  <tr key={c.contour_id}>
                    <td>
                      <Link to={`/app/area/${c.contour_id}`}>{c.name}</Link>
                      <span className="pf-sub">{c.source_name}</span>
                    </td>
                    <td className="tabular">{formatArea(c.area_ha)} га</td>
                    <td className="tabular">
                      {c.year_start}—{c.year_end}
                    </td>
                    <td className="tabular">
                      {/* «недоступно» и «ноль» — разные ответы (Е-05), и
                          писать прочерк вместо нуля нельзя. */}
                      {c.units === null ? "недоступно" : formatNumber(c.units)}
                    </td>
                    <td>
                      <button
                        type="button"
                        className={c.published ? "pf-pub pf-pub--on" : "pf-pub"}
                        onClick={() => togglePublish(c)}
                      >
                        {c.published ? "всем" : "только мне"}
                      </button>
                    </td>
                    <td>
                      <button
                        type="button"
                        className="pf-del"
                        onClick={() => handleDeleteContour(c)}
                        title="Удалить этот контур"
                      >
                        удалить
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        <Card
          title="Мои расчёты"
          note={`${calcs.length} ${plural(calcs.length, ["запись", "записи", "записей"])} в журнале`}
          className="pf-card pf-card--wide"
        >
          {calcs.length === 0 ? (
            <p className="pf-note">Запусков расчёта за вами пока нет.</p>
          ) : (
            <table className="pf-table">
              <thead>
                <tr>
                  <th>номер</th>
                  <th>когда</th>
                  <th>методика</th>
                  <th>хеш входа</th>
                </tr>
              </thead>
              <tbody>
                {calcs.slice(0, 20).map((c) => (
                  <tr key={c.calc_id}>
                    <td>{c.calc_id}</td>
                    <td className="tabular">
                      {new Date(c.calculated_at).toLocaleString("ru-RU")}
                    </td>
                    <td>{c.methodology_version}</td>
                    <td className="pf-hash">{c.input_hash.slice(0, 16)}…</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>
    </>
  );
}
