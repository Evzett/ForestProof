import { useState } from "react";
import { Card } from "../../components/ui";
import { PageHead } from "../../components/AppShell";
import { downloadReportPdf } from "../../reportPdf";
import { researchBlocks } from "../../data/research";
import type { ReportBlock } from "../../reportPdf";
import "./Research.css";

/* Исследовательский отчёт — KAN-53.

   Страница и PDF собираются из одного набора блоков. Держать две
   версии одного отчёта — верный способ однажды сказать в них разное,
   а отчёт, который расходится сам с собой, не проверишь. */

function Block({ block }: { block: ReportBlock }) {
  switch (block.kind) {
    case "title":
      return null; // заголовок отчёта рисует шапка страницы

    case "heading":
      return <h2 className="res__heading">{block.text}</h2>;

    case "kv":
      return (
        <dl className="kv res__kv">
          {block.rows.map(([label, value]) => (
            <div key={label + value}>
              <dt>{label}</dt>
              <dd className="tabular">{value}</dd>
            </div>
          ))}
        </dl>
      );

    case "steps":
      return (
        <ol className="steps">
          {block.rows.map(([label, value]) => (
            <li key={label + value}>
              <b>{label}</b>
              <span>{value}</span>
            </li>
          ))}
        </ol>
      );

    case "table":
      return (
        <div className="tbl__scroll">
          <table className="tbl res__table">
            <thead>
              <tr>
                {block.head.map((h) => (
                  <th key={h} className={h === block.head[0] ? "" : "num"}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.rows.map((row) => (
                <tr key={row.join("|")}>
                  {row.map((cell, i) => (
                    <td
                      key={i}
                      className={i === 0 ? "" : "num"}
                      /* Ненулевая ячейка выделена: в таблице из тридцати
                         значений три отличных от нуля иначе теряются, а
                         весь смысл таблицы именно в них. */
                      data-hot={i > 0 && cell !== "0" ? "true" : undefined}
                    >
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );

    case "list":
      return (
        <ul className="drivers res__list">
          {block.items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      );

    case "note":
      return <p className="res__note">{block.text}</p>;

    default:
      return null;
  }
}

export default function Research() {
  const blocks = researchBlocks();
  const title = blocks.find((b) => b.kind === "title");
  const [pdf, setPdf] = useState<"idle" | "busy" | "failed">("idle");

  const savePdf = async () => {
    if (pdf === "busy") return;
    setPdf("busy");
    try {
      await downloadReportPdf("forestproof-issledovanie.pdf", blocks);
      setPdf("idle");
    } catch {
      setPdf("failed");
    }
  };

  /* Разделы отчёта идут карточками: заголовок открывает карточку, и всё,
     что до следующего заголовка, лежит внутри неё. Сплошным текстом
     семь разделов читались бы одной простынёй. */
  const sections: { heading: string | null; body: ReportBlock[] }[] = [];
  for (const block of blocks) {
    if (block.kind === "title") continue;
    if (block.kind === "heading") {
      sections.push({ heading: block.text, body: [] });
    } else {
      if (sections.length === 0) sections.push({ heading: null, body: [] });
      sections[sections.length - 1].body.push(block);
    }
  }

  return (
    <>
      <PageHead
        title={title?.kind === "title" ? title.text : "Исследование"}
        subtitle={title?.kind === "title" ? title.sub : undefined}
        action={
          <button className="btn btn--dark" type="button" onClick={savePdf} disabled={pdf === "busy"}>
            <span>{pdf === "busy" ? "Готовим PDF…" : "Скачать PDF"}</span>
          </button>
        }
      />

      {pdf === "failed" && (
        <p className="ov-note" role="alert">
          PDF собрать не удалось — файл не скачан. Весь отчёт есть на этой странице, её же
          можно сохранить документом через печать браузера.
        </p>
      )}

      <div className="res">
        {sections.map((section, index) =>
          section.heading === null ? (
            <Card key="lead" className="res__lead">
              {section.body.map((b, i) => (
                <Block key={i} block={b} />
              ))}
            </Card>
          ) : (
            <Card key={section.heading} title={section.heading} className="res__section">
              {section.body.map((b, i) => (
                <Block key={i} block={b} />
              ))}
              <span className="res__index" aria-hidden="true">
                {String(index).padStart(2, "0")}
              </span>
            </Card>
          )
        )}
      </div>
    </>
  );
}
