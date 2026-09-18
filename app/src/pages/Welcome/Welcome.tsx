import { useNavigate } from "react-router-dom";
import { Button, InfoCard, StatPill } from "../../components/ui";
import "./Welcome.css";

/* Приветственный экран.
   Требования FR-01, спецификация — docs/05-frontend-user-flow.md раздел 2.
   Три смысловых блока: проблема, что делаем, чего не делаем.
   Закрывающий блок обязателен: пользователь должен уйти с экрана,
   понимая, чего от системы ждать не надо.

   Обложка текучая: картинка и типографика масштабируются от ширины окна,
   жёстких координат макета нет — иначе на узком экране текст наезжает на скалу. */

const SOURCES = [
  "реестр углеродных единиц АО «Контур»",
  "Hansen Global Forest Change v1.13",
  "Google Dynamic World",
  "ESA CCI Biomass v6",
  "MODIS MCD64A1",
  "TerraClimate",
];

export default function Welcome() {
  const navigate = useNavigate();
  return (
    <main className="welcome">
      {/* ---------- Обложка ---------- */}
      <section className="hero">
        <p className="hero__watermark" aria-hidden="true">
          ForestProof
        </p>

        <img className="hero__art" src="/images/hero-rock.png" alt="" />

        <div className="hero__grid">
          <div className="hero__copy">
            <h1 className="hero__title">Проверка климатических снимков по спутнику</h1>
            <p className="hero__note">
              Без регистрации. Все входные данные открытые — реестр и спутниковые продукты.
            </p>
            <Button onClick={() => navigate("/app/projects")}>Проверить проект из реестра</Button>
          </div>

          <div className="hero__side">
            <div className="hero__stats">
              <StatPill
                className="hero__stat--a"
                value="132"
                caption="климатических проекта в реестре России"
              />
              <StatPill
                value="2027"
                caption="с марта счёт резервирования станет обязательным"
              />
            </div>
            <p className="hero__lead">
              Считаем по открытым спутниковым данным, что физически происходит на участке, и
              сопоставляем с тем, что заявлено в реестре углеродных единиц.
            </p>
          </div>
        </div>
      </section>

      {/* ---------- Что мы делаем ---------- */}
      <section className="about">
        <div className="about__left">
          <h2 className="section-title">Что мы делаем?</h2>
          <p className="about__text">
            Берём границы климатического проекта, считаем по спутнику, что происходило внутри
            них все годы наблюдения, и ставим результат рядом с заявленным в реестре. Там, где
            данных не хватает на вывод, так и пишем.
          </p>
          <Button onClick={() => navigate("/app/territories")}>Оценить участок</Button>

          <div className="about__gallery">
            <img src="/images/gallery-1.jpg" alt="" loading="lazy" />
            <img src="/images/gallery-2.jpg" alt="" loading="lazy" />
          </div>
        </div>

        <div className="about__cards">
          <InfoCard
            tag="Проблема"
            title="Между отчётами не смотрит никто"
            body="Проект отчитался о мониторинге в 2023 году. Что горело на его территории в 2024, 2025 и 2026 — знает только спутник. С 1 марта 2027 счёт резервирования становится регуляторной процедурой, и обосновывать его чем-то придётся."
            image="/images/card-problem.jpg"
            imageAlt="Аэрофотоснимок полей и перелесков"
          />
          <InfoCard
            tone="dark"
            tag="Что делаем"
            title="Считаем факт и сверяем с заявленным"
            body="Лесопокрытая площадь, биомасса с погрешностью, история нарушений с пожарными признаками, полнота данных и доверие к измерению. Построчное сопоставление с показателями из реестра на дату отчётности."
            image="/images/card-what.jpg"
            imageAlt="Снимок густого хвойного леса сверху"
          />
          <InfoCard
            tag="Чего не делаем"
            title="Не выпускаем единицы и не судим"
            body="Не считаем базовые линии и дополнительность, не устанавливаем процент резервирования, не выносим вердикт о добросовестности. Максимально жёсткое, что система пишет, — «требует проверки»."
            image="/images/card-limits.jpg"
            imageAlt="Скалы, поросшие мхом"
          />
        </div>
      </section>

      {/* ---------- Закрывающий блок ---------- */}
      <section className="closing">
        <img className="closing__art" src="/images/closing-forest.png" alt="" loading="lazy" />
        <div className="closing__content">
          <h2 className="section-title section-title--light">С чего начать</h2>
          <p className="closing__text">
            Три участка уже посчитаны на открытых данных — реестра углеродных единиц и
            спутниковых продуктов. Откройте любой или добавьте свой полигон.
          </p>
          <div className="closing__actions">
            <Button variant="lime" arrow onClick={() => navigate("/app/projects")}>
              Проверить проект из реестра
            </Button>
            <p className="closing__caption">132 проекта · три уже посчитаны на реальных данных</p>
          </div>
        </div>
      </section>

      <p className="sources">Без регистрации. Источники: {SOURCES.join(" · ")}</p>
    </main>
  );
}
