import { Link } from "react-router-dom";
import {
  Card,
  ClaimPill,
  ConfidencePill,
  LevelPill,
  WithError,
  formatNumber,
} from "../../components/ui";
import { PageHead } from "../../components/AppShell";
import { PROJECTS } from "../../data/mock";
import "./Compare.css";

/* Сравнение проектов. Требования FR-14 — FR-17.

   Сводного балла нет и быть не может (FR-16). Групповая шапка не украшение:
   одиннадцать колонок подряд глаз всё равно суммирует в оценку, а пять групп
   читаются как пять разных вопросов.

   Цветом кодируются только уровни (FR-17). Числа остаются нейтральными:
   раскрашенная целиком таблица — это и есть сводная оценка, просто нарисованная. */

export default function Compare() {
  return (
    <>
      <PageHead
        title="Сравнение проектов"
        subtitle="Сводного рейтингового балла нет: пять групп — пять разных вопросов"
        action={<Link to="/app/projects" className="filter">← в каталог</Link>}
      />

      <div className="cmp-cards">
        {PROJECTS.map((p) => (
          <Card key={p.project_id} className="cmp-card">
            <img className="cmp-card__img" src={p.preview_path} alt="" />
            <div className="cmp-card__body">
              <b>{p.name}</b>
              <span>{formatNumber(p.area_ha)} га</span>
              <ClaimPill status={p.claim_status} />
            </div>
          </Card>
        ))}
      </div>

      <Card>
        <div className="tbl__scroll">
          <table className="tbl">
            <thead>
              <tr className="tbl__group">
                <th />
                <th colSpan={4}>Измерено</th>
                <th colSpan={2}>Риск</th>
                <th>Качество</th>
                <th>Заявлено</th>
                <th className="num">₽</th>
              </tr>
              <tr>
                <th>Проект</th>
                <th className="num">Площадь, га</th>
                <th className="num">Биомасса, т/га</th>
                <th className="num">Потери 10 л</th>
                <th className="num">Свежие, га</th>
                <th>Пожарн. эксп.</th>
                <th>Уязвимость</th>
                <th>Доверие</th>
                <th>Сверка</th>
                <th className="num">₽/га</th>
              </tr>
            </thead>
            <tbody>
              {PROJECTS.map((p) => (
                <tr key={p.project_id}>
                  <td>
                    <span className="tbl__name">
                      <Link to={`/app/plot/${p.project_id}`}>
                        <b>{p.name}</b>
                      </Link>
                      <span>{p.subtitle}</span>
                    </span>
                  </td>
                  <td className="num">{formatNumber(p.area_ha)}</td>
                  <td className="num">
                    <WithError value={p.agb_t_ha} error={p.agb_sd_t_ha} />
                  </td>
                  <td className="num">{p.historical_loss_share_pct} %</td>
                  <td className="num">{p.recent_loss_ha}</td>
                  <td>
                    <LevelPill level={p.fire_exposure} />
                  </td>
                  <td>
                    <LevelPill level={p.vulnerability_level} />
                  </td>
                  <td>
                    <ConfidencePill value={p.measurement_confidence_overall} />
                  </td>
                  <td>
                    <ClaimPill status={p.claim_status} />
                  </td>
                  <td className="num">
                    {p.revenue_rub_per_ha ? formatNumber(p.revenue_rub_per_ha) : <span className="dash">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <p className="ov-note">
          Цветом отмечены только уровни — числа остаются нейтральными. Раскрашенная целиком
          таблица читается как сводная оценка, а сводной оценки у нас нет и быть не может.
          Для территории без проекта сверка и выручка приходят пустыми: заявлять нечего, поэтому
          в ячейке прочерк, а не ошибка.
        </p>
      </Card>
    </>
  );
}
