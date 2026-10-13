# عقد API — ATLASYNTH Quant Agent v0.1

عنوان API المحلي الافتراضي: `http://127.0.0.1:8000`. مخطط OpenAPI متاح من `/docs` عند تشغيل الخدمة.

## قواعد عامة

- جميع endpoints مخصصة لقراءة بيانات السوق العامة أو تحليلها أو محاكاتها أو حساب تقدير مخاطر افتراضي.
- لا توجد endpoints أوامر Spot، ولا endpoint لتسجيل/إرسال مفاتيح Binance.
- أوقات بيانات السوق في contracts الداخلية بالميلي ثانية UTC ما لم ينص الحقل على غير ذلك.
- استجابات الخطأ تستخدم HTTP status غير ناجح ورسالة `detail` مختصرة.
- `evidence_score` ليست احتمال ربح.

## GET `/health`

يعيد `status`, `service`, `version` لفحص التشغيل.

## GET `/api/v1/system/safety`

يعرض إعدادات الأمان الفعلية، ويؤكد أن تنفيذ الأوامر وMargin وFutures وshorting معطلة، ولا يحتاج التطبيق إلى بيانات اعتماد البورصة.

## GET `/api/v1/strategies`

يعيد `strategy_id`, `description`, `regime_filter` للاستراتيجيات المتاحة.

## GET `/api/v1/markets/universe?limit=25`

- `limit`: من 1 إلى 100 ثم يُحد داخل الإعدادات.
- يعيد أصول Spot مؤهلة بحسب quote asset والحد الأدنى للحجم وسياسة الإزالة.
- قد يفشل بطلب 502 عند عدم توافر مصدر البيانات؛ الواجهة لا تستبدل الفشل ببيانات وهمية.

## GET `/api/v1/markets/{symbol}/candles?interval=1h&limit=500`

- `limit`: من 10 إلى 1000 ويُقيّد كذلك بالإعدادات.
- يعيد الشموع المكتملة فقط، مع OHLCV وأوقات الفتح/الإغلاق.
- الرمز والفاصل يمران عبر تحقق موصل البيانات؛ لا يسمح المستخدم بتمرير URL كامل.

## GET `/api/v1/research/analyze/{symbol}?interval=1h&limit=500`

- `limit`: من 80 إلى 1000.
- يعيد تقرير بحث لأصل واحد، وحالة السوق، واستراتيجيات مرشحة، ودرجة أدلة وتحذيرات وبصمة مصدر إن توفرت.
- يمكن أن تكون النتيجة `WATCH`, `CANDIDATE`, `REJECTED`, أو `INSUFFICIENT_DATA`.
- CANDIDATE تعني اجتياز قواعد فحص داخلية، لا ضمان النجاح ولا أمر شراء.

## GET `/api/v1/research/scan?assets_to_scan=10&interval=1h&candle_limit=300`

- `assets_to_scan`: من 1 إلى 25.
- `candle_limit`: من 80 إلى 1000.
- يرجع `requested_assets`, `assets_selected`, `assets_analyzed`, `assets_failed`, `ranked_by`, `partial_results`, `reports`, `failures`.
- الفشل لكل أصل لا يخفي؛ قد يعيد مسحًا جزئيًا مع الأخطاء.
- ترتيب التقرير بحسب disposition ثم evidence score، لا بحسب ربح متوقع.

## POST `/api/v1/backtests/run`

جسم الطلب:

```json
{
  "symbol": "ETHUSDT",
  "interval": "1h",
  "strategy_id": "trend_pullback",
  "candle_limit": 500,
  "starting_cash": 1000,
  "fee_rate": 0.001,
  "slippage_bps": 5,
  "risk_per_trade": 0.01,
  "max_exposure_fraction": 0.9,
  "atr_stop_multiple": 2,
  "reward_risk_ratio": 2
}
```

الاستراتيجيات المسموحة: `trend_pullback`, `mean_reversion`, `breakout`. القيم المدخلة عليها حدود تحقق. إن لم تتوفر عينة كافية تفشل الاستجابة بوضوح. النتائج محاكاة وليست أداء حساب حقيقي.

## POST `/api/v1/risk/estimate`

جسم الطلب:

```json
{
  "account_equity": 1000,
  "entry_price": 100,
  "stop_price": 95,
  "risk_fraction": 0.01,
  "max_exposure_fraction": 0.25,
  "fee_rate": 0.001,
  "slippage_fraction": 0.0005
}
```

يرجع تقدير كمية/تعرض نظريًا. ليس أمرًا ولا توصية مالية، ولا يتضمن اتصالًا بحساب التداول.

## POST `/api/v1/notifications/telegram/research`

جسم الطلب: `symbol`, `interval`, `candle_limit`. يتطلب متغيرات Telegram مفعلة. يرسل تقريرًا فقط إذا كان `disposition == CANDIDATE`؛ لا ينفذ صفقة. عند التعطيل أو نقص الإعدادات يرجع 409.

## التوافق بين الواجهة وAPI

الواجهة يجب أن تتعامل مع:
- تحميل (`loading`).
- خطأ شبكة/خدمة (`error`).
- نتيجة فارغة أو `INSUFFICIENT_DATA`.
- نتيجة جزئية للمسح.
- بيانات قديمة مع timestamp معلوم.
- تقارير فيها `null` لمقياس لا يمكن حسابه.

لا تضع بيانات سرية داخل حزمة الواجهة، ولا تفترض وجود حقول غير موجودة في الـ response. عند تعديل عقد API، عدّل types/tests/docs والواجهة في التغيير نفسه.
