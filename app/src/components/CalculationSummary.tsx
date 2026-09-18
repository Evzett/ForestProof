import type { CalculationSummary as Summary } from "../data/case";
import { Card } from "./ui";

export default function CalculationSummary({ summary }: { summary?: Summary | null }) {
  if (!summary) return null;

  return (
    <Card title="Краткая справка" className="plot-summary">
      <p>{summary.text}</p>
      <details>
        <summary>Поля-источники</summary>
        <ul>
          {summary.source_fields.map((field) => <li key={field}><code>{field}</code></li>)}
        </ul>
      </details>
    </Card>
  );
}
