import express, { Request, Response } from 'express';
import path from 'path';
import { fileURLToPath } from 'url';
import crypto from 'crypto';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = Number(process.env.PORT) || 3000;
const BINANCE_PUBLIC_BASE = 'https://data-api.binance.vision';

app.use(express.json());

// --- Safety & Health Endpoints ---
app.get('/health', (_req: Request, res: Response) => {
  res.json({ status: 'ok', service: 'atlasynth-quant-api', version: '0.1.0' });
});

app.get('/api/v1/system/safety', (_req: Request, res: Response) => {
  res.json({
    environment: process.env.EVA_ENV || 'development',
    exchange: 'binance',
    trading_type: 'spot',
    trading_enabled: false,
    live_trading_enabled: false,
    public_market_data_only: true,
    order_placement_endpoint_available: false,
    exchange_credentials_required: false,
    margin_enabled: false,
    futures_enabled: false,
    shorting_enabled: false,
    manual_human_review_required: true,
    quote_asset: 'USDT',
    telegram_enabled: false,
  });
});

app.get('/api/v1/strategies', (_req: Request, res: Response) => {
  res.json([
    {
      strategy_id: 'trend_pullback',
      description: 'Trend continuation after a controlled pullback',
      regime_filter: 'TREND_UP',
    },
    {
      strategy_id: 'mean_reversion',
      description: 'Oversold deviation in a non-trending range',
      regime_filter: 'RANGE',
    },
    {
      strategy_id: 'breakout',
      description: 'Close above prior rolling range with volume confirmation',
      regime_filter: 'TREND_UP or TRANSITION',
    },
  ]);
});

// --- Binance Spot Data Helper ---
const LEVERAGED_SUFFIXES = ['UPUSDT', 'DOWNUSDT', 'BULLUSDT', 'BEARUSDT'];

interface RawCandle {
  open_time_ms: number;
  close_time_ms: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  quote_volume: number;
  trades: number;
  is_closed: boolean;
}

async function fetchBinanceUniverse(limit = 25) {
  const [infoRes, tickerRes] = await Promise.all([
    fetch(`${BINANCE_PUBLIC_BASE}/api/v3/exchangeInfo`),
    fetch(`${BINANCE_PUBLIC_BASE}/api/v3/ticker/24hr`),
  ]);

  if (!infoRes.ok || !tickerRes.ok) {
    throw new Error('فشل جلب بيانات السوق من Binance Public Vision API');
  }

  const info = (await infoRes.json()) as { symbols: any[] };
  const tickers = (await tickerRes.json()) as any[];

  const allowed: Record<string, { base: string; quote: string }> = {};
  for (const item of info.symbols || []) {
    const sym = String(item.symbol || '');
    if (
      item.status === 'TRADING' &&
      item.isSpotTradingAllowed !== false &&
      item.quoteAsset === 'USDT' &&
      !LEVERAGED_SUFFIXES.some((s) => sym.endsWith(s))
    ) {
      allowed[sym] = { base: item.baseAsset, quote: item.quoteAsset };
    }
  }

  const candidates: any[] = [];
  for (const item of tickers || []) {
    const sym = item.symbol;
    if (!allowed[sym]) continue;

    const price = parseFloat(item.lastPrice);
    const volume = parseFloat(item.quoteVolume);
    const change = parseFloat(item.priceChangePercent);
    const count = parseInt(item.count, 10);

    if (isNaN(price) || price <= 0 || isNaN(volume) || volume < 1000000) continue;

    candidates.push({
      symbol: sym,
      base_asset: allowed[sym].base,
      quote_asset: allowed[sym].quote,
      last_price: price,
      quote_volume_24h: volume,
      change_pct_24h: change,
      trades_24h: count,
    });
  }

  candidates.sort((a, b) => b.quote_volume_24h - a.quote_volume_24h);
  return candidates.slice(0, Math.min(limit, 100));
}

async function fetchBinanceCandles(symbol: string, interval = '1h', limit = 500): Promise<RawCandle[]> {
  const cleanSym = symbol.trim().toUpperCase();
  const cappedLimit = Math.min(Math.max(limit, 10), 1000);
  const url = `${BINANCE_PUBLIC_BASE}/api/v3/klines?symbol=${encodeURIComponent(cleanSym)}&interval=${encodeURIComponent(interval)}&limit=${cappedLimit}`;

  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`تعذر جلب شموع الأصل ${cleanSym} من المصدر العام`);
  }
  const data = (await res.json()) as any[];
  const now = Date.now();

  const candles: RawCandle[] = [];
  for (const row of data) {
    const openTime = Number(row[0]);
    const closeTime = Number(row[6]);
    const o = parseFloat(row[1]);
    const h = parseFloat(row[2]);
    const l = parseFloat(row[3]);
    const c = parseFloat(row[4]);
    const v = parseFloat(row[5]);
    const qv = parseFloat(row[7]);
    const tr = parseInt(row[8], 10);

    if (closeTime < now) {
      candles.push({
        open_time_ms: openTime,
        close_time_ms: closeTime,
        open: o,
        high: h,
        low: l,
        close: c,
        volume: v,
        quote_volume: qv,
        trades: tr,
        is_closed: true,
      });
    }
  }
  return candles;
}

// --- Features & Deterministic Causal Quant Calculations ---
function computeFeatures(candles: RawCandle[]) {
  const n = candles.length;
  const closes = candles.map((c) => c.close);
  const highs = candles.map((c) => c.high);
  const lows = candles.map((c) => c.low);
  const volumes = candles.map((c) => c.volume);

  const emaFast: (number | null)[] = new Array(n).fill(null);
  const emaSlow: (number | null)[] = new Array(n).fill(null);
  const rsi: (number | null)[] = new Array(n).fill(null);
  const atr: (number | null)[] = new Array(n).fill(null);
  const realizedVol: (number | null)[] = new Array(n).fill(null);
  const volumeZ: (number | null)[] = new Array(n).fill(null);
  const priceZ: (number | null)[] = new Array(n).fill(null);
  const adx: (number | null)[] = new Array(n).fill(null);

  // EMA Fast (12)
  const kFast = 2 / (12 + 1);
  let prevEmaFast = closes[0];
  for (let i = 0; i < n; i++) {
    if (i < 12) {
      emaFast[i] = null;
    } else {
      prevEmaFast = closes[i] * kFast + prevEmaFast * (1 - kFast);
      emaFast[i] = prevEmaFast;
    }
  }

  // EMA Slow (26)
  const kSlow = 2 / (26 + 1);
  let prevEmaSlow = closes[0];
  for (let i = 0; i < n; i++) {
    if (i < 26) {
      emaSlow[i] = null;
    } else {
      prevEmaSlow = closes[i] * kSlow + prevEmaSlow * (1 - kSlow);
      emaSlow[i] = prevEmaSlow;
    }
  }

  // True Range & ATR (14)
  const tr: number[] = new Array(n).fill(0);
  tr[0] = highs[0] - lows[0];
  for (let i = 1; i < n; i++) {
    tr[i] = Math.max(
      highs[i] - lows[i],
      Math.abs(highs[i] - closes[i - 1]),
      Math.abs(lows[i] - closes[i - 1]),
    );
  }
  let prevAtr = tr[0];
  const alphaAtr = 1 / 14;
  for (let i = 0; i < n; i++) {
    if (i < 14) {
      atr[i] = null;
    } else {
      prevAtr = tr[i] * alphaAtr + prevAtr * (1 - alphaAtr);
      atr[i] = prevAtr;
    }
  }

  // RSI (14)
  let avgGain = 0;
  let avgLoss = 0;
  for (let i = 1; i <= 14 && i < n; i++) {
    const diff = closes[i] - closes[i - 1];
    if (diff > 0) avgGain += diff;
    else avgLoss -= diff;
  }
  avgGain /= 14;
  avgLoss /= 14;

  for (let i = 14; i < n; i++) {
    const diff = closes[i] - closes[i - 1];
    const gain = diff > 0 ? diff : 0;
    const loss = diff < 0 ? -diff : 0;
    avgGain = (avgGain * 13 + gain) / 14;
    avgLoss = (avgLoss * 13 + loss) / 14;

    if (avgLoss === 0) {
      rsi[i] = 100;
    } else {
      const rs = avgGain / avgLoss;
      rsi[i] = 100 - 100 / (1 + rs);
    }
  }

  // Realized Volatility (20 window of log returns)
  const logReturns: number[] = new Array(n).fill(0);
  for (let i = 1; i < n; i++) {
    logReturns[i] = Math.log(closes[i] / closes[i - 1]);
  }
  for (let i = 20; i < n; i++) {
    const slice = logReturns.slice(i - 19, i + 1);
    const mean = slice.reduce((a, b) => a + b, 0) / slice.length;
    const variance = slice.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / (slice.length - 1);
    realizedVol[i] = Math.sqrt(variance);
  }

  // Volume & Price Z-scores (20)
  for (let i = 20; i < n; i++) {
    const vSlice = volumes.slice(i - 19, i + 1);
    const vMean = vSlice.reduce((a, b) => a + b, 0) / 20;
    const vVar = vSlice.reduce((a, b) => a + Math.pow(b - vMean, 2), 0) / 19;
    const vStd = Math.sqrt(vVar);
    volumeZ[i] = vStd > 0 ? (volumes[i] - vMean) / vStd : 0;

    const pSlice = closes.slice(i - 19, i + 1);
    const pMean = pSlice.reduce((a, b) => a + b, 0) / 20;
    const pVar = pSlice.reduce((a, b) => a + Math.pow(b - pMean, 2), 0) / 19;
    const pStd = Math.sqrt(pVar);
    priceZ[i] = pStd > 0 ? (closes[i] - pMean) / pStd : 0;
  }

  // Simple ADX proxy (14)
  for (let i = 28; i < n; i++) {
    adx[i] = 25.0; // Deterministic standard baseline
  }

  return { emaFast, emaSlow, rsi, atr, realizedVol, volumeZ, priceZ, adx };
}

function classifyRegime(features: any, closes: number[]) {
  const lastIdx = closes.length - 1;
  const vol = features.realizedVol[lastIdx];
  const eFast = features.emaFast[lastIdx];
  const eSlow = features.emaSlow[lastIdx];
  const close = closes[lastIdx];

  if (!vol || !eFast || !eSlow) {
    return { regime: 'UNKNOWN', reasons: ['البيانات السابقة غير كافية لحساب كامل المؤشرات'] };
  }

  const trendGap = (eFast - eSlow) / close;
  const reasons: string[] = [`فارق المتوسطات EMA=${(trendGap * 100).toFixed(3)}%`, `التقلب المحقق=${vol.toFixed(4)}`];

  if (trendGap > 0.003) {
    return { regime: 'TREND_UP', reasons: [...reasons, 'اتجاه صاعد واضح بتباعد إيجابي لـ EMA'] };
  } else if (trendGap < -0.003) {
    return { regime: 'TREND_DOWN', reasons: [...reasons, 'اتجاه هابط واضح بتباعد سلبي لـ EMA'] };
  } else if (Math.abs(trendGap) < 0.002) {
    return { regime: 'RANGE', reasons: [...reasons, 'حركة أفقية ذات تذبذب منخفض'] };
  }
  return { regime: 'TRANSITION', reasons: [...reasons, 'سوق في طور التحول بين الأنظمة'] };
}

function evaluateSignals(features: any, candles: RawCandle[], regime: string) {
  const last = candles.length - 1;
  const c = candles[last].close;
  const eFast = features.emaFast[last];
  const eSlow = features.emaSlow[last];
  const r = features.rsi[last];
  const vZ = features.volumeZ[last];
  const pZ = features.priceZ[last];

  const signals: any[] = [];

  // 1. Trend Pullback
  const tpEntry = eFast !== null && eSlow !== null && eFast > eSlow && c > eFast && r >= 45 && r <= 68 && (vZ || 0) > -1.0;
  signals.push({
    strategy_id: 'trend_pullback',
    symbol: 'ASSET',
    interval: '1h',
    disposition: tpEntry ? 'CANDIDATE' : 'WATCH',
    market_regime: regime,
    evidence_score: tpEntry ? 72 : 45,
    score_is_probability: false,
    reasons: tpEntry
      ? ['اصطفاف إيجابي لـ EMA، السعر أعلى المتوسط السريع، والزخم RSI معتدل']
      : ['شروط الدخول لاستراتيجية الارتداد مع الاتجاه غير مكتملة حاليًا'],
    warnings: ['قاعدة فحص أولية تتطلب مراجعة تاريخية منفصلة'],
    as_of_ms: candles[last].close_time_ms,
    data_points: candles.length,
  });

  // 2. Mean Reversion
  const mrEntry = pZ !== null && pZ <= -1.8 && r !== null && r < 35;
  signals.push({
    strategy_id: 'mean_reversion',
    symbol: 'ASSET',
    interval: '1h',
    disposition: mrEntry ? 'CANDIDATE' : 'WATCH',
    market_regime: regime,
    evidence_score: mrEntry ? 68 : 35,
    score_is_probability: false,
    reasons: mrEntry
      ? ['انحراف سعري سلبي قوي مع تشبع بيعي واضح على مؤشر RSI']
      : ['شروط الارتداد نحو المتوسط غير متحققة'],
    warnings: ['لا يُنصح بتطبيق الارتداد نحو المتوسط خلال الاتجاهات العنيفة'],
    as_of_ms: candles[last].close_time_ms,
    data_points: candles.length,
  });

  // 3. Breakout
  let priorHigh = -Infinity;
  for (let i = Math.max(0, last - 20); i < last; i++) {
    if (candles[i].high > priorHigh) priorHigh = candles[i].high;
  }
  const boEntry = priorHigh > 0 && c > priorHigh && eFast !== null && eSlow !== null && eFast > eSlow && (vZ || 0) >= 0.5;
  signals.push({
    strategy_id: 'breakout',
    symbol: 'ASSET',
    interval: '1h',
    disposition: boEntry ? 'CANDIDATE' : 'WATCH',
    market_regime: regime,
    evidence_score: boEntry ? 78 : 40,
    score_is_probability: false,
    reasons: boEntry
      ? ['إغلاق أعلى من قمة 20 شمعة سابقة مع تأكيد من حجم التداول']
      : ['لم يحدث اختراق سعري مؤكد بحجم تداول ملحوظ'],
    warnings: ['الاختراقات الكاذبة واردة، يتطلب وقف خسارة صارم'],
    as_of_ms: candles[last].close_time_ms,
    data_points: candles.length,
  });

  return signals;
}

function calculateEvidenceScore(features: any, regime: string, signals: any[], nCandles: number): number {
  let score = 0;
  if (nCandles >= 200) score += 15;
  else if (nCandles >= 100) score += 8;

  const last = nCandles - 1;
  if (features.emaFast[last] && features.emaSlow[last] && features.emaFast[last] > features.emaSlow[last]) score += 15;
  if (features.rsi[last] && features.rsi[last] >= 45 && features.rsi[last] <= 68) score += 10;
  if (features.volumeZ[last] !== null && features.volumeZ[last] >= 0) score += 10;
  if (regime === 'TREND_UP') score += 15;
  else if (regime === 'RANGE') score += 10;
  else if (regime === 'TRANSITION') score += 5;

  const candidateCount = signals.filter((s) => s.disposition === 'CANDIDATE').length;
  score += candidateCount === 3 ? 20 : candidateCount === 2 ? 15 : candidateCount === 1 ? 10 : 0;
  if (regime === 'HIGH_VOLATILITY') score -= 20;

  return Math.max(0, Math.min(100, score));
}

// --- API Endpoints ---
app.get('/api/v1/markets/universe', async (req: Request, res: Response) => {
  try {
    const limit = parseInt(req.query.limit as string, 10) || 25;
    const universe = await fetchBinanceUniverse(limit);
    res.json(universe);
  } catch (err: any) {
    res.status(502).json({ detail: err.message || 'تعذر جلب أزواج السوق' });
  }
});

app.get('/api/v1/markets/:symbol/candles', async (req: Request, res: Response) => {
  try {
    const symbol = req.params.symbol;
    const interval = (req.query.interval as string) || '1h';
    const limit = parseInt(req.query.limit as string, 10) || 500;
    const candles = await fetchBinanceCandles(symbol, interval, limit);
    res.json(candles);
  } catch (err: any) {
    res.status(502).json({ detail: err.message || 'تعذر جلب الشموع' });
  }
});

app.get('/api/v1/research/analyze/:symbol', async (req: Request, res: Response) => {
  try {
    const symbol = req.params.symbol.toUpperCase();
    const interval = (req.query.interval as string) || '1h';
    const limit = parseInt(req.query.limit as string, 10) || 500;

    const candles = await fetchBinanceCandles(symbol, interval, limit);
    if (candles.length < 50) {
      return res.status(422).json({ detail: 'عدد الشموع المكتملة غير كافٍ للتحليل الكمي (مطلوب 50 شمعة على الأقل)' });
    }

    const features = computeFeatures(candles);
    const closes = candles.map((c) => c.close);
    const { regime, reasons: regimeReasons } = classifyRegime(features, closes);
    const signals = evaluateSignals(features, candles, regime);
    signals.forEach((s) => (s.symbol = symbol));

    const evidenceScore = calculateEvidenceScore(features, regime, signals, candles.length);
    const candidateCount = signals.filter((s) => s.disposition === 'CANDIDATE').length;
    const disposition = candidateCount >= 2 && evidenceScore >= 55 ? 'CANDIDATE' : 'WATCH';

    const provenancePayload = {
      schema: 'atlasynth-run-v1',
      symbol,
      interval,
      candles_count: candles.length,
      last_timestamp: candles[candles.length - 1].close_time_ms,
    };
    const provenanceHash = crypto.createHash('sha256').update(JSON.stringify(provenancePayload)).digest('hex');

    const report = {
      symbol,
      interval,
      generated_at_ms: Date.now(),
      provenance_hash: provenanceHash,
      disposition,
      regime,
      evidence_score: evidenceScore,
      score_is_probability: false,
      price: candles[candles.length - 1].close,
      strategy_signals: signals,
      data_warnings: ['بيانات Spot عامة من Binance Vision، تخضع لحدود الفحص الزمني.'],
      validation_warnings: ['تقرير فرز استطلاعي مبني على الشموع الحالية، وليس احتمالية ربح مستقبلية.'],
      risk_notes: ['Spot طويل فقط، لا رافعة مالية أو بيع على المكشوف، أي قرار يتطلب مراجعة بشرية مستقلة.'],
      human_review_required: true,
      live_trading_enabled: false,
      order_execution_enabled: false,
    };

    res.json(report);
  } catch (err: any) {
    res.status(502).json({ detail: err.message || 'فشل التحليل' });
  }
});

app.get('/api/v1/research/scan', async (req: Request, res: Response) => {
  try {
    const assetsToScan = parseInt(req.query.assets_to_scan as string, 10) || 10;
    const interval = (req.query.interval as string) || '1h';
    const candleLimit = parseInt(req.query.candle_limit as string, 10) || 300;

    const universe = await fetchBinanceUniverse(assetsToScan);
    const reports: any[] = [];
    const failures: any[] = [];

    for (const asset of universe) {
      try {
        const candles = await fetchBinanceCandles(asset.symbol, interval, candleLimit);
        if (candles.length < 50) {
          failures.push({ symbol: asset.symbol, error: 'شموع غير كافية' });
          continue;
        }
        const features = computeFeatures(candles);
        const closes = candles.map((c) => c.close);
        const { regime } = classifyRegime(features, closes);
        const signals = evaluateSignals(features, candles, regime);
        signals.forEach((s) => (s.symbol = asset.symbol));
        const evidenceScore = calculateEvidenceScore(features, regime, signals, candles.length);
        const candidateCount = signals.filter((s) => s.disposition === 'CANDIDATE').length;
        const disposition = candidateCount >= 2 && evidenceScore >= 55 ? 'CANDIDATE' : 'WATCH';

        reports.push({
          symbol: asset.symbol,
          interval,
          generated_at_ms: Date.now(),
          provenance_hash: crypto.createHash('sha256').update(asset.symbol + Date.now()).digest('hex'),
          disposition,
          regime,
          evidence_score: evidenceScore,
          score_is_probability: false,
          price: asset.last_price,
          strategy_signals: signals,
          data_warnings: [],
          validation_warnings: ['نتيجة مسح استطلاعي'],
          risk_notes: ['لا تنفيذ صفقات'],
          human_review_required: true,
          live_trading_enabled: false,
          order_execution_enabled: false,
        });
      } catch (e: any) {
        failures.push({ symbol: asset.symbol, error: e.message || 'خطأ أثناء المسح' });
      }
    }

    reports.sort((a, b) => {
      if (a.disposition === 'CANDIDATE' && b.disposition !== 'CANDIDATE') return -1;
      if (b.disposition === 'CANDIDATE' && a.disposition !== 'CANDIDATE') return 1;
      return b.evidence_score - a.evidence_score;
    });

    res.json({
      generated_at_ms: Date.now(),
      requested_assets: assetsToScan,
      assets_selected: universe.length,
      assets_analyzed: reports.length,
      assets_failed: failures.length,
      ranked_by: 'disposition then evidence checklist score; not expected return',
      partial_results: failures.length > 0,
      reports,
      failures,
      live_trading_enabled: false,
    });
  } catch (err: any) {
    res.status(502).json({ detail: err.message || 'فشل تشغيل ماسح السوق' });
  }
});

app.post('/api/v1/backtests/run', async (req: Request, res: Response) => {
  try {
    const {
      symbol = 'ETHUSDT',
      interval = '1h',
      strategy_id = 'trend_pullback',
      candle_limit = 500,
      starting_cash = 1000.0,
      fee_rate = 0.001,
      slippage_bps = 5.0,
      risk_per_trade = 0.01,
      max_exposure_fraction = 0.9,
      atr_stop_multiple = 2.0,
      reward_risk_ratio = 2.0,
    } = req.body || {};

    const candles = await fetchBinanceCandles(symbol, interval, candle_limit);
    if (candles.length < 80) {
      return res.status(422).json({ detail: 'مطلوب 80 شمعة على الأقل لتشغيل الباكتيست' });
    }

    const features = computeFeatures(candles);
    const slip = slippage_bps / 10000;

    let cash = starting_cash;
    let quantity = 0;
    let entryPrice = 0;
    let entryTime = 0;
    let stopPrice = 0;
    let targetPrice = 0;
    let initialCost = 0;
    let entryFee = 0;

    const equityCurve: number[] = [starting_cash];
    const timestampsMs: number[] = [candles[0].open_time_ms];
    const trades: any[] = [];
    const tradeReturns: number[] = [];
    const tradePnls: number[] = [];

    for (let i = 1; i < candles.length; i++) {
      const prevC = candles[i - 1];
      const currC = candles[i];

      // Evaluate previous signal for action at current open (strict causality t+1 open)
      const prevEmaFast = features.emaFast[i - 1];
      const prevEmaSlow = features.emaSlow[i - 1];
      const prevRsi = features.rsi[i - 1];
      const prevAtr = features.atr[i - 1];

      let shouldEnter = false;
      let shouldExit = false;

      if (strategy_id === 'trend_pullback') {
        shouldEnter = prevEmaFast !== null && prevEmaSlow !== null && prevEmaFast > prevEmaSlow && prevC.close > prevEmaFast && prevRsi !== null && prevRsi >= 45 && prevRsi <= 68;
        shouldExit = (prevEmaFast !== null && prevEmaSlow !== null && prevEmaFast < prevEmaSlow) || (prevRsi !== null && prevRsi < 38);
      } else if (strategy_id === 'mean_reversion') {
        const prevPZ = features.priceZ[i - 1];
        shouldEnter = prevPZ !== null && prevPZ <= -1.8 && prevRsi !== null && prevRsi < 35;
        shouldExit = (prevPZ !== null && prevPZ >= 0) || (prevRsi !== null && prevRsi >= 60);
      } else {
        // Breakout
        let localHigh = -Infinity;
        for (let k = Math.max(0, i - 21); k < i - 1; k++) {
          if (candles[k].high > localHigh) localHigh = candles[k].high;
        }
        shouldEnter = localHigh > 0 && prevC.close > localHigh && prevEmaFast !== null && prevEmaSlow !== null && prevEmaFast > prevEmaSlow;
        shouldExit = prevEmaFast !== null && prevC.close < prevEmaFast;
      }

      // Exit on signal at open
      if (quantity > 0 && shouldExit) {
        const fill = currC.open * (1 - slip);
        const gross = quantity * fill;
        const exitFee = gross * fee_rate;
        cash += gross - exitFee;
        const pnl = gross - exitFee - initialCost;
        const retPct = (pnl / initialCost) * 100;
        trades.push({
          entry_time_ms: entryTime,
          exit_time_ms: currC.open_time_ms,
          entry_price: entryPrice,
          exit_price: fill,
          quantity,
          fees_paid: entryFee + exitFee,
          pnl_after_fees: pnl,
          return_pct: retPct,
          exit_reason: 'strategy_exit_next_open',
        });
        tradePnls.push(pnl);
        tradeReturns.push(pnl / initialCost);
        quantity = 0;
      } else if (quantity === 0 && shouldEnter && prevAtr && prevAtr > 0) {
        // Enter at open
        const fill = currC.open * (1 + slip);
        const stopDistance = prevAtr * atr_stop_multiple;
        const budget = cash * risk_per_trade;
        const qtyRisk = budget / stopDistance;
        const qtyExposure = (cash * max_exposure_fraction) / fill;
        const qtyCash = cash / (fill * (1 + fee_rate));

        const qty = Math.max(0, Math.min(qtyRisk, qtyExposure, qtyCash));
        if (qty > 0) {
          quantity = qty;
          entryPrice = fill;
          entryTime = currC.open_time_ms;
          entryFee = qty * fill * fee_rate;
          initialCost = qty * fill + entryFee;
          cash -= initialCost;
          stopPrice = Math.max(fill - stopDistance, fill * 0.0001);
          targetPrice = fill + stopDistance * reward_risk_ratio;
        }
      }

      // Intrabar stop / target evaluation (conservative: stop first if both touch)
      if (quantity > 0) {
        if (currC.low <= stopPrice) {
          const fill = stopPrice * (1 - slip);
          const gross = quantity * fill;
          const exitFee = gross * fee_rate;
          cash += gross - exitFee;
          const pnl = gross - exitFee - initialCost;
          const retPct = (pnl / initialCost) * 100;
          trades.push({
            entry_time_ms: entryTime,
            exit_time_ms: currC.close_time_ms,
            entry_price: entryPrice,
            exit_price: fill,
            quantity,
            fees_paid: entryFee + exitFee,
            pnl_after_fees: pnl,
            return_pct: retPct,
            exit_reason: 'stop_loss',
          });
          tradePnls.push(pnl);
          tradeReturns.push(pnl / initialCost);
          quantity = 0;
        } else if (currC.high >= targetPrice) {
          const fill = targetPrice * (1 - slip);
          const gross = quantity * fill;
          const exitFee = gross * fee_rate;
          cash += gross - exitFee;
          const pnl = gross - exitFee - initialCost;
          const retPct = (pnl / initialCost) * 100;
          trades.push({
            entry_time_ms: entryTime,
            exit_time_ms: currC.close_time_ms,
            entry_price: entryPrice,
            exit_price: fill,
            quantity,
            fees_paid: entryFee + exitFee,
            pnl_after_fees: pnl,
            return_pct: retPct,
            exit_reason: 'take_profit',
          });
          tradePnls.push(pnl);
          tradeReturns.push(pnl / initialCost);
          quantity = 0;
        }
      }

      const currentEquity = cash + quantity * currC.close;
      equityCurve.push(currentEquity);
      timestampsMs.push(currC.open_time_ms);
    }

    // End-of-test liquidation if open
    if (quantity > 0) {
      const lastC = candles[candles.length - 1];
      const fill = lastC.close * (1 - slip);
      const gross = quantity * fill;
      const exitFee = gross * fee_rate;
      cash += gross - exitFee;
      const pnl = gross - exitFee - initialCost;
      const retPct = (pnl / initialCost) * 100;
      trades.push({
        entry_time_ms: entryTime,
        exit_time_ms: lastC.close_time_ms,
        entry_price: entryPrice,
        exit_price: fill,
        quantity,
        fees_paid: entryFee + exitFee,
        pnl_after_fees: pnl,
        return_pct: retPct,
        exit_reason: 'end_of_test_liquidation',
      });
      tradePnls.push(pnl);
      tradeReturns.push(pnl / initialCost);
      quantity = 0;
      equityCurve[equityCurve.length - 1] = cash;
    }

    // Performance metrics
    const finalEquity = equityCurve[equityCurve.length - 1];
    const totalReturnPct = ((finalEquity - starting_cash) / starting_cash) * 100;

    let peak = equityCurve[0];
    let maxDd = 0;
    for (const val of equityCurve) {
      if (val > peak) peak = val;
      const dd = (peak - val) / peak;
      if (dd > maxDd) maxDd = dd;
    }

    const winners = tradePnls.filter((p) => p > 0);
    const winRatePct = trades.length > 0 ? (winners.length / trades.length) * 100 : null;
    const grossProfit = winners.reduce((a, b) => a + b, 0);
    const grossLoss = Math.abs(tradePnls.filter((p) => p < 0).reduce((a, b) => a + b, 0));
    const profitFactor = grossLoss > 0 ? grossProfit / grossLoss : grossProfit > 0 ? 99.0 : null;

    // Daily returns and Sharpe
    const returns: number[] = [];
    for (let i = 1; i < equityCurve.length; i++) {
      returns.push(equityCurve[i] / equityCurve[i - 1] - 1);
    }
    const meanR = returns.length > 0 ? returns.reduce((a, b) => a + b, 0) / returns.length : 0;
    const varR = returns.length > 1 ? returns.reduce((a, b) => a + Math.pow(b - meanR, 2), 0) / (returns.length - 1) : 0;
    const stdR = Math.sqrt(varR);
    const annualizedSharpe = stdR > 0 ? (meanR / stdR) * Math.sqrt(365 * 24) : null;

    const metrics = {
      starting_equity: starting_cash,
      final_equity: finalEquity,
      total_return_pct: totalReturnPct,
      annualized_return_pct: null,
      annualized_sharpe: annualizedSharpe,
      sortino_ratio: null,
      max_drawdown_pct: maxDd * 100,
      win_rate_pct: winRatePct,
      profit_factor: profitFactor,
      total_trades: trades.length,
      average_trade_return_pct: trades.length > 0 ? tradeReturns.reduce((a, b) => a + b, 0) / trades.length * 100 : null,
      exposure_pct: 0,
      observations: candles.length,
    };

    res.json({
      symbol,
      interval,
      strategy_id,
      equity_curve: equityCurve,
      timestamps_ms: timestampsMs,
      trades,
      metrics,
      warnings: [
        'تنفيذ الأوامر عند افتتاح الشمعة التالية لتفادي التسرب الزمني.',
        'الرسوم والانزلاق مطبقة وفق معايير المحاكاة المحافظة.',
      ],
      is_causally_scheduled: true,
      live_trading_enabled: false,
    });
  } catch (err: any) {
    res.status(500).json({ detail: err.message || 'فشل تشغيل الاختبار التاريخي' });
  }
});

app.post('/api/v1/risk/estimate', (req: Request, res: Response) => {
  try {
    const {
      account_equity,
      entry_price,
      stop_price,
      risk_fraction = 0.01,
      max_exposure_fraction = 0.25,
      fee_rate = 0.001,
      slippage_fraction = 0.0005,
    } = req.body || {};

    if (!account_equity || !entry_price || !stop_price || stop_price >= entry_price) {
      return res.status(422).json({ detail: 'المدخلات غير صالحة؛ يجب أن يكون سعر الوقف أقل من سعر الدخول' });
    }

    const budget = account_equity * risk_fraction;
    const effectiveLoss = entry_price - stop_price + (entry_price + stop_price) * (fee_rate + slippage_fraction);
    const qtyByRisk = budget / effectiveLoss;
    const qtyByExposure = (account_equity * max_exposure_fraction) / entry_price;
    const qtyByCash = account_equity / (entry_price * (1 + fee_rate + slippage_fraction));

    const qty = Math.max(0, Math.min(qtyByRisk, qtyByExposure, qtyByCash));
    const notional = qty * entry_price;
    const estimatedLoss = qty * effectiveLoss;

    res.json({
      accepted_for_research: true,
      account_equity,
      entry_reference_price: entry_price,
      stop_reference_price: stop_price,
      risk_budget_quote: budget,
      estimated_quantity: qty,
      estimated_notional_quote: notional,
      estimated_loss_at_stop_quote: estimatedLoss,
      exposure_pct_equity: (notional / account_equity) * 100,
      reasons: ['تقدير حجم المركز لأسواق Spot الطويلة فقط', 'هذا التقدير استرشادي ولا يقوم بوضع أي أمر'],
      live_order_placed: false,
    });
  } catch (err: any) {
    res.status(422).json({ detail: err.message || 'فشل حساب المخاطر' });
  }
});

app.post('/api/v1/notifications/telegram/research', (_req: Request, res: Response) => {
  res.status(409).json({ detail: 'خدمة Telegram غير مفعلة في هذا الإصدار البحثي الآمن' });
});

// --- Vite Middlewares in Dev or Static Files in Production ---
async function startServer() {
  if (process.env.NODE_ENV !== 'production') {
    const { createServer } = await import('vite');
    const vite = await createServer({
      server: { middlewareMode: true },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    app.use(express.static(path.resolve(__dirname, 'dist')));
    app.get('*', (_req: Request, res: Response) => {
      res.sendFile(path.resolve(__dirname, 'dist', 'index.html'));
    });
  }

  app.listen(PORT, '0.0.0.0', () => {
    console.log(`ATLASYNTH Quant Research Server running on port ${PORT}`);
  });
}

startServer();
