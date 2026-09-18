/* Краткая справка, изложенная языковой моделью.

   Ключ сюда не попадает и попасть не может: запрос идёт на наш сервер,
   а он уже ходит к модели. Ключ в сборке фронта увидел бы любой, кто
   открыл страницу и нажал «посмотреть исходный код».

   Модель только формулирует. Числа считает сервис, передаёт их в
   готовом виде, а сервер сверяет ответ: величины, которых в расчёте
   нет, отбраковываются вместе со всем ответом. Поэтому «не выдумывает»
   здесь — свойство конструкции, а не обещание в промпте.

   Если сервер не поднят или модель молчит, показывается шаблонная
   справка. Это штатное состояние, а не поломка: демо обязано работать
   без сети. */

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export type AiSummary =
  | { ok: true; text: string; model: string }
  | { ok: false; reason: string };

export async function composeSummary(facts: Record<string, unknown>): Promise<AiSummary> {
  try {
    const response = await fetch(`${API_BASE}/api/summary`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ facts }),
      signal: AbortSignal.timeout(95_000),
    });
    if (!response.ok) {
      return { ok: false, reason: `сервер ответил ${response.status}` };
    }
    const body = await response.json();
    if (!body.available) {
      return { ok: false, reason: body.reason ?? "модель недоступна" };
    }
    return { ok: true, text: body.text, model: body.model };
  } catch {
    return { ok: false, reason: "сервер справки недоступен" };
  }
}
