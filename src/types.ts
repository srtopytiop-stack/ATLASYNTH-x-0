export type Regime = 'TREND_UP' | 'TREND_DOWN' | 'RANGE' | 'HIGH_VOLATILITY' | 'LOW_VOLATILITY' | 'TRANSITION' | 'UNKNOWN';
export type Disposition = 'WATCH' | 'CANDIDATE' | 'REJECTED' | 'INSUFFICIENT_DATA';

export interface SafetyStatus {
  environment: string;
  exchange: string;
  trading_type: string;
  trading_enabled: false;
  live_trading_enabled: false;
  public_market_data_only: true;
  order_placement_endpoint_available: false;
  exchange_credentials_required: false;
  margin_enabled: false;
  futures_enabled: false;
  shorting_enabled: false;
  manual_human_review_required: true;
  telegram_enabled: boolean;
}

export interface UniverseAsset {
  symbol: string;
  base_asset: string;
  quote_asset: string;
  last_price: number;
  quote_volume_24h: number;
  change_pct_24h: number;
  trades_24h: number;
}

export interface StrategySignal {
  strategy_id: string;
  symbol: string;
  interval: string;
  disposition: Disposition;
  market_regime: Regime;
  evidence_score: number;
  score_is_probability: false;
  reasons: string[];
  warnings: string[];
  as_of_ms: number;
  data_points: number;
}

export interface ResearchReport {
  symbol: string;
  interval: string;
  generated_at_ms: number;
  provenance_hash: string | null;
  disposition: Disposition;
  regime: Regime;
  evidence_score: number;
  score_is_probability: false;
  price: number | null;
  strategy_signals: StrategySignal[];
  data_warnings: string[];
  validation_warnings: string[];
  risk_notes: string[];
  human_review_required: true;
  live_trading_enabled: false;
  order_execution_enabled: false;
}

export interface PerformanceMetrics {
  starting_equity: number;
  final_equity: number;
  total_return_pct: number;
  annualized_return_pct: number | null;
  annualized_sharpe: number | null;
  sortino_ratio: number | null;
  max_drawdown_pct: number;
  win_rate_pct: number | null;
  profit_factor: number | null;
  total_trades: number;
  average_trade_return_pct: number | null;
  exposure_pct: number;
  observations: number;
}

export interface TradeRecord {
  entry_time_ms: number;
  exit_time_ms: number;
  entry_price: number;
  exit_price: number;
  quantity: number;
  fees_paid: number;
  pnl_after_fees: number;
  return_pct: number;
  exit_reason: string;
}

export interface BacktestResult {
  symbol: string;
  interval: string;
  strategy_id: string;
  equity_curve: number[];
  timestamps_ms: number[];
  trades: TradeRecord[];
  metrics: PerformanceMetrics;
  warnings: string[];
  is_causally_scheduled: true;
  live_trading_enabled: false;
}

export interface ScanResponse {
  generated_at_ms: number;
  requested_assets: number;
  assets_selected: number;
  assets_analyzed: number;
  assets_failed: number;
  ranked_by: string;
  partial_results: boolean;
  reports: ResearchReport[];
  failures: { symbol: string; error: string }[];
  live_trading_enabled: false;
}
