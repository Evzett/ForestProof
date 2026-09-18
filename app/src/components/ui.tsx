import type { ReactNode } from "react";
import "./ui.css";

/* Кнопка-пилюля. Два вида: тёмная (основная) и лаймовая (акцентная, в закрывающем блоке). */
export function Button({
  children,
  variant = "dark",
  arrow = false,
  onClick,
  type = "button",
}: {
  children: ReactNode;
  variant?: "dark" | "lime" | "outline";
  arrow?: boolean;
  onClick?: () => void;
  type?: "button" | "submit";
}) {
  return (
    <button type={type} className={`btn btn--${variant}`} onClick={onClick}>
      <span>{children}</span>
      {arrow && <span className="btn__arrow" aria-hidden="true">→</span>}
    </button>
  );
}

/* Плашка со статистикой: крупное число и подпись под ним. */
export function StatPill({
  value,
  caption,
  className = "",
}: {
  value: string;
  caption: string;
  className?: string;
}) {
  return (
    <div className={`stat ${className}`.trim()}>
      <span className="stat__value tabular">{value}</span>
      <span className="stat__caption">{caption}</span>
    </div>
  );
}

/* Ярлык-категория над заголовком карточки. */
export function Tag({ children, tone = "light" }: { children: ReactNode; tone?: "light" | "dark" }) {
  return <span className={`tag tag--${tone}`}>{children}</span>;
}

/* ---------- Элементы разделов приложения ---------- */

/* Карточка приложения: белая по умолчанию, тёмная или мягкая по необходимости. */
export function Card({
  title,
  note,
  tone = "light",
  className = "",
  children,
}: {
  title?: string;
  note?: string;
  tone?: "light" | "dark" | "soft";
  className?: string;
  children?: ReactNode;
}) {
  return (
    <section className={`card card--${tone} ${className}`.trim()}>
      {title && (
        <header className="card__head">
          <h2 className="card__title">{title}</h2>
          {note && <span className="card__note">{note}</span>}
        </header>
      )}
      {children}
    </section>
  );
}

const LEVEL_LABEL = { low: "низкая", medium: "средняя", high: "высокая" } as const;
const CONF_LABEL = { high: "высокое", moderate: "умеренное", low: "низкое" } as const;

/* Пилюля уровня. Цветом кодируются только уровни — числа остаются
   нейтральными, иначе таблица читается как сводная оценка (FR-17). */
export function LevelPill({ level, label }: { level: "low" | "medium" | "high"; label?: string }) {
  return <span className={`lvl lvl--${level}`}>{label ?? LEVEL_LABEL[level]}</span>;
}

export function ConfidencePill({ value }: { value: "high" | "moderate" | "low" }) {
  const level = value === "high" ? "low" : value === "moderate" ? "medium" : "high";
  return <span className={`lvl lvl--${level}`}>{CONF_LABEL[value]}</span>;
}

const CLAIM_LABEL = {
  no_material_discrepancy: "расхождений нет",
  review_recommended: "требует проверки",
  evidence_insufficient: "данных недостаточно",
  not_comparable: "не сопоставимы",
} as const;

const CLAIM_LEVEL = {
  no_material_discrepancy: "low",
  review_recommended: "high",
  evidence_insufficient: "none",
  not_comparable: "none",
} as const;

/* Статус сверки. Для территории без проекта приходит null — рисуем прочерк,
   а не ошибку: заявлять нечего. */
export function ClaimPill({ status }: { status: keyof typeof CLAIM_LABEL | null }) {
  if (!status) return <span className="dash">—</span>;
  return <span className={`lvl lvl--${CLAIM_LEVEL[status]}`}>{CLAIM_LABEL[status]}</span>;
}

/* Круглая кнопка-переход из угла карточки. */
export function CircleBtn({ glyph = "↗", tone = "dark" }: { glyph?: string; tone?: "dark" | "lime" }) {
  return (
    <span className={`circle circle--${tone}`} aria-hidden="true">
      {glyph}
    </span>
  );
}

/* Значение с погрешностью. Биомасса нигде не выводится без ± (FR-82). */
export function WithError({ value, error, unit }: { value: number; error: number; unit?: string }) {
  return (
    <span className="tabular">
      {value} ± {error}
      {unit ? ` ${unit}` : ""}
    </span>
  );
}

export function formatNumber(n: number): string {
  return n.toLocaleString("ru-RU");
}

/* Дробные — с запятой: точка в русском тексте читается как опечатка */
export function formatDecimal(n: number, digits = 1): string {
  return n.toLocaleString("ru-RU", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

/* Карточка раздела «Что мы делаем»: ярлык, заголовок, текст и фотография справа. */
export function InfoCard({
  tag,
  title,
  body,
  image,
  imageAlt,
  tone = "light",
}: {
  tag: string;
  title: string;
  body: string;
  image: string;
  imageAlt: string;
  tone?: "light" | "dark";
}) {
  return (
    <article className={`info info--${tone}`}>
      {/* В макете ярлык отбит от заголовка на 16, а заголовок от текста — на 10,
          поэтому пара «заголовок + текст» лежит в своей обёртке. */}
      <div className="info__text">
        <Tag tone={tone === "dark" ? "dark" : "light"}>{tag}</Tag>
        <div className="info__copy">
          <h3 className="info__title">{title}</h3>
          <p className="info__body">{body}</p>
        </div>
      </div>
      <div className="info__media">
        <img src={image} alt={imageAlt} loading="lazy" />
      </div>
    </article>
  );
}
