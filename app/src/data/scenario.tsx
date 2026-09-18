import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { PRICE_SCENARIOS, type PriceKey } from "./case";

/* Выбранный ценовой сценарий — один на всё приложение.

   Он не влияет ни на один физический показатель и ни на число единиц:
   цена умножается уже на готовое Q. Держим его отдельно от расчёта
   именно поэтому — чтобы в коде было видно, что сценарий стоит
   за пределами углеродной части.

   Значение запоминается в браузере, но только как удобство: расчёт
   его не читает, и при недоступном хранилище всё работает как обычно. */

const STORAGE_KEY = "forestproof.price-scenario";

type Ctx = {
  priceKey: PriceKey;
  price: number;
  label: string;
  setPriceKey: (key: PriceKey) => void;
};

const ScenarioCtx = createContext<Ctx | null>(null);

function readStored(): PriceKey {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    if (value === "low" || value === "base" || value === "high") return value;
  } catch {
    /* приватное окно или запрет на хранилище — берём значение по умолчанию */
  }
  return "base";
}

export function ScenarioProvider({ children }: { children: ReactNode }) {
  const [priceKey, setKey] = useState<PriceKey>(readStored);

  const setPriceKey = useCallback((key: PriceKey) => {
    setKey(key);
    try {
      window.localStorage.setItem(STORAGE_KEY, key);
    } catch {
      /* не сохранилось — не беда, состояние живёт в памяти */
    }
  }, []);

  const value = useMemo<Ctx>(() => {
    const scenario = PRICE_SCENARIOS.find((s) => s.key === priceKey) ?? PRICE_SCENARIOS[1];
    return { priceKey, price: scenario.price, label: scenario.label, setPriceKey };
  }, [priceKey, setPriceKey]);

  return <ScenarioCtx.Provider value={value}>{children}</ScenarioCtx.Provider>;
}

export function useScenario(): Ctx {
  const ctx = useContext(ScenarioCtx);
  if (!ctx) throw new Error("useScenario вне ScenarioProvider");
  return ctx;
}
