import { useEffect, useState } from "react";
import { api } from "../api/rest";
import type { SymbolInfo } from "../types";

export function useSymbols(enabled: boolean): SymbolInfo[] {
  const [symbols, setSymbols] = useState<SymbolInfo[]>([]);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    api.symbols().then((list) => {
      if (!cancelled) setSymbols(list);
    });
    return () => {
      cancelled = true;
    };
  }, [enabled]);

  return symbols;
}
