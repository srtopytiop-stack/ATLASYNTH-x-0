import { useEffect, useMemo, useState } from 'react';
import {
  Activity, AlertTriangle, ArrowDownRight, ArrowUpRight, BarChart3,
  CheckCircle2, ChevronDown, CircleDot, Clock3, Database, FlaskConical,
  Gauge, Layers3, LoaderCircle, Play, RefreshCw, Search, ShieldCheck,
  Sparkles, TrendingUp, TriangleAlert, Waves, Send,
} from 'lucide-react';
import {
  Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { api } from './api';
import type { BacktestResult, Disposition, ResearchReport, SafetyStatus, ScanResponse, UniverseAsset } from './types';

const INTERVALS = [
  { value: '15m', label: '15 دقيقة' }, { value: '1h', label: 'ساعة' },
  { value: '4h', label: '4 ساعات' }, { value: '1d', label: 'يومي' },
];
const STRATEGIES = [
  { value: 'trend_pullback', label: 'Trend Pullback' },
  { value: 'mean_reversion', label: 'Mean Reversion' },
  { value: 'breakout', label: 'Breakout' },
];
const fmt = (n: number | null | undefined, digits = 2) =>
  n === null || n === undefined || !Number.isFinite(n) ? '—' : n.toLocaleString('en-US', { maximumFractionDigits: digits, minimumFractionDigits: digits });
const fmtPct = (n: number | null | undefined) => n === null || n === undefined || !Number.isFinite(n) ? '—' : `${n >= 0 ? '+' : ''}${fmt(n)}%`;
const fmtVolume = (n: number) => n >= 1e9 ? `${fmt(n / 1e9)}B` : n >= 1e6 ? `${fmt(n / 1e6)}M` : `${fmt(n / 1e3)}K`;
const labelRegime: Record<string, string> = {
  TREND_UP: 'اتجاه صاعد', TREND_DOWN: 'اتجاه هابط', RANGE: 'نطاق عرضي',
  HIGH_VOLATILITY: 'تقلب مرتفع', LOW_VOLATILITY: 'تقلب منخفض', TRANSITION: 'مرحلة انتقالية', UNKNOWN: 'غير محدد',
};
const labelDisposition: Record<Disposition, string> = {
  CANDIDATE: 'مرشح للدراسة', WATCH: 'مراقبة', REJECTED: 'مرفوض', INSUFFICIENT_DATA: 'بيانات غير كافية',
};

function App() {
  const [safety, setSafety] = useState<SafetyStatus | null>(null);
  const [assets, setAssets] = useState<UniverseAsset[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState('ETHUSDT');
  const [interval, setInterval] = useState('1h');
  const [strategy, setStrategy] = useState('trend_pullback');
  const [report, setReport] = useState<ResearchReport | null>(null);
  const [scanResults, setScanResults] = useState<ScanResponse | null>(null);
  const [backtest, setBacktest] = useState<BacktestResult | null>(null);
  const [busy, setBusy] = useState<'markets' | 'analysis' | 'backtest' | null>(null);
  const [error, setError] = useState('');
  const [notifyResult, setNotifyResult] = useState('');
  const [search, setSearch] = useState('');

  useEffect(() => {
    api.safety().then(setSafety).catch((e: Error) => setError(e.message));
  }, []);

  const visibleAssets = useMemo(() => assets.filter((a) => a.symbol.toLowerCase().includes(search.toLowerCase())), [assets, search]);
  const chartData = useMemo(() => backtest?.equity_curve.map((equity, i) => ({
    index: i + 1, equity: Number(equity.toFixed(4)),
  })) || [], [backtest]);

  async function loadMarkets() {
    setBusy('markets'); setError('');
    try {
      const found = await api.universe(25);
      setAssets(found);
      if (found.length && !found.some((x) => x.symbol === selectedSymbol)) setSelectedSymbol(found[0].symbol);
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(null); }
  }
  async function runMarketScan() {
    setBusy('markets'); setError('');
    try {
      const [universe, result] = await Promise.all([api.universe(25), api.scan(interval, 10, 300)]);
      setAssets(universe);
      setScanResults(result);
      if (result.reports.length) {
        const selected = result.reports.find((r) => r.symbol === selectedSymbol) || result.reports[0];
        setSelectedSymbol(selected.symbol);
        setReport(selected);
      }
      if (result.assets_failed > 0) setError(`اكتمل المسح جزئيًا: ${result.assets_analyzed} أصلًا محللًا، وتعذر تحليل ${result.assets_failed} أصلًا. راجع أخطاء كل أصل.`);
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(null); }
  }

  async function analyze() {
    setBusy('analysis'); setError(''); setBacktest(null);
    try { setReport(await api.analyze(selectedSymbol, interval, 500)); }
    catch (e) { setError((e as Error).message); setReport(null); }
    finally { setBusy(null); }
  }
  async function sendTelegram() {
    setBusy('analysis'); setError(''); setNotifyResult('');
    try {
      const result = await api.telegramResearch(selectedSymbol, interval, 300);
      setNotifyResult(result.sent ? `تم إرسال تنبيه بحثي للأصل ${result.symbol}. لم تُرسل أي أوامر.` : (result.reason || 'لم يُرسل التنبيه.'));
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(null); }
  }

  async function runBacktest() {
    setBusy('backtest'); setError('');
    try {
      const result = await api.backtest({ symbol: selectedSymbol, interval, strategy_id: strategy, candle_limit: 500 });
      setBacktest(result);
    } catch (e) { setError((e as Error).message); setBacktest(null); }
    finally { setBusy(null); }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-lockup"><div className="brand-mark"><Layers3 size={22} /></div><div><div className="brand-name">ATLASYNTH</div><div className="brand-caption">QUANT RESEARCH AGENT</div></div></div>
        <div className="sidebar-section">مساحة العمل</div>
        <button className="nav-item active"><Gauge size={18} /><span>مركز التحليل</span><span className="nav-dot" /></button>
        <button className="nav-item" onClick={() => void loadMarkets()}><Search size={18} /><span>ماسح السوق</span></button>
        <button className="nav-item" onClick={() => document.getElementById('backtest-panel')?.scrollIntoView({ behavior: 'smooth' })}><FlaskConical size={18} /><span>مختبر الاستراتيجيات</span></button>
        <button className="nav-item" onClick={() => document.getElementById('validation-panel')?.scrollIntoView({ behavior: 'smooth' })}><ShieldCheck size={18} /><span>التحقق والمخاطر</span></button>
        <div className="sidebar-divider" />
        <div className="sidebar-section">حالة النظام</div>
        <div className="system-status"><span className="status-pulse" /><div><strong>تحليل فقط</strong><small>لا توجد صلاحية تنفيذ</small></div></div>
        <div className="sidebar-note"><ShieldCheck size={16} /><span>كل النتائج بحثية وتتطلب مراجعة بشرية قبل أي قرار.</span></div>
        <div className="sidebar-footer"><div className="api-indicator"><span className={safety ? 'indicator-ready' : 'indicator-off'} />{safety ? 'عقد الأمان محمّل' : 'بانتظار خدمة التحليل'}</div><div className="version-label">BUILD 0.1.0 · RESEARCH</div></div>
      </aside>

      <main className="main-content">
        <header className="topbar"><div className="breadcrumbs"><span>ATLASYNTH</span><span className="crumb-separator">/</span><strong>مركز التحليل</strong></div><div className="top-actions"><span className="mode-pill"><span /> SPOT RESEARCH</span><button className="icon-button" title="التحديث" onClick={() => void loadMarkets()}><RefreshCw size={17} /></button><div className="avatar">A</div></div></header>
        <section className="page-heading"><div><div className="eyebrow"><Sparkles size={14} /> QUANTITATIVE INTELLIGENCE</div><h1>مختبر السوق <span>الكمي</span></h1><p>تحليل متعدد الطبقات، تقييم الأدلة، واختبار الاستراتيجيات — دون تنفيذ تداول حقيقي.</p></div><div className="heading-status"><span className="live-dot" /> <span>وضع البحث الآمن</span><span className="status-divider" /> <span className="heading-meta">بيانات عامة فقط</span></div></section>

        {error && <div className="error-banner"><AlertTriangle size={18} /><div><strong>تعذر إكمال العملية</strong><p>{error}</p></div><button onClick={() => setError('')} aria-label="إغلاق">×</button></div>}

        <section className="kpi-grid">
          <article className="kpi-card"><div className="kpi-top"><span>الأصول المكتشفة</span><div className="kpi-icon blue"><Database size={18} /></div></div><div className="kpi-value">{scanResults ? scanResults.assets_analyzed : (assets.length || '—')}</div><div className="kpi-foot"><span className="neutral-dot" /> أزواج مؤهلة ديناميكيًا</div></article>
          <article className="kpi-card"><div className="kpi-top"><span>آخر درجة أدلة</span><div className="kpi-icon purple"><Gauge size={18} /></div></div><div className="kpi-value">{report ? fmt(report.evidence_score, 0) : '—'}<small>/100</small></div><div className="kpi-foot">ليست احتمالًا للربح</div></article>
          <article className="kpi-card"><div className="kpi-top"><span>المرشحون الحاليون</span><div className="kpi-icon mint"><TrendingUp size={18} /></div></div><div className="kpi-value">{scanResults ? scanResults.reports.filter((r) => r.disposition === 'CANDIDATE').length : (report ? report.strategy_signals.filter((s) => s.disposition === 'CANDIDATE').length : '—')}</div><div className="kpi-foot">من {report?.strategy_signals.length ?? 3} استراتيجيات مرجعية</div></article>
          <article className="kpi-card"><div className="kpi-top"><span>بوابة التنفيذ</span><div className="kpi-icon amber"><ShieldCheck size={18} /></div></div><div className="kpi-value locked">مقفلة</div><div className="kpi-foot"><CheckCircle2 size={13} /> لا تداول حقيقي</div></article>
        </section>

        <section className="workspace-grid">
          <div className="panel market-panel">
            <div className="panel-heading"><div><div className="panel-title"><Waves size={18} /> ماسح الأصول</div><div className="panel-subtitle">قائمة Spot العامة · حسب حجم التداول خلال 24 ساعة</div></div><button className="button-secondary" onClick={() => void runMarketScan()} disabled={busy !== null}>{busy === 'markets' ? <LoaderCircle className="spin" size={15} /> : <RefreshCw size={15} />} مسح وتحليل 10 أصول</button></div>
            <div className="table-toolbar"><div className="search-field"><Search size={15} /><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="ابحث عن أصل..." /></div><span className="table-count">{assets.length} أصل</span></div>
            {assets.length === 0 ? <div className="empty-state"><div className="empty-symbol"><Database size={24} /></div><strong>لم تُحمّل بيانات السوق بعد</strong><p>اضغط «فحص السوق» لجلب الأزواج المؤهلة من واجهة Binance العامة.</p><button className="button-primary" onClick={() => void loadMarkets()} disabled={busy !== null}>{busy === 'markets' ? <LoaderCircle className="spin" size={16} /> : <Play size={15} />} ابدأ المسح</button></div> : <div className="table-scroll"><table><thead><tr><th>الأصل</th><th>السعر</th><th>تغير 24س</th><th>حجم 24س</th><th /></tr></thead><tbody>{visibleAssets.map((asset) => <tr key={asset.symbol} className={selectedSymbol === asset.symbol ? 'selected-row' : ''} onClick={() => setSelectedSymbol(asset.symbol)}><td><div className="asset-cell"><div className="coin-token">{asset.base_asset.slice(0, 2)}</div><div><strong>{asset.base_asset}</strong><small>{asset.symbol}</small></div></div></td><td className="numeric">{fmt(asset.last_price, asset.last_price < 1 ? 6 : 3)}</td><td className={`numeric ${asset.change_pct_24h >= 0 ? 'positive' : 'negative'}`}>{asset.change_pct_24h >= 0 ? <ArrowUpRight size={13} /> : <ArrowDownRight size={13} />}{fmtPct(asset.change_pct_24h)}</td><td className="numeric muted-number">{fmtVolume(asset.quote_volume_24h)}</td><td><button className="row-select" aria-label={`اختيار ${asset.symbol}`}><ChevronDown size={15} /></button></td></tr>)}</tbody></table></div>}
            {scanResults && <div className="scan-results"><div className="scan-results-heading"><strong>نتائج المسح الأخير</strong><span>{scanResults.assets_analyzed} / {scanResults.assets_selected} محلل</span></div>{scanResults.reports.slice(0, 4).map((item) => <button className="scan-result-row" key={item.symbol} onClick={() => { setSelectedSymbol(item.symbol); setReport(item); }}><span className="scan-result-symbol">{item.symbol}</span><span className={`signal-chip ${item.disposition.toLowerCase()}`}>{labelDisposition[item.disposition]}</span><span className="scan-result-score">{fmt(item.evidence_score, 0)}/100</span></button>)}<small>{scanResults.ranked_by}</small></div>}
            <div className="panel-footer"><span><CircleDot size={12} /> بيانات عامة، وليست دفتر أوامر كاملًا</span><span>Quote: USDT</span></div>
          </div>

          <div className="panel analysis-panel">
            <div className="panel-heading"><div><div className="panel-title"><Activity size={18} /> تحليل الأصل</div><div className="panel-subtitle">تقرير السوق متعدد الاستراتيجيات</div></div><span className="research-tag">READ-ONLY</span></div>
            <div className="analysis-controls"><label>الأصل<div className="select-wrap"><select value={selectedSymbol} onChange={(e) => setSelectedSymbol(e.target.value)}>{assets.length ? assets.map((a) => <option key={a.symbol} value={a.symbol}>{a.symbol}</option>) : <option value={selectedSymbol}>{selectedSymbol}</option>}</select><ChevronDown size={15} /></div></label><label>الإطار الزمني<div className="select-wrap"><select value={interval} onChange={(e) => setInterval(e.target.value)}>{INTERVALS.map((x) => <option key={x.value} value={x.value}>{x.label}</option>)}</select><ChevronDown size={15} /></div></label></div>
            <button className="button-primary analyze-button" onClick={() => void analyze()} disabled={busy !== null}><span>{busy === 'analysis' ? <LoaderCircle className="spin" size={17} /> : <Search size={17} />}</span>{busy === 'analysis' ? 'جارٍ تحليل البيانات...' : 'تشغيل التحليل الكمي'}<ArrowUpRight size={16} /></button>
            {report ? <div className="report-result"><div className="report-topline"><div><span className="result-label">{report.symbol}</span><strong className="result-price">{fmt(report.price, report.price && report.price < 1 ? 6 : 3)}</strong></div><span className={`disposition ${report.disposition.toLowerCase()}`}>{labelDisposition[report.disposition]}</span></div><div className="score-row"><span>مؤشر الأدلة</span><strong>{fmt(report.evidence_score, 0)}<small>/100</small></strong></div><div className="score-track"><div style={{ width: `${report.evidence_score}%` }} /></div><div className="regime-box"><span className="regime-icon"><Activity size={17} /></span><div><small>نظام السوق المصنف</small><strong>{labelRegime[report.regime]}</strong></div><span className="regime-bullet" /></div><div className="mini-section-title">نتائج الاستراتيجيات</div><div className="strategy-list">{report.strategy_signals.map((sig) => <div className="strategy-row" key={sig.strategy_id}><div><strong>{sig.strategy_id.replaceAll('_', ' ')}</strong><small>{sig.reasons[0]}</small></div><span className={`signal-chip ${sig.disposition.toLowerCase()}`}>{labelDisposition[sig.disposition]}</span></div>)}</div><div className="report-warning"><TriangleAlert size={16} /><p>{report.validation_warnings[0] || 'هذه نتيجة بحثية أولية وليست توصية تداول.'}</p></div><div className="provenance-line"><span>بصمة التقرير</span><code title={report.provenance_hash || ''}>{report.provenance_hash?.slice(0, 18) || '—'}…</code></div>{safety?.telegram_enabled && <button className="button-secondary telegram-button" onClick={() => void sendTelegram()} disabled={busy !== null}><Send size={15} /> إرسال تنبيه بحثي عبر Telegram</button>}{notifyResult && <div className="notify-result">{notifyResult}</div>}</div> : <div className="analysis-placeholder"><div className="radar-graphic"><span /><span /><span /><div><Activity size={28} /></div></div><strong>بانتظار إشارة البحث</strong><p>اختر الأصل والإطار الزمني ثم شغّل التحليل. لن تظهر نتائج مصطنعة عند انقطاع البيانات.</p><div className="placeholder-points"><span><CheckCircle2 size={14} /> جودة البيانات</span><span><CheckCircle2 size={14} /> حالة السوق</span><span><CheckCircle2 size={14} /> توافق الاستراتيجيات</span></div></div>}
          </div>
        </section>

        <section className="bottom-grid" id="backtest-panel">
          <div className="panel backtest-panel"><div className="panel-heading"><div><div className="panel-title"><FlaskConical size={18} /> مختبر الاختبار التاريخي</div><div className="panel-subtitle">تكاليف مفترضة · تنفيذ على الشمعة التالية · Spot فقط</div></div><span className="research-tag">SIMULATION</span></div><div className="backtest-controls"><label>الاستراتيجية<div className="select-wrap"><select value={strategy} onChange={(e) => setStrategy(e.target.value)}>{STRATEGIES.map((x) => <option key={x.value} value={x.value}>{x.label}</option>)}</select><ChevronDown size={15} /></div></label><button className="button-primary" onClick={() => void runBacktest()} disabled={busy !== null}>{busy === 'backtest' ? <LoaderCircle className="spin" size={15} /> : <Play size={15} />} تشغيل باكتيست</button></div>{backtest ? <><div className="backtest-summary"><div><small>العائد الإجمالي</small><strong className={backtest.metrics.total_return_pct >= 0 ? 'positive' : 'negative'}>{fmtPct(backtest.metrics.total_return_pct)}</strong></div><div><small>أقصى تراجع</small><strong className="negative">{fmt(backtest.metrics.max_drawdown_pct)}%</strong></div><div><small>عدد الصفقات</small><strong>{backtest.metrics.total_trades}</strong></div><div><small>Sharpe سنوي</small><strong>{fmt(backtest.metrics.annualized_sharpe)}</strong></div></div><div className="equity-chart"><ResponsiveContainer width="100%" height={180}><AreaChart data={chartData}><defs><linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#5b8cff" stopOpacity={0.26} /><stop offset="100%" stopColor="#5b8cff" stopOpacity={0.01} /></linearGradient></defs><CartesianGrid strokeDasharray="3 5" stroke="#222c3b" vertical={false} /><XAxis dataKey="index" hide /><YAxis width={60} tick={{ fill: '#7d8ba1', fontSize: 10 }} domain={['auto', 'auto']} tickFormatter={(v: number) => v.toLocaleString()} axisLine={false} tickLine={false} /><Tooltip contentStyle={{ background: '#121b2a', border: '1px solid #2b3749', borderRadius: 8, color: '#e7edf7' }} formatter={(value) => [fmt(Number(value)), 'Equity']} labelFormatter={(x) => `Bar ${x}`} /><Area type="monotone" dataKey="equity" stroke="#7197ff" strokeWidth={2} fill="url(#equityFill)" dot={false} /></AreaChart></ResponsiveContainer></div><div className="panel-footer"><span><CheckCircle2 size={12} /> رسوم وانزلاق محسوبان حسب إعدادات الاختبار</span><span>{backtest.warnings.length} تنبيهات منهجية</span></div></> : <div className="backtest-empty"><div className="empty-symbol"><BarChart3 size={24} /></div><strong>لا توجد نتيجة اختبار بعد</strong><p>شغّل إحدى الاستراتيجيات لرؤية منحنى رأس المال والمخاطر الفعلية داخل النموذج. لن نعرض منحنى تجريبيًا مسبقًا.</p></div>}</div>
          <div className="panel validation-panel" id="validation-panel"><div className="panel-heading"><div><div className="panel-title"><ShieldCheck size={18} /> بوابة التحقق والمخاطر</div><div className="panel-subtitle">فحوص ما قبل الاعتماد</div></div><span className="lock-icon"><ShieldCheck size={16} /></span></div><div className="validation-list"><div className="validation-item"><span className="validation-icon"><CheckCircle2 size={16} /></span><div><strong>فصل البيانات العامة</strong><small>لا حاجة إلى مفاتيح تداول Binance.</small></div><span className="validation-state pass">مفعّل</span></div><div className="validation-item"><span className="validation-icon"><CheckCircle2 size={16} /></span><div><strong>توقيت الإشارة</strong><small>التنفيذ الافتراضي عند افتتاح الشمعة التالية.</small></div><span className="validation-state pass">مفعّل</span></div><div className="validation-item"><span className="validation-icon"><Clock3 size={16} /></span><div><strong>تحقق خارج العينة</strong><small>شغّل تحليل Walk-forward قبل الوثوق بالنتائج.</small></div><span className="validation-state pending">يتطلب تشغيلًا</span></div><div className="validation-item"><span className="validation-icon"><AlertTriangle size={16} /></span><div><strong>الانزلاق والسيولة</strong><small>افتراضات الباكتيست ليست تنفيذًا مضمونًا.</small></div><span className="validation-state review">مراجعة</span></div></div><div className="gate-footer"><ShieldCheck size={18} /><div><strong>بوابة التداول الحي غير موجودة</strong><p>هذا الإصدار يعرض التحليل والمحاكاة فقط؛ كل قرار يتطلب مراجعة بشرية.</p></div></div></div>
        </section>
        <footer className="page-footer"><div><span className="footer-mark">A</span><span>ATLASYNTH <small>Quant Research Agent</small></span></div><span>Research build 0.1.0</span><span><ShieldCheck size={13} /> Analysis only · Spot only</span></footer>
      </main>
    </div>
  );
}

export default App;
