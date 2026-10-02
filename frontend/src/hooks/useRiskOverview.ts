import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/rest";
import { useTradingStore } from "../state/store";
import type { RiskOverview } from "../types";

const SAFETY_POLL_MS = 15_000;
const DEBOUNCE_MS = 120;

/**
 * Loads /risk/overview and keeps it fresh. The server pushes a "risk_dirty"
 * nudge (via the shared WebSocket) after any order or fill; we refetch on
 * it. A slow poll covers a dropped socket, so the view self-heals.
 */
export function useRiskOverview(enabled: boolean) {
  const riskTick = useTradingStore((s) => s.riskTick);
  const [data, setData] = useState<RiskOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fetchedAt, setFetchedAt] = useState<Date | null>(null);
  const latestRequest = useRef(0);

  const load = useCallback(async () => {
    const requestId = ++latestRequest.current;
    try {
      const overview = await api.riskOverview();
      if (requestId !== latestRequest.current) return; // a newer fetch superseded this one
      setData(overview);
      setFetchedAt(new Date());
      setError(null);
    } catch (err) {
      if (requestId !== latestRequest.current) return;
      setError(String(err));
    }
  }, []);

  useEffect(() => {
    if (!enabled) return;
    const handle = setTimeout(load, DEBOUNCE_MS);
    return () => clearTimeout(handle);
  }, [enabled, riskTick, load]);

  useEffect(() => {
    if (!enabled) return;
    const handle = setInterval(load, SAFETY_POLL_MS);
    return () => clearInterval(handle);
  }, [enabled, load]);

  return { data, error, fetchedAt };
}
