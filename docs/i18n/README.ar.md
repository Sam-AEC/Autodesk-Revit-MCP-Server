<div align="center">

<img src="../../assets/logo.svg" alt="شعار AEC Model Bridge: مكعب نموذج أيزومتري يعلوه قوس جسر" height="120">

[English](../../README.md) | [简体中文](README.zh-CN.md) | [Español](README.es.md) | [हिन्दी](README.hi.md) | **العربية** | [Português (BR)](README.pt-BR.md) | [Русский](README.ru.md) | [日本語](README.ja.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Bahasa Indonesia](README.id.md) | [Türkçe](README.tr.md) | [한국어](README.ko.md) | [Tiếng Việt](README.vi.md) | [Italiano](README.it.md) | [Polski](README.pl.md) | [繁體中文](README.zh-TW.md)

<div dir="rtl">

> تمت هذه الترجمة بمساعدة الذكاء الاصطناعي. المرجع الأساسي هو ملف [README](../../README.md) الإنجليزي، ونرحّب بالتصحيحات عبر pull request (راجع [CONTRIBUTING.md](../../CONTRIBUTING.md)).

</div>

**اسأل الذكاء الاصطناعي عن نموذج Revit المفتوح لديك. افتراضيًا، تُحظر أدوات الكتابة حتى توافق على خطة.**

خادم MCP مفتوح المصدر وإضافة أصلية لبرنامج Revit 2024 – 2027. يعمل مع Claude وCodex وعملاء MCP الآخرين.

[![CI](https://img.shields.io/github/actions/workflow/status/Sam-AEC/aec-model-bridge/ci.yml?branch=main&style=flat-square&label=CI)](https://github.com/Sam-AEC/aec-model-bridge/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Sam-AEC/aec-model-bridge?style=flat-square&color=0F766E)](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)
[![Revit](https://img.shields.io/badge/Revit-2024--2027-0696D7?style=flat-square)](#إصدارات-revit-المدعومة)
[![License](https://img.shields.io/badge/license-GPL--3.0%20%2B%20commercial-2563EB?style=flat-square)](../../LICENSING.md)

[ابدأ الآن](#البدء-السريع) | [أمثلة على سير العمل](#أمثلة-على-سير-العمل) | [الأدوات](../tools-generated.md) | [التوثيق](#التوثيق) | [التنزيل](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)

</div>

<div dir="rtl">

<p align="center">
  <img src="../images/readme/revit-villa-panel.png" alt="نموذج فيلا في Revit بجانب لوحة AEC Model Bridge مع تفعيل وضع Dev." width="900">
</p>

AEC Model Bridge هو خادم MCP مفتوح المصدر لبرنامج Revit، يتيح لـ Claude وCodex وCursor وغيرها من مساعدي الذكاء الاصطناعي قراءة نموذج Revit المفتوح لديك وتعديله، على أن توافق أنت أولًا على كل تغيير. يجمع بين خادم MCP مكتوب بلغة Python وإضافة Revit أصلية: تفحص الأدوات المخصصة للقراءة فقط النموذج فورًا، أما أي تغيير في النموذج فيتطلب افتراضيًا خطة معتمدة. [اطّلع على آلية الموافقة](#كيف-تعمل-الموافقة).

<p align="center">
  <img src="../images/readme/works-with.svg" alt="يعمل مع: إعداد Claude Desktop وVS Code مع GitHub Copilot وCursor وCodex موثّق. ويُتوقع أن تعمل عملاء MCP الأخرى أيضًا، مثل Claude Code وWindsurf وCline وContinue وZed وGemini CLI. التطبيقات: Revit من 2024 إلى 2027، وRhino، وGrasshopper، وNavisworks (قيد التطوير). البيانات: IFC وSpeckle وExcel وSQLite. البروتوكول: MCP عبر stdio مع بوابة موافقة." width="900">
</p>

إعداد الاتصال موثّق لـ Claude Desktop وVS Code مع GitHub Copilot وCursor وCodex. وبما أنه خادم MCP قياسي يعمل عبر stdio، فمن المتوقع أن تعمل معه عملاء أخرى مثل Claude Code وWindsurf وCline وContinue وZed وGemini CLI. راجع [التوافق](../compatibility.md) لمعرفة ما هو موثّق وما لم يُختبر بعد.

يتضمن الخادم نفسه فحص ملفات IFC وأتمتة Rhino وGrasshopper والتكامل مع Speckle. يبيّن [حالة التكاملات](#تكاملات-أخرى) المزوّدات المتاحة وتلك التي ما زالت قيد التطوير.

## أمثلة على سير العمل

لمنسّقي BIM: افحص جودة النموذج، وراجع العناصر المتأثرة، ووافق على تصحيح المعاملات (parameters)، ثم تحقق من النتائج وصدّر تقريرًا. تستخدم هذه الأمثلة أدوات من [الفهرس الحالي](../tools-generated.md).

| سير العمل | مثال على الطلب | الأدوات المستخدمة |
| --- | --- | --- |
| مراجعة النموذج | "اعرض المستند النشط، وأدرج تحذيراته، وابحث عن العناصر المتأثرة." | `revit_get_document_info`، `revit_get_warnings`، `revit_get_elements_by_type` |
| تحديث المعاملات | "ابحث عن الجدران في Level 02، واعرض قيم Comments الخاصة بها، واقترح تحديثًا دفعيًا." | `revit_get_elements_by_type`، `revit_get_element_parameters`، `revit_batch_set_parameters` |
| إنتاج المخططات | "جهّز قائمة لوحات (sheets) من ملف CSV هذا، ثم اقترح إنشاء اللوحات ووضع المناظير (views)." | `revit_batch_create_sheets_from_csv`، `revit_place_viewport_on_sheet` |
| مراجعة IFC | "اعرض طوابق ملف IFC هذا، وافحص خصائص الجدران، وأبلغ عن مشكلات التحقق من المخطط." | `ifc_get_spatial_structure`، `ifc_get_properties`، `ifc_validate` |

لتجربة أولى داخل Revit، جرّب ما يلي:

</div>

```text
Read the active model's warnings. Group them by description and show the
affected element IDs. Then suggest which issues to investigate first.
```

<div dir="rtl">

ثم جرّب تصحيح معامل، مع استبدال المستوى والقيمة بما يناسب مشروعك:

</div>

```text
Find walls on Level 02 and show their current Comments values. Propose setting
Comments to "Coordination reviewed" for the elements I choose. After I approve
the plan in Revit, apply it and read the values back to confirm the result.
```

<div dir="rtl">

في التعديلات، ينشئ المساعد خطة باستخدام `plan_actions`؛ وتراجعها أنت في لوحة Revit قبل أن يطبّقها `execute_plan`. مراجعة IFC تعمل دون Revit.

تتطلب وحدات QA/QC والتقارير القائمة على اللقطات (snapshots) لقطة محفوظة متوافقة. ويحتاج تمرير اللقطة حاليًا من Revit إلى الوحدة إلى تطابق اسم الملف ومساحة العمل؛ وقد يؤدي حذف `snapshot_id` إلى إرجاع بيانات نموذجية مولَّدة. استخدم أدوات Revit المباشرة أعلاه للفحص الحي. [الإصلاحات المخططة والعرض التجريبي](../roadmap.md).

## البدء السريع

**التثبيت بنقرة واحدة**

[![Install in VS Code](https://img.shields.io/badge/Install_in-VS_Code-0098FF?style=for-the-badge)](../install-buttons.md#vs-code)
[![Install in Cursor](https://img.shields.io/badge/Install_in-Cursor-111111?style=for-the-badge)](https://cursor.com/en/install-mcp?name=aec-model-bridge&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyItLWZyb20iLCJnaXQraHR0cHM6Ly9naXRodWIuY29tL1NhbS1BRUMvYWVjLW1vZGVsLWJyaWRnZSNzdWJkaXJlY3Rvcnk9cGFja2FnZXMvbWNwLXNlcnZlci1yZXZpdCIsImFlYy1tb2RlbC1icmlkZ2UiXSwiZW52Ijp7Ik1DUF9SRVZJVF9NT0RFIjoiYnJpZGdlIn19)
[![Claude Desktop bundle](https://img.shields.io/badge/Claude_Desktop-.mcpb_bundle-D97757?style=for-the-badge)](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)

تحتاج الأزرار إلى [uv](https://docs.astral.sh/uv/getting-started/installation/) فقط دون أي إعداد آخر: يستخدم الخادم المجلد `~/Documents/AEC Model Bridge` كمساحة عمل ما لم تحدد مساحتك الخاصة. بالنسبة إلى Claude Desktop، نزّل ملف `.mcpb` من أحدث إصدار وافتحه. ما زال العمل الحي مع Revit يتطلب Revit و[الإضافة](#تثبيت-إضافة-revit)؛ أما الوضع التجريبي (mock) فلا يحتاج إلى شيء.

**الإعداد اليدوي**

للأتمتة الحية في Revit تحتاج إلى Windows، ونسخة مرخّصة من Revit من 2024 إلى 2027، وPython 3.11 أو أحدث، و[uv](https://docs.astral.sh/uv/getting-started/installation/)، وإضافة Revit ([خطوات التثبيت](#تثبيت-إضافة-revit)). ثم أضف ما يلي إلى ملف `claude_desktop_config.json` (يستخدم Codex وCursor وVS Code القيم نفسها؛ ومتغيرا المجلدين اختياريان ويشيران افتراضيًا إلى مساحة العمل المذكورة أعلاه):

</div>

```json
{
  "mcpServers": {
    "aec-model-bridge": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/Sam-AEC/aec-model-bridge#subdirectory=packages/mcp-server-revit",
        "aec-model-bridge"
      ],
      "env": {
        "MCP_REVIT_MODE": "bridge",
        "MCP_REVIT_WORKSPACE_DIR": "C:\\RevitProjects",
        "MCP_REVIT_ALLOWED_DIRECTORIES": "C:\\RevitProjects"
      }
    }
  }
}
```

<div dir="rtl">

هل تريد الاطلاع على الأدوات أولًا دون Revit؟ اضبط `"MCP_REVIT_MODE": "mock"`. عندئذٍ يعمل الخادم في أي مكان، ويسرد كل الأدوات مع مخططاتها، ويعيد ردودًا جاهزة دون أن يلمس أي نموذج. يوجد ملف `Dockerfile` للوضع التجريبي نفسه في جذر المستودع (`docker build -t aec-model-bridge .` ثم `docker run -i --rm aec-model-bridge`).

تستخدم VS Code؟ يسجّل [مصدر الامتداد وخطوات التثبيت المحلي](../../extensions/vscode/README.md) خادم MCP ويعرض حالة الاتصال بـ Revit. لم يُنشر الامتداد في Marketplace.

### نظرة سريعة على الأدوات

| المجال | الأدوات | ماذا تفعل |
| --- | --- | --- |
| Revit | 110 | قراءة النموذج، وإنشاء العناصر والمعاملات والمناظير واللوحات والجداول وتحريرها، والتصدير، والعمل المشترك (worksharing) |
| الموافقة | 5 | تخطيط تغييرات النموذج ومراجعتها واعتمادها وتنفيذها والتراجع عنها |
| الوحدات | 108 | فحص اللقطات، وشبكات المعاملات، وفحوص QA/QC، والوصفات، والتقارير، والتحديدات |
| Rhino وGrasshopper | 19 | الهندسة، والطبقات، والخامات، والعمليات المنطقية (boolean) |
| Speckle | 17 | المشاريع، والنماذج، والإصدارات، والإرسال والاستقبال |
| Navisworks | 15 | شجرة النموذج، ونقاط الرؤية، واختبارات التعارض (قيد التطوير) |
| IFC | 7 | قراءة ملفات IFC دون Revit: البنية، والخصائص، والتحقق |
| الرسم البياني، واللقطات، والتصدير، والمهام | 21 | تدقيق الرسم البياني الدلالي، وفروق اللقطات، والتصدير إلى SQLite، والمهام الخلفية |

تُدرج 302 أداة في الإعداد الافتراضي (عُدّت من الخادم الحالي في الوضع التجريبي mock). تظهر أدوات Autodesk Data عند ضبط بيانات اعتماد APS. يسرد [مرجع الأدوات](../tools-generated.md) كل أداة. تحمل كل أداة تعليقات MCP التوضيحية (`readOnlyHint` و`destructiveHint` و`idempotentHint` و`openWorldHint`)، ليتمكّن العملاء من التمييز بين القراءة والكتابة.

### أتمتة Revit المتقدمة

إلى جانب استعلامات النموذج وتحديثات المعاملات، تنشئ أدوات Revit عناصر المباني والمناظير واللوحات والجداول والوسوم والأبعاد، وتصدّر ملفات IFC وDWG والصور وملفات Navisworks. راجع [مرجع الأدوات](../tools-generated.md) للاطلاع على العمليات والمدخلات المدعومة.

لما لا يغطيه فهرس الأدوات، تعمل `revit_invoke_method` و`revit_reflect_get` و`revit_reflect_set` مع أعضاء واجهة Revit API العامة، وتشغّل `revit_execute_python` شيفرة IronPython داخل Revit. لهذه الأدوات المتقدمة الصلاحيات نفسها التي لعملية Revit. لا تستخدمها إلا مع عملاء MCP وprompts تثق بها.

## كيف يعمل

يتحدث عميل MCP مع موزّع (hub) واحد مكتوب بـ Python. يرسل الموزّع كل استدعاء إلى المزوّد الذي يملك الأداة. وتتحدث مزوّدات تطبيقات سطح المكتب عبر localhost مع إضافة صغيرة داخل ذلك التطبيق.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../images/architecture-dark.png">
    <img src="../images/architecture-light.png" alt="بنية AEC Model Bridge: يستدعي عميل MCP، مثل Claude أو Codex، موزّع MCP المكتوب بلغة Python، فيوجّه الموزّع استدعاءات الأدوات إلى مزوّدات Revit وRhino وNavisworks وIFC وSpeckle. يتصل مزوّدا Revit وRhino بالإضافات عبر HTTP على localhost، ويقرأ مزوّد IFC ملفات IFC باستخدام IfcOpenShell، أما Navisworks فما زال قيد التطوير." width="900">
  </picture>
</p>

<sub>مصدر المخطط: [architecture.mmd](../diagrams/architecture.mmd). أعد توليد الصور بالأمر `python scripts/render_diagrams.py`.</sub>

المربعات ذات اللون الأخضر المزرق تعمل اليوم. المربعات ذات الحدود المتقطعة بلون العنبر قيد التطوير. أما الأشكال النيلية فتمثّل البيانات والخدمات الخارجية.

### كيف تعمل الموافقة

يوقف الموزّع أي استدعاء لأداة يغيّر النموذج ما لم يحمل خطة معتمدة. الوضع الافتراضي هو `required`. يقترح الذكاء الاصطناعي خطة، وتراجعها أنت في اللوحة الجانبية في Revit، ثم تنفّذها الإضافة على الخيط الرئيسي (main thread) في Revit وتنفّذ إجراءات تعديل المعاملات (parameters) والنموذج كلًّا ضمن معاملة (transaction) مسمّاة مستقلة؛ أما إجراءات الحفظ والمزامنة والسكربتات فلا، لذا لا يشملها Ctrl+Z.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/Sam-AEC/aec-model-bridge/main/docs/images/readme/readme-workflow-dark.png">
    <img src="https://raw.githubusercontent.com/Sam-AEC/aec-model-bridge/main/docs/images/readme/readme-workflow-light.png" alt="فحص، اقتراح، موافقة، تحقق. أربع خطوات: يعثر الفحص على قيمة Mark فارغة، ويصوغ الاقتراح تغييرًا، والموافقة قرار بشري، ويقرأ التحقق القيمة مجددًا. القيم المعروضة أمثلة توضيحية." width="900">
  </picture>
</p>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../images/approval-flow-dark.png">
    <img src="../images/approval-flow-light.png" alt="مخطط تدفق الموافقة: يصوغ مساعد الذكاء الاصطناعي خطة عبر plan_actions، وتعرض اللوحة الجانبية التغييرات المقترحة (الأعداد والنطاق والقيم قبل وبعد)، ثم يوافق إنسان في اللوحة أو عبر أداة سطر الأوامر aec-model-bridge-approve، ولا تتم الموافقة أبدًا عبر MCP. يتحقق الموزّع من تطابق الخطة مع الأداة والوسائط المعتمدة، ولمرة واحدة فقط. ثم ينفّذ Revit كل إجراء في معاملة مستقلة، فيتراجع Ctrl+Z عن إجراء واحد في كل ضغطة. وإذا رفضتَ أو لم توافق، يُحجب الاستدعاء ويبقى النموذج دون تغيير." width="900">
  </picture>
</p>

<sub>مصدر المخطط: [approval-flow.mmd](../diagrams/approval-flow.mmd). أعد توليد الصور بالأمر `python scripts/render_diagrams.py`.</sub>

إذا تبيّن أن خطة ما خاطئة، فتراجع عنها بـ Ctrl+Z في Revit. كل كتابة لمعامل هي معاملة مسمّاة مستقلة، لذا قد تحتاج خطة واحدة إلى عدة ضغطات. التراجع بخطوة واحدة عن خطة كاملة مخطَّط له ولم يُبنَ بعد. يعيد الطريق الثاني هو خطة تراجع: يصيغ المساعد واحدة بالأداة `plan_revert` انطلاقًا من إثبات خطة نُفّذت، وتوافق عليها كأي خطة أخرى. `rollback_plan` مخصص للأشخاص فقط وليس زرًا ولا أمرًا، فلا تعتمد عليه. لم يُتحقَّق من أيٍّ من هذه المسارات في جلسة Revit حقيقية بعد (UNVERIFIED). أما العمليات التي لا يمكن عكسها، مثل كتابة الملفات، فلا يتراجع عنها أيٌّ منها، ولا تطلب تأكيدًا ثانيًا بعد (مخطَّط له). تعرض قائمة الخطط في اللوحة الخطط المعلّقة فقط؛ ويعمل الأمر `aec-model-bridge-approve show <plan_id>` مع خطة في أي حالة، بينما لا توجد حزم `proofs/` إلا للخطط التي نُفّذت (أو جرت محاولة تنفيذها). دورة الحياة موضحة في [ADR 0008](../0008-approval-gate-lifecycle.md).

في خطوط المعالجة الآلية غير المراقَبة يمكنك ضبط `MCP_REVIT_APPROVAL_MODE=auto`. يؤدي ذلك إلى إيقاف المراجعة البشرية، لذا استخدمه في بيئة خاضعة للتحكم فقط.

## إصدارات Revit المدعومة

| إصدار Revit | هدف الإضافة | أدوات البناء |
|---|---|---|
| 2024 | .NET Framework 4.8 | .NET 8 SDK وحزمة المطوّر لـ .NET Framework 4.8 |
| 2025 | .NET 8 for Windows | .NET 8 SDK |
| 2026 | .NET 8 for Windows | .NET 8 SDK |
| 2027 | .NET 10 for Windows | .NET 10 SDK |

تحتاج أيضًا إلى Windows 10 أو 11، وPython 3.11 أو أحدث، ونسخة Revit مرخّصة للإصدار الذي تستخدمه. يشغّل الوضع التجريبي (mock) الخادم دون Revit، وهو مفيد للتطوير والاختبار.

### تكاملات أخرى

| التكامل | الحالة |
|---|---|
| Revit | متاح. إضافة أصلية بلغة C#. |
| IFC (IfcOpenShell) | متاح. يقرأ ملفات IFC دون الحاجة إلى تشغيل Revit. |
| Rhino وGrasshopper | متاح. يتصل بإضافة Rhino على `localhost:3004`. |
| Speckle | متاح. يحتاج إلى معرّف عميل Speckle في بيئتك. |
| Navisworks Manage | قيد التطوير. المزوّد وأدواته مسجّلان، لكن إضافة Navisworks لم تكتمل. |
| Power BI | قيد التطوير. المزوّد والأداة موجودان لكنهما غير مسجّلين في الموزّع. |
| Excel وParquet وDuckDB | مخطط له. |

أسماء المنتجات والشعارات مملوكة لأصحابها. تُستخدم في اللافتة العلوية فقط لبيان ما يعمل معه هذا المشروع.

## تثبيت إضافة Revit

**الأسهل (Windows):** نزّل `AECModelBridge-Setup-<version>.exe` من [أحدث إصدار](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)، وانقر عليه نقرًا مزدوجًا، واختر إصدارات Revit لديك، ثم أعد تشغيل Revit. يثبّت الإضافة وخادم Python المرفق، وإذا حددت الخيار فيثبّت أيضًا إعدادات Claude Desktop وVS Code مع نسخة احتياطية من إعداداتك الحالية. يمكنك إلغاء التثبيت من إعدادات Windows. الخطوات أدناه مخصصة للبناء من المصدر.

عليك تثبيت جزأين: خادم MCP بلغة Python وإضافة Revit. تحتاج الأتمتة الحية في Revit إلى كليهما.

### 1. تثبيت خادم MCP

</div>

```powershell
git clone https://github.com/Sam-AEC/aec-model-bridge.git
cd aec-model-bridge

py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e packages/mcp-server-revit
```

<div dir="rtl">

### 2. تثبيت إضافة Revit

اضبط الإصدار ليطابق تثبيت Revit لديك. إذا حظر Windows السكربتات التي نزّلتها، فانقر بزر الفأرة الأيمن على كل ملف `.ps1`، وافتح Properties، واختر Unblock قبل تشغيلها.

</div>

```powershell
$RevitVersion = Read-Host "Revit year (2024, 2025, 2026, or 2027)"

.\scripts\package.ps1 -RevitVersion $RevitVersion
.\scripts\install.ps1 -RevitVersion $RevitVersion
```

<div dir="rtl">

يضع المثبّت الملفات التنفيذية الخاصة بكل إصدار في:

</div>

```text
C:\ProgramData\AECModelBridge\bin\<year>
```

<div dir="rtl">

يُثبَّت ملف بيان الإضافة (manifest) لكل مستخدم في:

</div>

```text
%APPDATA%\Autodesk\Revit\Addins\<year>
```

<div dir="rtl">

استخدم `-AllUsers` مع `install.ps1` لتثبيت ملف البيان في `C:\ProgramData\Autodesk\Revit\Addins\<year>` بدلًا من ذلك.

لتجهيز الملفات التنفيذية لكل الإصدارات المدعومة دفعة واحدة:

</div>

```powershell
.\scripts\package.ps1 -RevitVersion All
```

<div dir="rtl">

يتضمن كل [إصدار على GitHub](https://github.com/Sam-AEC/aec-model-bridge/releases/latest) حزمة جاهزة لكل سنة من Revit، مثل `aec-model-bridge-revit-2026-<version>.zip`. فك ضغطها ثم شغّل `.\install.ps1 -RevitVersion 2026` بدلًا من البناء من المصدر. ولإنشاء مثبّت Windows بنقرة مزدوجة، يبنيه السكربت `scripts/build-installer.ps1` باستخدام Inno Setup. الدليل الكامل، مع استكشاف الأخطاء وإصلاحها، في [docs/install.md](../install.md).

## ربط Claude Desktop بـ Revit

أضف الخادم إلى إعدادات عميل MCP لديك. في Claude Desktop هو قسم `mcpServers` في `claude_desktop_config.json`. يستخدم Codex وCursor وVS Code وغيرها من عملاء MCP قيم `command` و`args` و`env` نفسها بصيغة الإعداد الخاصة بكل منها.

استخدم ملف Python التنفيذي من بيئتك الافتراضية، واختر مجلد مساحة عمل يُسمح للخادم بالوصول إليه:

</div>

```json
{
  "mcpServers": {
    "aec-model-bridge": {
      "command": "C:\\path\\to\\aec-model-bridge\\.venv\\Scripts\\python.exe",
      "args": ["-m", "revit_mcp_server.mcp_server"],
      "env": {
        "MCP_REVIT_MODE": "bridge",
        "MCP_REVIT_WORKSPACE_DIR": "C:\\RevitProjects",
        "MCP_REVIT_ALLOWED_DIRECTORIES": "C:\\RevitProjects"
      }
    },
    "aec-model-bridge-revit-2026": {
      "command": "C:\\path\\to\\aec-model-bridge\\.venv\\Scripts\\python.exe",
      "args": ["-m", "revit_mcp_server.mcp_server"],
      "env": {
        "MCP_REVIT_MODE": "bridge",
        "MCP_REVIT_HOST_VERSION": "2026",
        "MCP_REVIT_WORKSPACE_DIR": "C:\\RevitProjects",
        "MCP_REVIT_ALLOWED_DIRECTORIES": "C:\\RevitProjects"
      }
    }
  }
}
```

<div dir="rtl">

احذف `MCP_REVIT_HOST_VERSION` لاستهداف أحدث نسخة Revit مفتوحة. واضبطه على سنة مثل `2024` أو `2026` لتثبيت إدخال العميل على ذلك الإصدار من Revit. يتجاوز `MCP_REVIT_BRIDGE_URL` نقطة الاتصال في الإعدادات المتقدمة.

يمكن لمستخدمي VS Code البدء من [`.vscode/mcp.json`](../../.vscode/mcp.json). ويمكن لمستخدمي Hermes Desktop البدء من [`docs/examples/hermes-desktop.json`](../examples/hermes-desktop.json) بعد استبدال مسار Python النموذجي. ويمكن للعملاء الذين يدعمون MCP Bundles تثبيت ملف `.mcpb` من [أحدث إصدار](https://github.com/Sam-AEC/aec-model-bridge/releases/latest). وتبقى إضافة Revit مطلوبة لأن الخادم يتحدث مع تطبيق سطح المكتب العامل.

### التحقق من الاتصال

أعد تشغيل Revit بعد تثبيت الإضافة، وافتح نموذجًا، ثم نفّذ:

</div>

```powershell
$registry = Get-ChildItem "$env:LOCALAPPDATA\AECModelBridge\registry\revit-*.json" | Select-Object -First 1
$switch = Get-Content $registry.FullName -Raw | ConvertFrom-Json
Invoke-RestMethod "$($switch.endpoint)/health"
```

<div dir="rtl">

يجب أن يُظهر الرد `healthy` وإصدار Revit العامل. في Revit، ابحث عن علامة التبويب `AEC Bridge` في الشريط. تضم لوحة Workflows الأوامر Open Panel وHealth Check وPending Actions وReports. وتضم لوحة Tools الأوامر Config وHelp وAbout.

## الأمان

- يستمع جسر Revit على localhost فقط.
- يقرأ الخادم ويكتب داخل المجلدات المذكورة في `MCP_REVIT_ALLOWED_DIRECTORIES` فقط.
- تحتاج الأدوات التي تغيّر النموذج إلى خطة معتمدة ما لم توقف الموافقة.
- تُسجَّل استدعاءات الأدوات في سجل تدقيق، وتُخفى القيم السرية.

التفاصيل في [docs/security.md](../security.md). للإبلاغ عن ثغرة أمنية، اتبع [SECURITY.md](../../SECURITY.md).

## الأسئلة الشائعة

### ما هو خادم MCP لبرنامج Revit؟

بروتوكول Model Context Protocol (MCP) معيار مفتوح يتيح لمساعدي الذكاء الاصطناعي استدعاء أدوات في برامج أخرى. ينشر خادم MCP لبرنامج Revit عمليات Revit على هيئة أدوات. يختار المساعد الأدوات، وتنفّذها الإضافة داخل Revit.

### ما مساعدو الذكاء الاصطناعي الذين يعملون معه؟

أي عميل MCP قادر على تشغيل خادم stdio محلي. نوثّق إعداد Claude Desktop وVS Code مع GitHub Copilot وCursor وCodex، والعملاء الذين يقرؤون إعداد `mcpServers` القياسي. ويُتوقع أن تعمل Windsurf وCline وRoo Code وContinue وZed وClaude Code وGemini CLI بالطريقة نفسها، لكنها لم تُختبر. راجع [التوافق](../compatibility.md). ويمكن لمحادثة اللوحة أيضًا استخدام مفتاح Anthropic API أو أداتي سطر الأوامر `claude` أو `codex` إذا كانتا مثبّتتين. راجع [ADR 0012](../0012-native-agent-chat-backend.md).

### هل يستطيع الذكاء الاصطناعي تغيير نموذجي دون أن يسأل؟

ليس في الوضع الافتراضي. تُحجب الأدوات التي تغيّر النموذج حتى تُعتمد خطة في لوحة Revit. وتعمل الأدوات للقراءة فقط دون موافقة. وإذا ضبطت `MCP_REVIT_APPROVAL_MODE=auto` فستُتجاوز الموافقة.

### هل يرسل نموذجي إلى السحابة؟

يعمل الخادم والإضافة على جهازك، ويستمع الجسر على localhost. وما يراه مساعد الذكاء الاصطناعي يعتمد على العميل الذي تستخدمه: تذهب نتائج الأدوات إلى مزوّد النموذج لدى ذلك العميل. أما المزوّدات المرتبطة بالسحابة، مثل Speckle، فلا تعمل إلا عند ضبطها واستدعاء أدواتها.

### هل يعمل مع ملفات IFC دون Revit؟

نعم. يقرأ مزوّد IFC الملفات باستخدام IfcOpenShell. يمكنه إرجاع بيانات الملف الوصفية والبنية المكانية وخصائص العناصر والصناديق المحيطة (bounding boxes)، وتنفيذ استعلامات بحسب الفئة أو GUID أو الاسم أو الخاصية، والتحقق من المخطط. ولا يحرّر ملفات IFC.

### هل يمكنني استخدامه دون تثبيت Revit؟

يمكنك تشغيل الخادم في الوضع التجريبي (mock) للتطوير والاختبار. أما العمل الحي على النموذج فيحتاج إلى Revit من 2024 إلى 2027 والإضافة.

## الإصدارات والنسخ

يتبع AEC Model Bridge نظام الإصدارات الدلالي. تُوسَم الإصدارات على GitHub بالصيغة `vX.Y.Z`، ويحتوي ملف `VERSION` في الجذر على رقم الإصدار. راجع [docs/versioning.md](../versioning.md) لعملية الإصدار، و[CHANGELOG.md](../../CHANGELOG.md) لما تغيّر في كل إصدار.

## التطوير

</div>

```powershell
# Python tests
python -m pytest packages/mcp-server-revit/tests

# Build one Revit version, for example 2026
.\scripts\build-addin.ps1 -RevitVersion 2026 -Configuration Release

# Build all supported versions
.\scripts\package.ps1 -RevitVersion All
```

<div dir="rtl">

يبني CI خادم Python وأهداف الإضافة لإصدارات Revit من 2024 إلى 2027. راجع [CONTRIBUTING.md](../../CONTRIBUTING.md) قبل فتح pull request.

## التوثيق

- [دليل التثبيت](../install.md)
- [مرجع الأدوات](../tools-generated.md)
- [البنية المعمارية](../0001-multi-provider-architecture.md)
- [مرجع الإعدادات](../configuration-reference.md)
- [الأمان](../security.md)
- [عملاء MCP والسجل](../marketplaces.md)
- [الإصدارات والنسخ](../versioning.md)
- [كل التوثيق](../README.md)
- [دليل المساهمة](../../CONTRIBUTING.md) و [مدونة السلوك](../../CODE_OF_CONDUCT.md)
- [المساهمون](../../CONTRIBUTORS.md)

## Built with

AEC Model Bridge stands on open-source work. It is independent and is not affiliated with or endorsed by any project named here.

- [Model Context Protocol](https://modelcontextprotocol.io) Python SDK (MIT) for the MCP server
- [IfcOpenShell](https://ifcopenshell.org) (LGPL-3.0-or-later) for IFC files
- [specklepy](https://github.com/specklesystems/specklepy) (Apache-2.0) for Speckle
- [pydantic](https://docs.pydantic.dev), [httpx](https://www.python-httpx.org), [NetworkX](https://networkx.org), [openpyxl](https://openpyxl.readthedocs.io) and [PyYAML](https://pyyaml.org) (MIT or BSD)
- [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python) (MIT) for the built-in agent chat
- [Serilog](https://serilog.net), [IronPython](https://ironpython.net) and [Microsoft WebView2](https://developer.microsoft.com/microsoft-edge/webview2/) in the Revit add-in
- Autodesk Revit and Navisworks and McNeel Rhino are separate products that you license yourself. This project does not include their code.

Licence texts and the full list of packages are in [THIRD_PARTY_NOTICES.md](../../THIRD_PARTY_NOTICES.md). Licences were read from package metadata; rows that could not be verified are marked as such.

## المشروع والترخيص

يتولى صيانته [A. Sam Mohammad](https://github.com/Sam-AEC).
[LinkedIn](https://www.linkedin.com/in/a-sam-mohammad-92790416b) |
[Issues](https://github.com/Sam-AEC/aec-model-bridge/issues)

[GPL-3.0-or-later مع استثناء الربط بـ Revit (Revit Linking Exception)، أو ترخيص تجاري](../../LICENSING.md).

</div>
