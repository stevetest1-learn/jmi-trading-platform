const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

let authToken: string | null = null;

export function setAuthToken(token: string | null): void {
  authToken = token;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (authToken) headers.Authorization = `Bearer ${authToken}`;

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${options.method ?? "GET"} ${path} failed: ${res.status} ${body}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  login: (username: string, password: string) =>
    request<{ access_token: string; account_id: number; username: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  me: () => request<import("../types").AccountInfo>("/accounts/me"),
  symbols: () => request<import("../types").SymbolInfo[]>("/symbols"),
  submitOrder: (body: {
    symbol: string;
    side: string;
    order_type: string;
    qty: string;
    price?: string | null;
  }) => request<import("../types").OrderResponse>("/orders", { method: "POST", body: JSON.stringify(body) }),
  cancelOrder: (orderId: number) =>
    request<import("../types").OrderResponse>(`/orders/${orderId}`, { method: "DELETE" }),
  openOrders: () => request<import("../types").OrderResponse[]>("/orders?status_filter=open"),
  positions: () => request<import("../types").PositionResponse[]>("/positions"),
  blotter: () => request<import("../types").BlotterRow[]>("/blotter"),
  riskOverview: () => request<import("../types").RiskOverview>("/risk/overview"),
  orderBook: (symbol: string) => request<import("../types").OrderBookSnapshot>(`/marketdata/${symbol}`),
};

export function wsUrl(token: string): string {
  const base = API_BASE.replace(/^http/, "ws");
  return `${base}/ws?token=${encodeURIComponent(token)}`;
}
