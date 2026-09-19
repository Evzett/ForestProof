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

import { useCallback, useEffect, useRef, useState } from "react";

/* Адрес API берётся из общего модуля, а не собирается здесь заново.
   Раньше тут стоял собственный запасной адрес `http://localhost:8000`, и
   на собранном фронте за nginx справка уходила в localhost браузера —
   то есть в никуда, — пока все остальные запросы шли на тот же origin и
   работали. Два разных представления об адресе сервера — два разных
   поведения, и расходятся они там, где это труднее всего заметить. */
import { apiBase } from "../api";

/* Подключена ли модель вообще. Спрашивается один раз на всё
   приложение: без ключа ответ не изменится, а карточек справки на
   экране бывает много — каждая слала бы свой запрос и получала один и
   тот же отказ.

   Promise кэшируется, а не результат: иначе две карточки, открытые
   одновременно, успели бы отправить по запросу до того, как вернётся
   первый. */
let statusPromise: Promise<boolean> | null = null;

function modelAvailable(): Promise<boolean> {
  if (statusPromise === null) {
    statusPromise = fetch(`${apiBase}/api/summary/status`)
      .then((r) => (r.ok ? r.json() : { available: false }))
      .then((body) => Boolean(body?.available))
      .catch(() => false);
  }
  return statusPromise;
}

export type AiSummary =
  | { ok: true; text: string; model: string }
  | { ok: false; reason: string };

export async function composeSummary(facts: Record<string, unknown>): Promise<AiSummary> {
  if (!(await modelAvailable())) {
    return { ok: false, reason: "языковая модель не подключена" };
  }
  try {
    const response = await fetch(`${apiBase}/api/summary`, {
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

export type AiState = {
  ai: { text: string; model: string } | null;
  note: string | null;
  busy: boolean;
  refresh: () => void;
};

/* Справка запрашивается сразу, как только экран открыт, и заново при
   смене исходных данных — периода, выбора участков, участка.

   Почему не по кнопке. Кнопка означала бы, что изложение модели —
   дополнительная возможность, которую надо попросить; на деле это
   основной текст карточки, а шаблон — запасной путь на случай, когда
   сервер не отвечает. Кнопка остаётся, но как «пересобрать», а не как
   «включить».

   `key` — то, при изменении чего справку надо пересобрать. Факты сюда
   не годятся: это новый объект на каждый рендер, и запрос уходил бы
   бесконечно. */
export function useAiSummary(
  key: string,
  buildFacts: () => Record<string, unknown>
): AiState {
  const [ai, setAi] = useState<{ text: string; model: string } | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const factsRef = useRef(buildFacts);
  factsRef.current = buildFacts;

  /* Ответ на устаревший запрос не должен затирать свежий: при быстрой
     смене периода модель отвечает не в том порядке, в каком её
     спрашивали. */
  const generation = useRef(0);

  /* За какой ключ уже спрашивали. В режиме разработки React вызывает
     эффект дважды, и без этой проверки каждый экран обращался бы к
     модели по два раза — она платная, и второй ответ всё равно
     отбрасывается как устаревший. */
  const asked = useRef<string | null>(null);

  const run = useCallback((key?: string) => {
    if (key !== undefined) {
      if (asked.current === key) return;
      asked.current = key;
    }
    const mine = ++generation.current;
    setBusy(true);
    setNote(null);

    composeSummary(factsRef.current()).then((result) => {
      if (mine !== generation.current) return;
      if (result.ok) {
        setAi({ text: result.text, model: result.model });
      } else {
        setAi(null);
        setNote(result.reason);
      }
      setBusy(false);
    });
  }, []);

  useEffect(() => {
    run(key);
    /* Здесь намеренно нет очистки, отменяющей запрос. В режиме
       разработки React размонтирует и монтирует экран повторно; если
       на размонтировании объявлять ответ устаревшим, то единственный
       отправленный запрос возвращается уже «ненужным», а повторный не
       уходит — и карточка навсегда остаётся в состоянии «модель
       отвечает…». Устаревшие ответы отсекает счётчик поколений: он
       растёт при каждом новом запросе, и этого достаточно. */
  }, [key, run]);

  /* Кнопка «пересобрать» спрашивает заново тот же ключ — это
     осознанное действие пользователя, а не повтор эффекта. */
  const refresh = useCallback(() => {
    asked.current = null;
    run(key);
  }, [key, run]);

  return { ai, note, busy, refresh };
}
