import type { SymbolInfo } from "../types";

interface Props {
  symbols: SymbolInfo[];
  selected: string | null;
  onSelect: (symbol: string) => void;
}

export function SymbolSelector({ symbols, selected, onSelect }: Props) {
  return (
    <div className="symbol-selector">
      {symbols.map((s) => (
        <button
          key={s.symbol}
          type="button"
          className={`symbol-tab ${s.symbol === selected ? "symbol-tab--active" : ""}`}
          onClick={() => onSelect(s.symbol)}
        >
          {s.display_symbol}
        </button>
      ))}
    </div>
  );
}
