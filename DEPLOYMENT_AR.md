# دليل التشغيل والنشر — ATLASYNTH

## 1. البنية المنشورة

المشروع مكوّن من خدمتين:

1. **واجهة ثابتة** من React/Vite داخل `web/` تُبنى إلى ملفات `dist/`.
2. **خدمة API** من FastAPI/Python داخل `backend/atlasynth/` وتحتاج بيئة Python واتصالًا خارجيًا للوصول إلى بيانات السوق العامة.

نشر الواجهة وحدها لا يشغّل محرك البيانات. يجب نشر API في عنوان HTTPS يمكن للواجهة الوصول إليه، وضبط CORS على أصل الواجهة بدقة.

## 2. إنشاء مستودع GitHub

1. أنشئ مستودعًا جديدًا باسم `ATLASYNTH`، ويفضل عدم اختيار إنشاء README تلقائيًا إن كنت ستدفع هذه الملفات كمجلد مشروع كامل.
2. فك ضغط `ATLASYNTH_QUANT_AGENT_V01.zip` محليًا.
3. ارفع محتويات المجلد إلى جذر المستودع، لا المجلد الأب كاملًا بطريقة تجعل المشروع متداخلًا مثل `ATLASYNTH/ATLASYNTH_QUANT_AGENT/backend`.
4. تأكد أن `README_AR.md`, `requirements.txt`, `pyproject.toml`, `backend/`, `web/`, `tests/`, `.github/` موجودة في جذر المشروع.
5. راجع `git status` ولا تضف `.env` أو `node_modules` أو `.venv` أو بيانات حساب خاصة.
6. افتح GitHub Actions وتأكد من تشغيل بوابة الجودة.

## 3. نشر API

استخدم استضافة تدعم Python وASGI. أمر بدء التشغيل من جذر المشروع:

```bash
uvicorn atlasynth.api.main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8000}
```

قد تتطلب بعض المنصات صياغة مختلفة لمتغير PORT أو Root Directory. اضبط متغيرات بيئة خدمة API من لوحة الاستضافة، وليس داخل ملفات المصدر.

الحد الأدنى المقترح للإعداد:

```env
EXCHANGE=binance
TRADING_TYPE=spot
TRADING_ENABLED=false
LIVE_TRADING_ENABLED=false
PUBLIC_MARKET_DATA_ONLY=true
QUOTE_ASSET=USDT
MAX_SCAN_ASSETS=10
MIN_QUOTE_VOLUME_24H=1000000
REQUEST_TIMEOUT_SECONDS=10
MAX_CANDLES_PER_REQUEST=1000
CORS_ORIGINS=https://YOUR-REAL-FRONTEND-DOMAIN
TELEGRAM_ENABLED=false
```

استبدل `YOUR-REAL-FRONTEND-DOMAIN` باسم الأصل الفعلي للواجهة؛ لا تترك placeholder في الإنتاج. أبقِ Telegram معطلًا إلا إذا طلبت إشعارات البحث وأعددت السر في مكان آمن.

بعد النشر تحقق من:
- `/health`
- `/api/v1/system/safety`
- `/docs` إذا أبقيت توثيق OpenAPI متاحًا.

فكر في تقييد `/docs` في نشر عام إذا لم تكن هناك حاجة إليه. لا ترفع مستوى استهلاك المسح عشوائيًا؛ كل مسح يطلب بيانات من المصدر العام.

## 4. نشر الواجهة

من مجلد `web/`:

```bash
npm install
npm run build
```

يكون الناتج في `web/dist/`. عيّن متغير بناء:

```env
VITE_API_BASE_URL=https://YOUR-REAL-API-DOMAIN
```

متغيرات `VITE_*` تُضمّن في حزمة العميل؛ لا تضع فيها أي token أو كلمة مرور أو سر. بعد التغيير أعد البناء.

## 5. الاختبار قبل مشاركة الرابط

- `pytest -q`
- `python -m compileall -q backend tests`
- `npm run build` من `web/`
- اختبر من الهاتف وعبر اتصال خارجي، لا localhost فقط.
- تحقق من CORS ومن timeout ومن فشل API ومن الرسائل الفارغة/الجزئية.
- تحقق أن صفحة الأمان تقول صراحةً أن تنفيذ التداول الحي معطل.
- لا تعتبر build النجاح دليلًا على ربحية الاستراتيجيات.

## 6. حدود الأداء والتكلفة

مسح عدة أصول يستدعي بيانات لكل أصل، لذا يجب تحديد عدد محدود من الأصول وتجنب polling السريع. هذه النسخة لا تملك queue موزعة أو cache دائمًا أو ضمان uptime. قبل توسيع الاستخدام، أضف rate limiting وcache وjob queue وmonitoring وstorage وفق خارطة الطريق.
