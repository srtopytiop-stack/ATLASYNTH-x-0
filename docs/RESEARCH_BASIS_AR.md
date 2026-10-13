# الأساس البحثي والمراجع المعمارية

هذه المراجع مصادر إلهام ومقارنة، وليست اعتمادًا على كودها بالكامل ولا دليلًا على أن ATLASYNTH يعادل منتجاتها المؤسسية. يجب مراجعة التراخيص والإصدارات الحالية قبل تبنّي أي كود أو اعتماد.

## EVA — الأصل الذي نطوره

- مستودع EVA-AI-01: https://github.com/srtopytiop-stack/EVA-AI-01
- يُستخدم لمراجعة فصل البيانات والخصائص والأنظمة السوقية وإدارة المخاطر والباكتيست والتحقق وبوابة الإنتاج والمراقبة. ATLASYNTH scaffold جديد ولا يُدّعى أنه دمج حرفي لكل تاريخ EVA.

## أطر بحث كمي ومعالجة البيانات

- Microsoft Qlib: https://github.com/microsoft/qlib
  - مرجع لتصميم وحدات قابلة للتركيب من البيانات والميزات والنماذج والتقييم وسير العمل.
- QuantConnect LEAN: https://github.com/QuantConnect/Lean
  - مرجع لمحرك بحث/اختبار معياري قائم على الأحداث، مع فصل بيانات/استراتيجية/محفظة/وسيط محاكاة.
- Freqtrade Lookahead Analysis: https://www.freqtrade.io/en/stable/lookahead-analysis/
  - مرجع لفحص الاستراتيجيات التي تستخدم معلومات من المستقبل أثناء الباكتيست.
- Freqtrade Recursive Analysis: https://www.freqtrade.io/en/stable/recursive-analysis/
  - مرجع لفحص حساسية المؤشرات لبداية التاريخ وطول العينة المتاحة.
- CCXT Manual: https://github.com/ccxt/ccxt/wiki/manual
  - مرجع عام في توحيد واجهات منصات التداول وإدارة حدود الطلب؛ هذه النواة لا تتطلب CCXT ولا تستخدم واجهات تنفيذ أوامر.
- Binance Spot API documentation: https://github.com/binance/binance-spot-api-docs
- Binance Market Data Only FAQs: https://github.com/binance/binance-spot-api-docs/blob/master/faqs/market_data_only.md
  - مصدر التحقق من مداخل البيانات العامة المتاحة دون مفاتيح خاصة. راجع قيود الواجهة الحالية قبل النشر.

## الاستدلال الإحصائي

- Bailey, D. H. & López de Prado, M. (2014), “The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting and Non-Normality”, *The Journal of Portfolio Management*.
  - DOI: https://doi.org/10.3905/jpm.2014.40.5.094
- Politis & Romano (1994), The Stationary Bootstrap.
  - أساس كلاسيكي للتفكير في إعادة أخذ عينات تعتمد على كتل لسلاسل زمنية.
- White (2000), A Reality Check for Data Snooping.
  - يوضح خطورة اختيار نتائج جيدة من تجارب متعددة.
- Hansen (2005), A Test for Superior Predictive Ability.
  - مرجع لاختبار تفوق تنبؤي مع معالجة تعدد النماذج.

## الوكلاء المتعددون والنماذج اللغوية

- TradingAgents: https://github.com/TauricResearch/TradingAgents
  - مثال بحثي على تنظيم أدوار متعددة للمساعدة في تحليل السوق. ATLASYNTH لا يحتاج LLM لتشغيل الحسابات الأساسية، وأي دور لغوي لاحق يبقى اختياريًا ولا يُعامل كمرجع بيانات أو إثبات إحصائي.

## سياسة الاستخدام

1. تفضيل الوثائق الرسمية والأوراق العلمية الأصلية على ملخصات التسويق.
2. تسجيل إصدار المكتبة وتاريخ المراجعة عند اعتماد تنفيذ.
3. التحقق من الترخيص قبل نسخ أو تضمين أي كود خارجي.
4. لا تسند ادعاء «ربحية مثبتة» إلى وجود أدوات أو أوراق بحثية في المراجع.
5. تحديث هذه القائمة إذا تغيرت واجهات Binance أو تراخيص المكتبات أو إصداراتها.
