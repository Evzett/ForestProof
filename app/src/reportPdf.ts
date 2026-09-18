/* Сборка отчёта в PDF-файл. KAN-79.

   Почему не печать браузером: из диалога печати документ не скачивается,
   его надо сохранять руками, а на защите и в переписке нужен файл.

   Почему не картинка страницы: растровый PDF нельзя ни искать по тексту,
   ни скопировать из него число. Отчёт, из которого нельзя вытащить
   значение, проверяющему бесполезен — поэтому текст остаётся текстом.

   Кириллица требует встроенного шрифта: стандартные шрифты PDF её не
   содержат, и без внедрения текст превратится в мусор. Отсюда PT Sans
   (SIL OFL) в assets — он грузится только при сборке документа, а не при
   открытии приложения. */

import { jsPDF } from "jspdf";
import regularUrl from "./assets/fonts/PTSans-Regular.ttf?url";
import boldUrl from "./assets/fonts/PTSans-Bold.ttf?url";

const FONT = "PTSans";
const PAGE_W = 210;
const PAGE_H = 297;
const MARGIN = 16;
const WIDTH = PAGE_W - MARGIN * 2;

async function toBase64(url: string): Promise<string> {
  const buffer = await (await fetch(url)).arrayBuffer();
  const bytes = new Uint8Array(buffer);
  let binary = "";
  // По кускам: строка из 400 КБ через apply(...) переполняет стек аргументов.
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

let fontsReady: Promise<{ regular: string; bold: string }> | null = null;

function loadFonts() {
  if (!fontsReady) {
    fontsReady = Promise.all([toBase64(regularUrl), toBase64(boldUrl)]).then(
      ([regular, bold]) => ({ regular, bold })
    );
  }
  return fontsReady;
}

export type ReportBlock =
  | { kind: "title"; text: string; sub?: string }
  | { kind: "heading"; text: string }
  | { kind: "kv"; rows: [string, string][] }
  | { kind: "steps"; rows: [string, string][] }
  | { kind: "table"; head: string[]; rows: string[][] }
  | { kind: "list"; items: string[] }
  | { kind: "note"; text: string };

/** Курсор по странице: следит за тем, чтобы блок не начинался в самом низу. */
class Cursor {
  y = MARGIN;
  private readonly doc: jsPDF;

  constructor(doc: jsPDF) {
    this.doc = doc;
  }

  space(height: number) {
    if (this.y + height > PAGE_H - MARGIN) {
      this.doc.addPage();
      this.y = MARGIN;
    }
  }

  advance(height: number) {
    this.y += height;
  }
}

function text(doc: jsPDF, cur: Cursor, value: string, opts: {
  size: number;
  bold?: boolean;
  color?: [number, number, number];
  x?: number;
  width?: number;
  lineHeight?: number;
}) {
  const { size, bold = false, color = [30, 34, 28], x = MARGIN, width = WIDTH } = opts;
  const lineHeight = opts.lineHeight ?? size * 0.45;
  doc.setFont(FONT, bold ? "bold" : "normal");
  doc.setFontSize(size);
  doc.setTextColor(...color);
  const lines = doc.splitTextToSize(value, width) as string[];
  for (const line of lines) {
    cur.space(lineHeight);
    doc.text(line, x, cur.y);
    cur.advance(lineHeight);
  }
}

function renderBlock(doc: jsPDF, cur: Cursor, block: ReportBlock) {
  switch (block.kind) {
    case "title":
      text(doc, cur, block.text, { size: 20, bold: true, lineHeight: 9 });
      if (block.sub) {
        cur.advance(1);
        text(doc, cur, block.sub, { size: 10, color: [110, 116, 104], lineHeight: 5 });
      }
      cur.advance(4);
      break;

    case "heading":
      cur.advance(4);
      cur.space(8);
      text(doc, cur, block.text.toUpperCase(), {
        size: 8.5,
        bold: true,
        color: [120, 126, 112],
        lineHeight: 4.5,
      });
      doc.setDrawColor(213, 216, 207);
      cur.space(2);
      doc.line(MARGIN, cur.y - 1.5, PAGE_W - MARGIN, cur.y - 1.5);
      cur.advance(2);
      break;

    case "kv":
      for (const [key, value] of block.rows) {
        // Пара «название — значение» не разрывается между страницами:
        // значение без своего названия на новой странице бессмысленно.
        cur.space(6);
        const top = cur.y;
        text(doc, cur, key, { size: 9, color: [110, 116, 104], width: 52, lineHeight: 4.5 });
        const afterKey = cur.y;
        cur.y = top;
        text(doc, cur, value, { size: 9.5, x: MARGIN + 56, width: WIDTH - 56, lineHeight: 4.5 });
        cur.y = Math.max(afterKey, cur.y) + 1.5;
      }
      break;

    case "steps":
      block.rows.forEach(([label, value], i) => {
        cur.space(8);
        const top = cur.y;
        text(doc, cur, `${i + 1}. ${label}`, {
          size: 9,
          bold: true,
          width: 46,
          lineHeight: 4.5,
        });
        const afterLabel = cur.y;
        cur.y = top;
        text(doc, cur, value, {
          size: 9,
          x: MARGIN + 50,
          width: WIDTH - 50,
          color: [70, 75, 66],
          lineHeight: 4.5,
        });
        cur.y = Math.max(afterLabel, cur.y) + 2.5;
      });
      break;

    case "table": {
      const colWidth = WIDTH / block.head.length;
      cur.space(7);
      block.head.forEach((h, i) => {
        doc.setFont(FONT, "bold");
        doc.setFontSize(8);
        doc.setTextColor(120, 126, 112);
        doc.text(h, MARGIN + i * colWidth, cur.y);
      });
      cur.advance(4.5);
      for (const row of block.rows) {
        const cells = row.map((cell) =>
          doc.splitTextToSize(cell, colWidth - 3)
        ) as string[][];
        const height = Math.max(...cells.map((c) => c.length)) * 4 + 1.5;
        cur.space(height);
        doc.setFont(FONT, "normal");
        doc.setFontSize(8.5);
        doc.setTextColor(40, 44, 38);
        cells.forEach((lines, i) => {
          lines.forEach((line, k) => {
            doc.text(line, MARGIN + i * colWidth, cur.y + k * 4);
          });
        });
        cur.advance(height);
      }
      break;
    }

    case "list":
      for (const item of block.items) {
        cur.space(5);
        text(doc, cur, `— ${item}`, { size: 9, color: [70, 75, 66], lineHeight: 4.5 });
        cur.advance(1);
      }
      break;

    case "note":
      cur.advance(2);
      text(doc, cur, block.text, { size: 8, color: [125, 130, 120], lineHeight: 4 });
      break;
  }
}

export async function downloadReportPdf(fileName: string, blocks: ReportBlock[]) {
  const { regular, bold } = await loadFonts();
  const doc = new jsPDF({ unit: "mm", format: "a4" });

  doc.addFileToVFS("PTSans-Regular.ttf", regular);
  doc.addFont("PTSans-Regular.ttf", FONT, "normal");
  doc.addFileToVFS("PTSans-Bold.ttf", bold);
  doc.addFont("PTSans-Bold.ttf", FONT, "bold");

  const cur = new Cursor(doc);
  for (const block of blocks) renderBlock(doc, cur, block);

  // Нумерация страниц ставится в конце: до отрисовки их число неизвестно.
  const pages = doc.getNumberOfPages();
  for (let i = 1; i <= pages; i++) {
    doc.setPage(i);
    doc.setFont(FONT, "normal");
    doc.setFontSize(7.5);
    doc.setTextColor(140, 145, 135);
    doc.text(`${i} из ${pages}`, PAGE_W - MARGIN, PAGE_H - 8, { align: "right" });
    doc.text("ForestProof · расчёт по условиям кейса", MARGIN, PAGE_H - 8);
  }

  doc.save(fileName);
}
