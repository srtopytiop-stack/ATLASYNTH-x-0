# ATLASYNTH — وكيل البحث الكمي المتقدم عن EVA

**الإصدار الهيكلي:** `0.1.0`  
**النطاق:** تحليل Binance Spot العام، إنشاء مرشحين بحثيين، الاختبار التاريخي، التحقق الإحصائي، تقدير المخاطر، وتقارير بشرية المراجعة.  
**حظر دائم في هذا الإصدار:** لا تنفيذ أوامر حقيقية، ولا Margin أو Futures أو رافعة مالية أو بيع على المكشوف.

> هذه حزمة نواة قابلة للتطوير، وليست ادعاءً بأن لدينا استراتيجية مربحة أو نظامًا مؤسسيًا مكتملًا. نتيجة الاختبار لا تضمن نتيجة مستقبلية. الاختبارات البرمجية تتحقق من سلوك الكود، ولا تثبت وجود ميزة سوقية.

## 1. ما الذي تتضمنه النواة الفعلية؟

- واجهة خلفية Python/FastAPI مستقلة عن واجهة الموقع.
- موصل Binance Spot للبيانات العامة فقط؛ لا يحتاج مفاتيح تداول.
- اختيار ديناميكي للأزواج ذات عملة التسعير المحددة (USDT افتراضيًا)، مع فلترة الحجم وحالة الزوج.
- تحقق من OHLCV وترتيب الشموع وإزالة الشموع غير المكتملة.
- محرك خصائص سببي يشمل EMA وRSI وATR والتقلب المحقق وZ-score والحجم وBollinger Bands وADX.
- مصنف حالة سوق تفسيري، وثلاث استراتيجيات مرجعية long-only للبحث: Trend Pullback وMean Reversion وBreakout.
- محرك باكتيست يحاكي الدخول عند افتتاح الشمعة التالية، ويحتسب رسومًا وانزلاقًا مفترضين، ويستخدم معالجة متحفظة عندما يلمس High/Low وقف الخسارة والهدف في الشمعة نفسها.
- مقاييس عوائد وتراجع وSharpe وSortino ومعدل صفقات رابحة وعوامل أداء، مع `None` عندما لا يكون المقياس قابلًا للحساب بدل اختلاق رقم.
- PSR وDSR تقريبي معلن، وmoving-block bootstrap، وCSCV/PBO، وتقسيمات Walk-forward، وفحص prefix-invariance للخصائص.
- GARCH(1,1) recursion بمعلمات يزوّدها الباحث، وGaussian HMM صغير للتقلب، يفترض تدريبُه على بيانات التدريب فقط.
- تقدير حجم Spot النظري بالمخاطر، وبصمة SHA-256 لمدخلات التجربة، وإشعارات Telegram الاختيارية بعد إعدادها صراحةً.
- API لعرض حالة الأمان، السوق، التحليل، المسح المحدود، الاختبار التاريخي وتقدير المخاطر.
- واجهة React/Vite مبدئية عربية RTL تعرض بيانات API الفعلية ولا تصطنع بيانات سوق عند انقطاع الاتصال.
- اختبارات آلية تغطي العقود، بعض مسارات البيانات، السببية، الاختبار التاريخي، النماذج الإحصائية، المخاطر وواجهات API.

## 2. بنية المستودع

```text
ATLASYNTH_QUANT_AGENT/
├── backend/atlasynth/
│   ├── api/                 # FastAPI: API للقراءة والتحليل فقط
│   ├── core/                # إعدادات وعقود البيانات وبصمة التجربة
│   ├── data/                # موصل Binance Spot العام
│   ├── features/            # هندسة الخصائص
│   ├── regimes/             # مصنف الحالة وGARCH/HMM
│   ├── strategies/          # الاستراتيجيات المرجعية
│   ├── backtesting/         # تنفيذ افتراضي ومقاييس
│   ├── validation/          # PSR/DSR وBootstrap وCSCV وWalk-forward
│   ├── risk/                # حساب مخاطر Spot افتراضي
│   ├── agents/              # تنسيق التحليل متعدد الأدوار
│   └── notifications/       # Telegram بحثي اختياري
├── web/                     # واجهة React/Vite عربية RTL
├── tests/                   # اختبارات Python
├── docs/                    # المواصفات والمنهج العلمي والأمان
├── .github/workflows/       # بوابة الجودة
├── requirements.txt
├── pyproject.toml
├── Dockerfile
└── .env.example
```

## 3. التشغيل المحلي

### الواجهة الخلفية

يتطلب Python 3.11 أو أحدث واتصالًا بالإنترنت عند تثبيت الحزم وجلب بيانات السوق.

```bash
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell:
# .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
uvicorn atlasynth.api.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

على Windows إذا لم تتوفر `cp` أنشئ نسخة من `.env.example` باسم `.env`. افتح `http://127.0.0.1:8000/docs` لمراجعة عقد API.

### الاختبارات

من جذر المستودع:

```bash
pytest -q
python -m compileall -q backend tests
```

في حزمة التطوير هذه، اجتازت مجموعة الاختبارات المضمنة **23 اختبارًا** في البيئة التي بُنيت فيها الحزمة. لم يُتحقق من بناء واجهة React داخل بيئة الإنشاء لأن تنزيل npm dependencies انتهى بمهلة ولم تُثبت الحزم هنا؛ يجب تشغيل `npm install` و`npm run build` في بيئة متصلة قبل اعتماد الواجهة.

### الواجهة الأمامية

```bash
cd web
cp .env.example .env
npm install
npm run dev
```

العنوان الافتراضي للـ API هو `http://localhost:8000`. غيّره في `web/.env` إلى عنوان خدمة التحليل المنشورة عند النشر. تُعرض الأخطاء عند عدم اتصال الواجهة الخلفية بدل ملئها ببيانات وهمية.

### فحص من سطر الأوامر

```bash
PYTHONPATH=backend python backend/run_scan.py --symbol ETHUSDT --interval 1h --limit 300
```

تأكد من بقاء `TRADING_ENABLED=false` و`LIVE_TRADING_ENABLED=false`. إعدادات الأمان ترفض قيم التداول الفعلي بدل تفعيلها.

## 4. أهم API endpoints

| الطريقة | المسار | الغرض |
|---|---|---|
| GET | `/health` | فحص الخدمة |
| GET | `/api/v1/system/safety` | حدود الأمان الفعلية |
| GET | `/api/v1/strategies` | الاستراتيجيات المتاحة |
| GET | `/api/v1/markets/universe?limit=25` | قائمة الأزواج المؤهلة |
| GET | `/api/v1/markets/{symbol}/candles?interval=1h&limit=500` | الشموع المكتملة |
| GET | `/api/v1/research/analyze/{symbol}?interval=1h&limit=500` | تحليل أصل واحد |
| GET | `/api/v1/research/scan?assets_to_scan=10&interval=1h&candle_limit=300` | فحص أعلى مجموعة مؤهلة حسب حجم التداول |
| POST | `/api/v1/backtests/run` | محاكاة استراتيجية على بيانات تاريخية |
| POST | `/api/v1/risk/estimate` | تقدير حجم صفقة Spot نظريًا |
| POST | `/api/v1/notifications/telegram/research` | إرسال تقرير مرشح بحثي إلى Telegram المُعد مسبقًا |

لا يوجد مسار `/orders` أو تنفيذ أوامر في هذه النواة. فحص السوق محدود بعدد أصول يحدده الطلب والإعدادات لتجنب عدد غير مضبوط من استدعاءات API.

## 5. متغيرات البيئة

ابدأ من `.env.example`. الافتراضات المهمة:

```env
EXCHANGE=binance
TRADING_TYPE=spot
TRADING_ENABLED=false
LIVE_TRADING_ENABLED=false
PUBLIC_MARKET_DATA_ONLY=true
QUOTE_ASSET=USDT
MAX_SCAN_ASSETS=25
MIN_QUOTE_VOLUME_24H=1000000
TELEGRAM_ENABLED=false
```

لا تضع مفاتيح Binance الخاصة أو بيانات حسابك داخل المتصفح أو GitHub. Binance public market-data endpoints تستخدم دون مفاتيح خاصة. Telegram اختياري فقط، ويحتاج `TELEGRAM_BOT_TOKEN` و`TELEGRAM_CHAT_ID` إذا فعّلته؛ لا تضمّن هذه القيم في ملفات المشروع.

## 6. حدود الإصدار الحالي بوضوح

1. الاستراتيجيات الثلاث baseline research examples وليست استراتيجيات مثبتة الربحية.
2. واجهة المسح ترتب بحسب حالة المرشح ودرجة قائمة أدلة؛ الدرجة **ليست** احتمال الربح ولا عائدًا متوقعًا.
3. لا يوجد تخزين دائم للتجارب أو قاعدة بيانات في هذه النواة.
4. فحص الأسواق متعدد الأصول محدود بأعلى الأزواج حسب حجم 24 ساعة وعملة التسعير المختارة؛ ليس مسحًا لكل زوج موجود في كل عملات التسعير.
5. GARCH module يطبق التكرار الشرطي بمعلمات مدخلة ولا يقدّرها تلقائيًا. HMM module منفصل عن استراتيجيات baseline، ويجب تدريبُه خارج العينة؛ لا نعرضه كتنبؤ جاهز.
6. CSCV/PBO وDSR فحوص بحثية حساسة لافتراضات البيانات وتعريف التجارب وعدد المحاولات. لا يكفي تنفيذها وحده لاعتماد استراتيجية.
7. لا يوجد نموذج لغوي مطلوب لتشغيل الحسابات، ولا يتم اعتبار أي نموذج اختياري مصدر حقيقة السوق.
8. لم يتم إجراء اختبار حي على اتصال Binance في بيئة التحقق هذه، ولم يتم اختبار بناء الواجهة بسبب تعذر تنزيل npm dependencies.

اقرأ `MASTER_SPEC_AR.md` و`docs/SCIENTIFIC_METHODS_AR.md` و`docs/SECURITY_AR.md` قبل توسيع المحركات.
