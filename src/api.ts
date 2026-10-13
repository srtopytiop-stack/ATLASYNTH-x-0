import type { BacktestResult, ResearchReport, SafetyStatus, ScanResponse, UniverseAsset } from './types';

const API_BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    });
  } catch {
    throw new Error(`تعذر الاتصال بخدمة التحليل: ${API_BASE || 'محليًا'}. تأكد من اتصال الخادم.`);
  }
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = typeof payload === 'object' && payload !== null && 'detail' in payload
      ? String((payload as { detail: unknown }).detail)
      : `HTTP ${response.status}`;
    throw new Error(detail);
  }
  return payload as T;
}

export const api = {
  safety: () => request<SafetyStatus>('/api/v1/system/safety'),
  universe: (limit = 25) => request<UniverseAsset[]>(`/api/v1/markets/universe?limit=${limit}`),
  scan: (interval: string, assets = 10, candleLimit = 300) =>
    request<ScanResponse>(`/api/v1/research/scan?interval=${interval}&assets_to_scan=${assets}&candle_limit=${candleLimit}`),
  telegramResearch: (symbol: string, interval: string, candle_limit = 300) =>
    request<{ sent: boolean; reason?: string; symbol?: string; message_scope?: string }>('/api/v1/notifications/telegram/research', { method: 'POST', body: JSON.stringify({ symbol, interval, candle_limit }) }),
  analyze: (symbol: string, interval: string, limit = 500) =>
    request<ResearchReport>(`/api/v1/research/analyze/${encodeURIComponent(symbol)}?interval=${interval}&limit=${limit}`),
  backtest: (input: { symbol: string; interval: string; strategy_id: string; candle_limit: number }) =>
    request<BacktestResult>('/api/v1/backtests/run', { method: 'POST', body: JSON.stringify(input) }),
  riskEstimate: (input: { account_equity: number; entry_price: number; stop_price: number; risk_fraction?: number; max_exposure_fraction?: number }) =>
    request<any>('/api/v1/risk/estimate', { method: 'POST', body: JSON.stringify(input) }),
};
