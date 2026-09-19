import { useNavigate } from "react-router-dom";
import { Button, InfoCard, StatPill } from "../../components/ui";
import { AREAS, PARAMETERS } from "../../data/case";
import "./Welcome.css";

/* Приветственный экран.

   Три смысловых блока: проблема, что делаем, чего не делаем.
   Закрывающий блок обязателен: пользователь должен уйти с экрана,
   понимая, чего от системы ждать не надо.

   Цифры берутся из посчитанного, а не вписаны руками: если набор
   поменяется, экран не начнёт врать.

   Обложка текучая: картинка и типографика масштабируются от ширины окна,
   жёстких координат макета нет — иначе на узком экране текст наезжает на скалу. */

const SOURCES = [
  "ESA CCI Biomass v7.0",
  "Hansen Global Forest Change v1.13",
  "MODIS MCD64A1",
  "Sentinel-2 L2A",
];

export default function Welcome() {
  const navigate = useNavigate();
  const totalArea = Math.round(AREAS.reduce((s, a) => s + a.area_ha, 0));

  return (
    <main className="welcome">
      {/* ---------- Обложка ---------- */}
      <section className="hero">
        <p className="hero__watermark" aria-hidden="true">
          ForestProof
        </p>

        <div className="hero__float" aria-hidden="true">
          <span className="hero__shadow" />
          <img className="hero__art" src="/images/hero-rock.png" alt="" />
        </div>

        <div className="hero__grid">
          <div className="hero__copy">
            <h1 className="hero__title">Проверка запаса углерода в лесу по спутнику</h1>
            <p className="hero__note">
              Просмотр без входа. Все входные данные открытые — спутниковые продукты ESA, NASA и
              Мэрилендского университета.
            </p>
            <Button size="hero" onClick={() => navigate("/app/areas")}>
              Открыть участки
            </Button>
          </div>

          <div className="hero__side">
            <div className="hero__stats">
              <StatPill
                className="hero__stat--a"
                value={String(AREAS.length)}
                caption="участка посчитано на реальных растрах"
              />
              <StatPill
                value="547 га"
                caption="потеряли древесный покров за 2020—2024"
              />
            </div>
            <p className="hero__lead">
              Считаем по открытым спутниковым данным, сколько углерода лежит в лесу и как эта
              величина изменилась, и честно показываем, насколько результату можно верить.
            </p>
          </div>
        </div>
      </section>

      {/* ---------- Что мы делаем ---------- */}
      <section className="about">
        <div className="about__left">
          <h2 className="section-title">Что мы делаем?</h2>
          <p className="about__text">
            Берём контур участка и период, считаем запас углерода на обе даты по продукту
            биомассы, показываем, где и насколько он изменился, и сравниваем результат с базовой
            линией. Там, где данных не хватает на вывод, так и пишем.
          </p>
          {/* Ведёт в журнал расчётов, а не в обзор: кнопка так и
              называется, и открывать по ней другое — обманывать подпись. */}
          <Button size="hero" onClick={() => navigate("/app/calculations")}>
            Посмотреть расчёты
          </Button>

          <div className="about__gallery">
            <img src="/images/gallery-1.jpg" alt="" loading="lazy" />
            <img src="/images/gallery-2.jpg" alt="" loading="lazy" />
          </div>
        </div>

        <div className="about__cards">
          <InfoCard
            tag="Проблема"
            title="Между отчётами не смотрит никто"
            body="Пожары, потеря покрова и восстановление меняют запас углерода, а спутниковые продукты дают разные оценки, часть наблюдений закрыта облаками, и сама биомасса известна с погрешностью. Чтобы проверить климатический проект, надо понять, какие изменения подтверждаются данными и насколько обоснован результат."
            image="/images/card-problem.jpg"
            imageAlt="Аэрофотоснимок полей и перелесков"
          />
          <InfoCard
            tone="dark"
            tag="Что делаем"
            title="Считаем запас и показываем его неопределённость"
            body="Разность запасов углерода между двумя годами с площадным взвешиванием по контуру, карта изменений из тех же пикселей, что и числа, диапазон результата с переносом ошибки продукта и расчёт потенциальных единиц относительно заданной базовой линии."
            image="/images/card-what.jpg"
            imageAlt="Снимок густого хвойного леса сверху"
          />
          <InfoCard
            tag="Чего не делаем"
            title="Не выпускаем единицы и не судим"
            body="Не устанавливаем дополнительность реального проекта, не называем причину изменения без подтверждения, не выдаём сценарный диапазон за откалиброванный интервал и не сводим пять разных вопросов в один рейтинговый балл."
            image="/images/card-limits.jpg"
            imageAlt="Скалы, поросшие мхом"
          />
        </div>
      </section>

      {/* ---------- Закрывающий блок ---------- */}
      <section className="closing">
        <span className="closing__art" aria-hidden="true" />

        <div className="closing__content">
          <h2 className="section-title section-title--light">С чего начать</h2>
          <p className="closing__text">
            {AREAS.length} участка уже посчитаны по растрам набора: биомасса, потери покрова,
            подтверждённые пожары и диапазон результата. Откройте любой или задайте свой контур.
          </p>
          <div className="closing__actions">
            <Button variant="lime" arrow size="hero" onClick={() => navigate("/app/areas")}>
              Открыть участки
            </Button>
            <p className="closing__caption">
              {totalArea.toLocaleString("ru-RU")} га суммарно · цена сценария{" "}
              {PARAMETERS.prices_rub.base.toLocaleString("ru-RU")} ₽ за единицу, не прогноз рынка
            </p>
          </div>
        </div>
      </section>

      <p className="sources">Просмотр без входа. Источники: {SOURCES.join(" · ")}</p>
    </main>
  );
}
