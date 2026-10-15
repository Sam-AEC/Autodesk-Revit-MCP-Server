<div align="center">

<img src="../../assets/logo.svg" alt="AEC Model Bridge का लोगो: ब्रिज आर्च वाला आइसोमेट्रिक मॉडल क्यूब" height="120">

[English](../../README.md) | [简体中文](README.zh-CN.md) | [Español](README.es.md) | **हिन्दी** | [العربية](README.ar.md) | [Português (BR)](README.pt-BR.md) | [Русский](README.ru.md) | [日本語](README.ja.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Bahasa Indonesia](README.id.md) | [Türkçe](README.tr.md) | [한국어](README.ko.md) | [Tiếng Việt](README.vi.md) | [Italiano](README.it.md) | [Polski](README.pl.md) | [繁體中文](README.zh-TW.md)

> यह अनुवाद AI की मदद से किया गया है। मूल स्रोत अंग्रेज़ी [README](../../README.md) है; सुधार के लिए pull request का स्वागत है (देखें [CONTRIBUTING.md](../../CONTRIBUTING.md))।

**अपने खुले Revit मॉडल के बारे में AI से पूछिए। डिफ़ॉल्ट रूप से, जब तक आप किसी योजना को मंज़ूर नहीं करते, लिखने वाले टूल ब्लॉक रहते हैं।**

Revit 2024 – 2027 के लिए ओपन-सोर्स MCP सर्वर और नेटिव ऐड-इन। Claude, Codex और अन्य MCP क्लाइंट के साथ काम करता है।

[![CI](https://img.shields.io/github/actions/workflow/status/Sam-AEC/aec-model-bridge/ci.yml?branch=main&style=flat-square&label=CI)](https://github.com/Sam-AEC/aec-model-bridge/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Sam-AEC/aec-model-bridge?style=flat-square&color=0F766E)](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)
[![Revit](https://img.shields.io/badge/Revit-2024--2027-0696D7?style=flat-square)](#समर्थित-revit-वर्ज़न)
[![License](https://img.shields.io/badge/license-GPL--3.0%20%2B%20commercial-2563EB?style=flat-square)](../../LICENSING.md)

[शुरुआत करें](#क्विक-स्टार्ट) | [वर्कफ़्लो के उदाहरण](#वर्कफ़्लो-के-उदाहरण) | [टूल](../tools-generated.md) | [दस्तावेज़ीकरण](#दस्तावेज़ीकरण) | [डाउनलोड](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)

</div>

<p align="center">
  <img src="../images/readme/revit-villa-panel.png" alt="Revit में विला का मॉडल, बगल में AEC Model Bridge पैनल और Dev मोड चालू है।" width="900">
</p>

AEC Model Bridge ओपन-सोर्स Revit MCP सर्वर है, जिससे Claude, Codex, Cursor और अन्य AI असिस्टेंट आपके खुले Revit मॉडल को पढ़ और बदल सकते हैं, और हर बदलाव पहले आपकी मंज़ूरी से गुज़रता है। इसमें Python MCP सर्वर और नेटिव Revit ऐड-इन साथ आते हैं: रीड-ओनली टूल मॉडल को तुरंत जाँच लेते हैं, और मॉडल में किसी भी बदलाव के लिए डिफ़ॉल्ट रूप से मंज़ूर की हुई योजना ज़रूरी है। [मंज़ूरी की प्रक्रिया देखें](#मंज़ूरी-कैसे-काम-करती-है)।

<p align="center">
  <img src="../images/readme/works-with.svg" alt="इनके साथ काम करता है: Claude Desktop, GitHub Copilot वाले VS Code, Cursor और Codex के लिए सेटअप दस्तावेज़ में दिया गया है। Claude Code, Windsurf, Cline, Continue, Zed और Gemini CLI जैसे अन्य MCP क्लाइंट भी काम करने चाहिए। एप्लिकेशन: Revit 2024 से 2027, Rhino, Grasshopper, Navisworks (विकास जारी)। डेटा: IFC, Speckle, Excel, SQLite। प्रोटोकॉल: मंज़ूरी गेट के साथ stdio पर MCP।" width="900">
</p>

सेटअप Claude Desktop, GitHub Copilot वाले VS Code, Cursor और Codex के लिए दस्तावेज़ में दिया गया है। यह एक मानक MCP stdio सर्वर है, इसलिए Claude Code, Windsurf, Cline, Continue, Zed और Gemini CLI जैसे अन्य क्लाइंट भी काम करने चाहिए। क्या दस्तावेज़ में है और क्या अभी परखा नहीं गया, यह जानने के लिए [संगतता](../compatibility.md) देखें।

इसी सर्वर में IFC जाँच, Rhino और Grasshopper ऑटोमेशन तथा Speckle इंटीग्रेशन भी शामिल हैं। [इंटीग्रेशन की स्थिति](#अन्य-इंटीग्रेशन) बताती है कि कौन-से प्रोवाइडर उपलब्ध हैं और कौन-से अभी बन रहे हैं।

## वर्कफ़्लो के उदाहरण

BIM समन्वयकों के लिए: मॉडल की गुणवत्ता जाँचें, प्रभावित एलिमेंट देखें, पैरामीटर सुधार को मंज़ूरी दें, फिर नतीजे जाँचें और रिपोर्ट एक्सपोर्ट करें। ये उदाहरण [मौजूदा कैटलॉग](../tools-generated.md) के टूल इस्तेमाल करते हैं।

| वर्कफ़्लो | अनुरोध का उदाहरण | इस्तेमाल होने वाले टूल |
| --- | --- | --- |
| मॉडल समीक्षा | "सक्रिय दस्तावेज़ दिखाओ, उसकी चेतावनियाँ सूचीबद्ध करो और प्रभावित एलिमेंट खोजो।" | `revit_get_document_info`, `revit_get_warnings`, `revit_get_elements_by_type` |
| पैरामीटर अपडेट | "Level 02 की दीवारें खोजो, उनके Comments के मान दिखाओ और बैच अपडेट का प्रस्ताव दो।" | `revit_get_elements_by_type`, `revit_get_element_parameters`, `revit_batch_set_parameters` |
| ड्रॉइंग तैयार करना | "इस CSV से शीट सूची तैयार करो, फिर शीट बनाने और व्यू रखने का प्रस्ताव दो।" | `revit_batch_create_sheets_from_csv`, `revit_place_viewport_on_sheet` |
| IFC समीक्षा | "इस IFC फ़ाइल की मंज़िलें दिखाओ, दीवारों की प्रॉपर्टी जाँचो और स्कीमा वैलिडेशन की समस्याएँ बताओ।" | `ifc_get_spatial_structure`, `ifc_get_properties`, `ifc_validate` |

Revit में पहली बार आज़माने के लिए, यह लिखें:

```text
Read the active model's warnings. Group them by description and show the
affected element IDs. Then suggest which issues to investigate first.
```

फिर पैरामीटर सुधार आज़माएँ, और लेवल व मान अपने प्रोजेक्ट के अनुसार बदल लें:

```text
Find walls on Level 02 and show their current Comments values. Propose setting
Comments to "Coordination reviewed" for the elements I choose. After I approve
the plan in Revit, apply it and read the values back to confirm the result.
```

बदलावों के लिए असिस्टेंट `plan_actions` से योजना बनाता है; `execute_plan` उसे लागू करे, इससे पहले आप Revit पैनल में उसकी समीक्षा करते हैं। IFC समीक्षा Revit के बिना चलती है।

स्नैपशॉट आधारित QA/QC और रिपोर्ट मॉड्यूल के लिए एक संगत सेव किया हुआ स्नैपशॉट ज़रूरी है। फ़िलहाल Revit से मॉड्यूल तक स्नैपशॉट पहुँचाने में फ़ाइल नाम और वर्कस्पेस का मेल होना ज़रूरी है; `snapshot_id` छोड़ने पर बनाया हुआ नमूना डेटा लौट सकता है। लाइव जाँच के लिए ऊपर दिए Revit टूल सीधे इस्तेमाल करें। [नियोजित सुधार और डेमो](../roadmap.md)।

## क्विक स्टार्ट

**वन-क्लिक इंस्टॉल**

[![Install in VS Code](https://img.shields.io/badge/Install_in-VS_Code-0098FF?style=for-the-badge)](../install-buttons.md#vs-code)
[![Install in Cursor](https://img.shields.io/badge/Install_in-Cursor-111111?style=for-the-badge)](https://cursor.com/en/install-mcp?name=aec-model-bridge&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyItLWZyb20iLCJnaXQraHR0cHM6Ly9naXRodWIuY29tL1NhbS1BRUMvYWVjLW1vZGVsLWJyaWRnZSNzdWJkaXJlY3Rvcnk9cGFja2FnZXMvbWNwLXNlcnZlci1yZXZpdCIsImFlYy1tb2RlbC1icmlkZ2UiXSwiZW52Ijp7Ik1DUF9SRVZJVF9NT0RFIjoiYnJpZGdlIn19)
[![Claude Desktop bundle](https://img.shields.io/badge/Claude_Desktop-.mcpb_bundle-D97757?style=for-the-badge)](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)

इन बटनों के लिए सिर्फ़ [uv](https://docs.astral.sh/uv/getting-started/installation/) चाहिए, और किसी सेटअप की ज़रूरत नहीं: जब तक आप अपना न चुनें, सर्वर `~/Documents/AEC Model Bridge` को वर्कस्पेस की तरह इस्तेमाल करता है। Claude Desktop के लिए नवीनतम रिलीज़ से `.mcpb` फ़ाइल डाउनलोड करके खोलें। लाइव Revit काम के लिए अब भी Revit और [ऐड-इन](#revit-ऐड-इन-इंस्टॉल-करें) चाहिए; mock मोड को कुछ नहीं चाहिए।

**मैन्युअल सेटअप**

लाइव Revit ऑटोमेशन के लिए आपको Windows, लाइसेंस वाला Revit 2024 से 2027, Python 3.11 या नया, [uv](https://docs.astral.sh/uv/getting-started/installation/) और Revit ऐड-इन चाहिए ([इंस्टॉल के चरण](#revit-ऐड-इन-इंस्टॉल-करें))। फिर इसे अपने `claude_desktop_config.json` में जोड़ें (Codex, Cursor और VS Code यही मान इस्तेमाल करते हैं; दोनों डायरेक्टरी वेरिएबल वैकल्पिक हैं और डिफ़ॉल्ट रूप से ऊपर बताया वर्कस्पेस लेते हैं):

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

पहले बिना Revit के टूल देखना चाहते हैं? `"MCP_REVIT_MODE": "mock"` सेट करें। तब सर्वर कहीं भी चलता है, हर टूल को उसके स्कीमा के साथ सूचीबद्ध करता है और मॉडल को छुए बिना पहले से तय जवाब लौटाता है। इसी mock मोड के लिए एक `Dockerfile` रिपॉज़िटरी के रूट में है (`docker build -t aec-model-bridge .`, फिर `docker run -i --rm aec-model-bridge`)।

VS Code इस्तेमाल करते हैं? [एक्सटेंशन का सोर्स और लोकल इंस्टॉल के चरण](../../extensions/vscode/README.md) MCP सर्वर रजिस्टर करते हैं और Revit कनेक्शन की स्थिति दिखाते हैं। इसे Marketplace पर प्रकाशित नहीं किया गया है।

### टूल एक नज़र में

| क्षेत्र | टूल | क्या करते हैं |
| --- | --- | --- |
| Revit | 110 | मॉडल पढ़ना, एलिमेंट, पैरामीटर, व्यू, शीट, शेड्यूल बनाना और संपादित करना, एक्सपोर्ट, वर्कशेयरिंग |
| मंज़ूरी | 5 | मॉडल बदलावों की योजना बनाना, समीक्षा, मंज़ूरी, निष्पादन और रोलबैक |
| मॉड्यूल | 83 | स्नैपशॉट जाँच, पैरामीटर ग्रिड, QA/QC जाँचें, रेसिपी, रिपोर्ट, सेलेक्शन |
| Rhino और Grasshopper | 19 | ज्यामिति, लेयर, मटीरियल, बूलियन ऑपरेशन |
| Speckle | 17 | प्रोजेक्ट, मॉडल, वर्ज़न, भेजना और प्राप्त करना |
| Navisworks | 15 | मॉडल ट्री, व्यूपॉइंट, क्लैश टेस्ट (विकास जारी) |
| IFC | 7 | Revit के बिना IFC फ़ाइलें पढ़ना: संरचना, प्रॉपर्टी, वैलिडेशन |
| ग्राफ़, स्नैपशॉट, एक्सपोर्ट, जॉब | 21 | सिमेंटिक ग्राफ़ ऑडिट, स्नैपशॉट अंतर, SQLite एक्सपोर्ट, बैकग्राउंड जॉब |

डिफ़ॉल्ट सेटअप में 277 टूल सूचीबद्ध हैं (mock मोड में मौजूदा सर्वर से गिने गए)। APS क्रेडेंशियल कॉन्फ़िगर होने पर Autodesk Data टूल दिखाई देते हैं। [टूल संदर्भ](../tools-generated.md) में हर टूल दिया गया है। हर टूल पर MCP एनोटेशन (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`) होते हैं, ताकि क्लाइंट पढ़ने और लिखने वाले टूल में फ़र्क कर सकें।

### उन्नत Revit ऑटोमेशन

मॉडल क्वेरी और पैरामीटर अपडेट के अलावा, Revit टूल बिल्डिंग एलिमेंट, व्यू, शीट, शेड्यूल, टैग और डाइमेंशन बनाते हैं, और IFC, DWG, इमेज तथा Navisworks फ़ाइलें एक्सपोर्ट करते हैं। समर्थित ऑपरेशन और इनपुट के लिए [टूल संदर्भ](../tools-generated.md) देखें।

जो टूल कैटलॉग में नहीं है, उसके लिए `revit_invoke_method`, `revit_reflect_get` और `revit_reflect_set` सार्वजनिक Revit API सदस्यों के साथ काम करते हैं, और `revit_execute_python` Revit के अंदर IronPython चलाता है। इन उन्नत टूल के अधिकार Revit प्रोसेस जितने ही होते हैं। इन्हें सिर्फ़ उन MCP क्लाइंट और प्रॉम्प्ट के साथ इस्तेमाल करें जिन पर आपको भरोसा है।

## यह कैसे काम करता है

MCP क्लाइंट एक Python हब से बात करता है। हब हर कॉल को उस प्रोवाइडर तक भेजता है जिसके पास वह टूल है। डेस्कटॉप ऐप के प्रोवाइडर localhost के ज़रिए उस ऐप के अंदर के एक छोटे ऐड-इन से बात करते हैं।

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../images/architecture-dark.png">
    <img src="../images/architecture-light.png" alt="AEC Model Bridge का आर्किटेक्चर: Claude या Codex जैसा MCP क्लाइंट Python MCP हब को कॉल करता है, जो टूल कॉल को Revit, Rhino, Navisworks, IFC और Speckle प्रोवाइडर तक पहुँचाता है। Revit और Rhino प्रोवाइडर localhost HTTP के ज़रिए ऐड-इन से बात करते हैं, IFC प्रोवाइडर IfcOpenShell से IFC फ़ाइलें पढ़ता है, और Navisworks अभी विकास में है।" width="900">
  </picture>
</p>

<sub>डायग्राम का स्रोत: [architecture.mmd](../diagrams/architecture.mmd)। इमेज दोबारा बनाने के लिए `python scripts/render_diagrams.py` चलाएँ।</sub>

टील रंग के बॉक्स आज काम करते हैं। एम्बर रंग के डैश वाले बॉक्स अभी बन रहे हैं। इंडिगो आकृतियाँ डेटा और बाहरी सेवाएँ हैं।

### मंज़ूरी कैसे काम करती है

हब मॉडल बदलने वाली हर टूल कॉल को रोक देता है, जब तक उसके साथ मंज़ूर की हुई योजना न हो। डिफ़ॉल्ट मोड `required` है। AI योजना सुझाता है, आप उसे Revit साइड पैनल में देखते हैं, और ऐड-इन उसे Revit के मुख्य थ्रेड पर चलाता है, पैरामीटर और मॉडल-संपादन वाले एक्शन अपने-अपने नामित ट्रांज़ैक्शन में चलते हैं; सेव, सिंक और स्क्रिप्ट एक्शन ऐसे नहीं चलते, इसलिए Ctrl+Z उन्हें कवर नहीं करता।

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/Sam-AEC/aec-model-bridge/main/docs/images/readme/readme-workflow-dark.png">
    <img src="https://raw.githubusercontent.com/Sam-AEC/aec-model-bridge/main/docs/images/readme/readme-workflow-light.png" alt="जाँचें, प्रस्ताव दें, मंज़ूर करें, सत्यापित करें। चार चरण: जाँच में खाली Mark मिलता है, प्रस्ताव में बदलाव का मसौदा बनता है, मंज़ूरी इंसान का फ़ैसला है, और सत्यापन में मान वापस पढ़ा जाता है। दिखाए गए मान उदाहरण के लिए हैं।" width="900">
  </picture>
</p>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../images/approval-flow-dark.png">
    <img src="../images/approval-flow-light.png" alt="मंज़ूरी का प्रवाह: AI असिस्टेंट plan_actions से योजना का मसौदा बनाता है, साइड पैनल प्रस्तावित बदलाव (संख्या, दायरा, पहले और बाद) दिखाता है, और कोई व्यक्ति पैनल में या aec-model-bridge-approve CLI से मंज़ूरी देता है, MCP के ज़रिए कभी नहीं। हब जाँचता है कि योजना मंज़ूर किए गए टूल और आर्गुमेंट से मेल खाती है, और केवल एक बार। फिर Revit हर कार्रवाई को अपने अलग ट्रांज़ैक्शन में चलाता है, इसलिए Ctrl+Z हर बार एक कार्रवाई पूर्ववत करता है। अस्वीकार करने या कभी मंज़ूर न करने पर कॉल रुक जाती है और मॉडल अछूता रहता है।" width="900">
  </picture>
</p>

<sub>डायग्राम का स्रोत: [approval-flow.mmd](../diagrams/approval-flow.mmd)। इमेज दोबारा बनाने के लिए `python scripts/render_diagrams.py` चलाएँ।</sub>

अगर कोई योजना ग़लत निकले, तो Revit में Ctrl+Z से उसे पलटिए। हर पैरामीटर राइट अपना अलग नामित ट्रांज़ैक्शन है, इसलिए एक योजना के लिए कई बार दबाना पड़ सकता है। पूरी योजना को एक ही चरण में पलटने की सुविधा योजना में है, अभी बनी नहीं है। दूसरा रास्ता रिवर्ट योजना है: असिस्टेंट किसी चलाई जा चुकी योजना के प्रूफ़ से `plan_revert` द्वारा उसका मसौदा बनाता है, और आप उसे किसी भी अन्य योजना की तरह मंज़ूर करते हैं। `rollback_plan` केवल इंसानों के लिए है और न कोई बटन है न कोई कमांड, इसलिए उस पर भरोसा न करें। इनमें से कोई भी रास्ता अभी किसी असली Revit सेशन में सत्यापित नहीं हुआ है (UNVERIFIED)। जिन ऑपरेशनों को पलटा नहीं जा सकता, जैसे फ़ाइल आउटपुट, उन्हें इनमें से कोई भी नहीं पलटता, और उनके लिए अभी दूसरी बार पुष्टि नहीं माँगी जाती (योजना में है)। पैनल की Plans सूची केवल लंबित योजनाएँ दिखाती है; `aec-model-bridge-approve show <plan_id>` किसी भी अवस्था की योजना के लिए काम करता है, जबकि `proofs/` बंडल केवल उन्हीं योजनाओं के लिए बनते हैं जो चलाई गईं (या चलाने की कोशिश हुई)। पूरा जीवनचक्र [ADR 0008](../0008-approval-gate-lifecycle.md) में है।

बिना निगरानी वाली पाइपलाइनों के लिए आप `MCP_REVIT_APPROVAL_MODE=auto` सेट कर सकते हैं। इससे इंसान द्वारा की जाने वाली जाँच बंद हो जाती है, इसलिए इसे सिर्फ़ नियंत्रित एनवायरनमेंट में इस्तेमाल करें।

## समर्थित Revit वर्ज़न

| Revit वर्ज़न | ऐड-इन टारगेट | बिल्ड टूल |
|---|---|---|
| 2024 | .NET Framework 4.8 | .NET 8 SDK और .NET Framework 4.8 डेवलपर पैक |
| 2025 | .NET 8 for Windows | .NET 8 SDK |
| 2026 | .NET 8 for Windows | .NET 8 SDK |
| 2027 | .NET 10 for Windows | .NET 10 SDK |

इसके अलावा Windows 10 या 11, Python 3.11 या बाद का वर्ज़न, और आप जो वर्ज़न इस्तेमाल करते हैं उसकी लाइसेंस वाली Revit इंस्टॉलेशन चाहिए। Mock मोड सर्वर को बिना Revit के चलाता है, जो डेवलपमेंट और टेस्ट के लिए उपयोगी है।

### अन्य इंटीग्रेशन

| इंटीग्रेशन | स्थिति |
|---|---|
| Revit | उपलब्ध। नेटिव C# ऐड-इन। |
| IFC (IfcOpenShell) | उपलब्ध। Revit चले बिना IFC फ़ाइलें पढ़ता है। |
| Rhino और Grasshopper | उपलब्ध। `localhost:3004` पर Rhino ऐड-इन से जुड़ता है। |
| Speckle | उपलब्ध। आपके एनवायरनमेंट में Speckle क्लाइंट ID चाहिए। |
| Navisworks Manage | विकास जारी। प्रोवाइडर और उसके टूल रजिस्टर हैं। Navisworks ऐड-इन अधूरा है। |
| Power BI | विकास जारी। प्रोवाइडर और टूल मौजूद हैं, पर हब में रजिस्टर नहीं हैं। |
| Excel, Parquet और DuckDB | नियोजित। |

उत्पादों के नाम और लोगो उनके मालिकों के हैं। बैनर में इनका उपयोग सिर्फ़ यह दिखाने के लिए है कि यह प्रोजेक्ट किनके साथ काम करता है।

## Revit ऐड-इन इंस्टॉल करें

**सबसे आसान तरीका (Windows):** [नवीनतम रिलीज़](https://github.com/Sam-AEC/aec-model-bridge/releases/latest) से `AECModelBridge-Setup-<version>.exe` डाउनलोड करें, उस पर डबल-क्लिक करें, अपने Revit वर्ज़न चुनें और Revit दोबारा शुरू करें। यह ऐड-इन, साथ आया Python सर्वर और, अगर आप बॉक्स चुनें, तो Claude Desktop व VS Code की सेटिंग इंस्टॉल करता है, और आपकी मौजूदा सेटिंग का बैकअप भी रखता है। अनइंस्टॉल Windows सेटिंग से करें। नीचे के चरण सोर्स से बिल्ड करने के लिए हैं।

आप दो हिस्से इंस्टॉल करते हैं: Python MCP सर्वर और Revit ऐड-इन। लाइव Revit ऑटोमेशन के लिए दोनों चाहिए।

### 1. MCP सर्वर इंस्टॉल करें

```powershell
git clone https://github.com/Sam-AEC/aec-model-bridge.git
cd aec-model-bridge

py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e packages/mcp-server-revit
```

### 2. Revit ऐड-इन इंस्टॉल करें

वर्ज़न को अपनी Revit इंस्टॉलेशन के अनुसार सेट करें। अगर Windows डाउनलोड की गई स्क्रिप्ट रोके, तो हर `.ps1` फ़ाइल पर राइट-क्लिक करें, Properties खोलें और चलाने से पहले Unblock चुनें।

```powershell
$RevitVersion = Read-Host "Revit year (2024, 2025, 2026, or 2027)"

.\scripts\package.ps1 -RevitVersion $RevitVersion
.\scripts\install.ps1 -RevitVersion $RevitVersion
```

इंस्टॉलर वर्ज़न-विशेष बाइनरी यहाँ रखता है:

```text
C:\ProgramData\AECModelBridge\bin\<year>
```

ऐड-इन मैनिफ़ेस्ट हर उपयोगकर्ता के लिए अलग से यहाँ इंस्टॉल होता है:

```text
%APPDATA%\Autodesk\Revit\Addins\<year>
```

मैनिफ़ेस्ट को इसके बजाय `C:\ProgramData\Autodesk\Revit\Addins\<year>` में इंस्टॉल करने के लिए `install.ps1` के साथ `-AllUsers` इस्तेमाल करें।

सभी समर्थित वर्ज़न की बाइनरी एक बार में तैयार करने के लिए:

```powershell
.\scripts\package.ps1 -RevitVersion All
```

हर [GitHub रिलीज़](https://github.com/Sam-AEC/aec-model-bridge/releases/latest) में हर Revit वर्ष के लिए बना-बनाया पैकेज होता है, जैसे `aec-model-bridge-revit-2026-<version>.zip`। सोर्स से बिल्ड करने के बजाय उसे अनज़िप करें और `.\install.ps1 -RevitVersion 2026` चलाएँ। डबल-क्लिक वाले Windows इंस्टॉलर के लिए `scripts/build-installer.ps1` Inno Setup से एक बनाता है। समस्या-निवारण सहित पूरी गाइड [docs/install.md](../install.md) में है।

## Claude Desktop को Revit से जोड़ें

सर्वर को अपने MCP क्लाइंट की कॉन्फ़िगरेशन में जोड़ें। Claude Desktop में यह `claude_desktop_config.json` का `mcpServers` भाग है। Codex, Cursor, VS Code और अन्य MCP क्लाइंट अपने-अपने कॉन्फ़िग फ़ॉर्मैट में यही `command`, `args` और `env` मान इस्तेमाल करते हैं।

अपने वर्चुअल एनवायरनमेंट का Python एक्ज़ीक्यूटेबल इस्तेमाल करें, और ऐसा वर्कस्पेस फ़ोल्डर चुनें जिस तक सर्वर पहुँच सके:

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

सबसे नए खुले Revit इंस्टेंस को चुनने के लिए `MCP_REVIT_HOST_VERSION` छोड़ दें। किसी क्लाइंट एंट्री को एक Revit वर्ज़न पर लॉक करने के लिए उसे `2024` या `2026` जैसे वर्ष पर सेट करें। उन्नत सेटअप में `MCP_REVIT_BRIDGE_URL` एंडपॉइंट बदल देता है।

VS Code उपयोगकर्ता [`.vscode/mcp.json`](../../.vscode/mcp.json) से शुरू कर सकते हैं। Hermes Desktop उपयोगकर्ता प्लेसहोल्डर Python पाथ बदलने के बाद [`docs/examples/hermes-desktop.json`](../examples/hermes-desktop.json) से शुरू कर सकते हैं। MCP Bundles समर्थित क्लाइंट [नवीनतम रिलीज़](https://github.com/Sam-AEC/aec-model-bridge/releases/latest) से `.mcpb` फ़ाइल इंस्टॉल कर सकते हैं। Revit ऐड-इन फिर भी ज़रूरी है, क्योंकि सर्वर चल रहे डेस्कटॉप ऐप से बात करता है।

### कनेक्शन जाँचें

ऐड-इन इंस्टॉल करने के बाद Revit दोबारा शुरू करें, कोई मॉडल खोलें और चलाएँ:

```powershell
$registry = Get-ChildItem "$env:LOCALAPPDATA\AECModelBridge\registry\revit-*.json" | Select-Object -First 1
$switch = Get-Content $registry.FullName -Raw | ConvertFrom-Json
Invoke-RestMethod "$($switch.endpoint)/health"
```

जवाब में `healthy` और चल रहे Revit का वर्ज़न दिखना चाहिए। Revit में `AEC Bridge` रिबन टैब देखें। इसके Workflows पैनल में Open Panel, Health Check, Pending Actions और Reports हैं। इसके Tools पैनल में Config, Help और About हैं।

## सुरक्षा

- Revit ब्रिज सिर्फ़ localhost पर सुनता है।
- सर्वर सिर्फ़ `MCP_REVIT_ALLOWED_DIRECTORIES` में दिए फ़ोल्डरों के अंदर पढ़ता और लिखता है।
- मॉडल बदलने वाले टूल को मंज़ूर की हुई योजना चाहिए, जब तक आप मंज़ूरी बंद न करें।
- टूल कॉल ऑडिट लॉग में दर्ज होती हैं, और गोपनीय जानकारी छिपा दी जाती है।

विवरण [docs/security.md](../security.md) में हैं। किसी सुरक्षा कमज़ोरी की रिपोर्ट करने के लिए [SECURITY.md](../../SECURITY.md) का पालन करें।

## अक्सर पूछे जाने वाले सवाल

### Revit के लिए MCP सर्वर क्या है?

Model Context Protocol (MCP) एक ओपन स्टैंडर्ड है जो AI असिस्टेंट को दूसरे सॉफ़्टवेयर के टूल कॉल करने देता है। Revit का MCP सर्वर Revit के ऑपरेशन को टूल के रूप में उपलब्ध कराता है। असिस्टेंट टूल चुनता है, और ऐड-इन उन्हें Revit के अंदर चलाता है।

### कौन-से AI असिस्टेंट इसके साथ काम करते हैं?

कोई भी MCP क्लाइंट जो लोकल stdio सर्वर शुरू कर सके। हमने Claude Desktop, GitHub Copilot वाले VS Code, Cursor और Codex, तथा मानक `mcpServers` कॉन्फ़िगरेशन पढ़ने वाले क्लाइंट के सेटअप का दस्तावेज़ तैयार किया है। Windsurf, Cline, Roo Code, Continue, Zed, Claude Code और Gemini CLI को भी इसी तरह काम करना चाहिए, पर इन्हें परखा नहीं गया है। [संगतता](../compatibility.md) देखें। पैनल चैट Anthropic API कुंजी, या इंस्टॉल होने पर `claude` या `codex` कमांड-लाइन टूल भी इस्तेमाल कर सकती है। [ADR 0012](../0012-native-agent-chat-backend.md) देखें।

### क्या AI बिना पूछे मेरा मॉडल बदल सकता है?

डिफ़ॉल्ट मोड में नहीं। मॉडल बदलने वाले टूल तब तक रुके रहते हैं जब तक Revit पैनल में योजना मंज़ूर न हो। रीड-ओनली टूल बिना मंज़ूरी के चलते हैं। अगर आप `MCP_REVIT_APPROVAL_MODE=auto` सेट करते हैं, तो मंज़ूरी छोड़ दी जाती है।

### क्या यह मेरा मॉडल क्लाउड पर भेजता है?

सर्वर और ऐड-इन आपकी मशीन पर चलते हैं, और ब्रिज localhost पर सुनता है। AI असिस्टेंट क्या देखता है, यह आपके इस्तेमाल किए क्लाइंट पर निर्भर है: टूल के नतीजे उस क्लाइंट के मॉडल प्रोवाइडर को जाते हैं। Speckle जैसे क्लाउड से जुड़े प्रोवाइडर तभी चलते हैं जब आप उन्हें कॉन्फ़िगर करें और उनके टूल कॉल करें।

### क्या यह Revit के बिना IFC फ़ाइलों के साथ काम करता है?

हाँ। IFC प्रोवाइडर IfcOpenShell से फ़ाइलें पढ़ता है। यह फ़ाइल मेटाडेटा, स्थानिक संरचना, एलिमेंट प्रॉपर्टी और बाउंडिंग बॉक्स लौटा सकता है, क्लास, GUID, नाम या प्रॉपर्टी से क्वेरी चला सकता है और स्कीमा वैलिडेट कर सकता है। यह IFC फ़ाइलें संपादित नहीं करता।

### क्या मैं इसे Revit इंस्टॉल किए बिना इस्तेमाल कर सकता हूँ?

डेवलपमेंट और टेस्ट के लिए आप सर्वर को mock मोड में चला सकते हैं। लाइव मॉडल काम के लिए Revit 2024 से 2027 और ऐड-इन चाहिए।

## रिलीज़ और वर्ज़न

AEC Model Bridge सिमेंटिक वर्ज़निंग का पालन करता है। रिलीज़ GitHub पर `vX.Y.Z` टैग से चिह्नित होती हैं, और रूट की `VERSION` फ़ाइल में वर्ज़न नंबर रहता है। रिलीज़ प्रक्रिया के लिए [docs/versioning.md](../versioning.md) और हर वर्ज़न में क्या बदला, यह जानने के लिए [CHANGELOG.md](../../CHANGELOG.md) देखें।

## डेवलपमेंट

```powershell
# Python tests
python -m pytest packages/mcp-server-revit/tests

# Build one Revit version, for example 2026
.\scripts\build-addin.ps1 -RevitVersion 2026 -Configuration Release

# Build all supported versions
.\scripts\package.ps1 -RevitVersion All
```

CI Python सर्वर और Revit 2024 से 2027 के ऐड-इन टारगेट बिल्ड करता है। pull request खोलने से पहले [CONTRIBUTING.md](../../CONTRIBUTING.md) पढ़ें।

## दस्तावेज़ीकरण

- [इंस्टॉलेशन गाइड](../install.md)
- [टूल संदर्भ](../tools-generated.md)
- [आर्किटेक्चर](../0001-multi-provider-architecture.md)
- [कॉन्फ़िगरेशन संदर्भ](../configuration-reference.md)
- [सुरक्षा](../security.md)
- [MCP क्लाइंट और रजिस्ट्री](../marketplaces.md)
- [वर्ज़निंग और रिलीज़](../versioning.md)
- [सभी दस्तावेज़](../README.md)
- [योगदान गाइड](../../CONTRIBUTING.md) और [आचार संहिता](../../CODE_OF_CONDUCT.md)
- [योगदानकर्ता](../../CONTRIBUTORS.md)

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

## प्रोजेक्ट और लाइसेंस

[A. Sam Mohammad](https://github.com/Sam-AEC) द्वारा संचालित।
[LinkedIn](https://www.linkedin.com/in/a-sam-mohammad-92790416b) |
[Issues](https://github.com/Sam-AEC/aec-model-bridge/issues)

[Revit Linking Exception के साथ GPL-3.0-or-later, या व्यावसायिक लाइसेंस](../../LICENSING.md)।
