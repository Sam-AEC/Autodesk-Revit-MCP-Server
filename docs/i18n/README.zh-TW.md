<div align="center">

<img src="../../assets/logo.svg" alt="AEC Model Bridge logo: an isometric model cube with a bridge arch" height="120">

[English](../../README.md) | [简体中文](README.zh-CN.md) | [Español](README.es.md) | [हिन्दी](README.hi.md) | [العربية](README.ar.md) | [Português (BR)](README.pt-BR.md) | [Русский](README.ru.md) | [日本語](README.ja.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Bahasa Indonesia](README.id.md) | [Türkçe](README.tr.md) | [한국어](README.ko.md) | [Tiếng Việt](README.vi.md) | [Italiano](README.it.md) | [Polski](README.pl.md) | **繁體中文**

> 本文由 AI 輔助翻譯。內容以英文版 [README](../../README.md) 為準；若發現錯誤或有改進建議，歡迎透過 Pull Request 提出，詳見 [CONTRIBUTING.md](../../CONTRIBUTING.md)。

**就你開啟中的 Revit 模型向 AI 提問。預設情況下，在你核准計畫之前，寫入類工具會被攔截。**

適用於 Revit 2024 – 2027 的開源 MCP 伺服器與原生增益集，可搭配 Claude、Codex 及其他 MCP 用戶端使用。

[![CI](https://img.shields.io/github/actions/workflow/status/Sam-AEC/aec-model-bridge/ci.yml?branch=main&style=flat-square&label=CI)](https://github.com/Sam-AEC/aec-model-bridge/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Sam-AEC/aec-model-bridge?style=flat-square&color=0F766E)](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)
[![Revit](https://img.shields.io/badge/Revit-2024--2027-0696D7?style=flat-square)](#支援的-revit-版本)
[![License](https://img.shields.io/badge/license-GPL--3.0%20%2B%20commercial-2563EB?style=flat-square)](../../LICENSING.md)

[快速開始](#快速開始) | [範例工作流程](#範例工作流程) | [工具](../tools-generated.md) | [文件](#文件) | [下載](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)

</div>

<p align="center">
  <img src="../images/readme/revit-villa-panel.png" alt="Revit 別墅模型位於 AEC Model Bridge 面板旁，Dev 模式已開啟。" width="900">
</p>

AEC Model Bridge 是開源的 Revit MCP 伺服器，讓 Claude、Codex、Cursor 等 AI 助理讀取並編輯你開啟中的 Revit 模型，且每一項變更都須先經你核准。它結合 Python MCP 伺服器與原生 Revit 增益集：唯讀工具可立即檢查模型，而模型的任何變更預設都必須有已核准的計畫。[查看核准流程](#核准如何運作)。

<p align="center">
  <img src="../images/readme/works-with.svg" alt="相容：Claude Desktop、搭配 GitHub Copilot 的 VS Code、Cursor 與 Codex 已有設定文件。Claude Code、Windsurf、Cline、Continue、Zed 與 Gemini CLI 等其他 MCP 用戶端應該也能使用。應用程式：Revit 2024 至 2027、Rhino、Grasshopper、Navisworks（開發中）。資料：IFC、Speckle、Excel、SQLite。通訊協定：附核准關卡的 stdio MCP。" width="900">
</p>

已提供 Claude Desktop、搭配 GitHub Copilot 的 VS Code、Cursor 與 Codex 的設定文件。它是標準的 MCP stdio 伺服器，因此 Claude Code、Windsurf、Cline、Continue、Zed 與 Gemini CLI 等其他用戶端應該也能使用。哪些已有文件、哪些尚未測試，請參閱[相容性說明](../compatibility.md)。

同一個伺服器還包含 IFC 檢查、Rhino 與 Grasshopper 自動化，以及 Speckle 整合。[整合狀態](#其他整合)會區分哪些提供者已可使用、哪些仍在開發中。

## 範例工作流程

適用於 BIM 協調人員：檢查模型品質、檢視受影響的元件、核准參數修正，接著確認結果並匯出報告。這些範例使用[目前工具目錄](../tools-generated.md)中的工具。

| 工作流程 | 範例請求 | 使用的工具 |
| --- | --- | --- |
| 模型檢視 | "顯示目前的文件，列出其警告並找出受影響的元件。" | `revit_get_document_info`, `revit_get_warnings`, `revit_get_elements_by_type` |
| 參數更新 | "找出 Level 02 的牆，顯示它們的 Comments 值，並提出批次更新的建議。" | `revit_get_elements_by_type`, `revit_get_element_parameters`, `revit_batch_set_parameters` |
| 圖面製作 | "根據這份 CSV 準備圖紙清單，然後建議建立圖紙並放置視圖。" | `revit_batch_create_sheets_from_csv`, `revit_place_viewport_on_sheet` |
| IFC 檢視 | "顯示這個 IFC 檔案的樓層，檢查牆的屬性，並回報結構描述驗證的問題。" | `ifc_get_spatial_structure`, `ifc_get_properties`, `ifc_validate` |

第一次在 Revit 中試用時，可以這樣下指令：

```text
Read the active model's warnings. Group them by description and show the
affected element IDs. Then suggest which issues to investigate first.
```

接著試試修正參數，並將樓層與數值換成你專案中的內容：

```text
Find walls on Level 02 and show their current Comments values. Propose setting
Comments to "Coordination reviewed" for the elements I choose. After I approve
the plan in Revit, apply it and read the values back to confirm the result.
```

需要修改時，助理會用 `plan_actions` 建立計畫；你先在 Revit 面板中檢視，`execute_plan` 才會套用。IFC 檢視不需要 Revit 即可執行。

快照型的 QA/QC 與報告模組需要相容且已儲存的快照。目前從 Revit 將快照交給模組時，檔名與工作區必須一致；省略 `snapshot_id` 可能會回傳產生的範例資料。即時檢查請直接使用上述 Revit 工具。[規劃中的修正與示範](../roadmap.md)。

## 快速開始

**一鍵安裝**

[![Install in VS Code](https://img.shields.io/badge/Install_in-VS_Code-0098FF?style=for-the-badge)](../install-buttons.md#vs-code)
[![Install in Cursor](https://img.shields.io/badge/Install_in-Cursor-111111?style=for-the-badge)](https://cursor.com/en/install-mcp?name=aec-model-bridge&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyItLWZyb20iLCJnaXQraHR0cHM6Ly9naXRodWIuY29tL1NhbS1BRUMvYWVjLW1vZGVsLWJyaWRnZSNzdWJkaXJlY3Rvcnk9cGFja2FnZXMvbWNwLXNlcnZlci1yZXZpdCIsImFlYy1tb2RlbC1icmlkZ2UiXSwiZW52Ijp7Ik1DUF9SRVZJVF9NT0RFIjoiYnJpZGdlIn19)
[![Claude Desktop bundle](https://img.shields.io/badge/Claude_Desktop-.mcpb_bundle-D97757?style=for-the-badge)](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)

這些按鈕只需要 [uv](https://docs.astral.sh/uv/getting-started/installation/)，不需其他設定：除非你自行指定，否則伺服器會使用 `~/Documents/AEC Model Bridge` 作為工作區。使用 Claude Desktop 時，請從最新版本下載 `.mcpb` 檔案並開啟。要即時操作 Revit，仍需要 Revit 與[增益集](#安裝-revit-增益集)；mock 模式則什麼都不需要。

**手動設定**

若要進行 Revit 即時自動化，你需要 Windows、已授權的 Revit 2024 至 2027、Python 3.11 或更新版本、[uv](https://docs.astral.sh/uv/getting-started/installation/)，以及 Revit 增益集（[安裝步驟](#安裝-revit-增益集)）。然後將下列內容加入 `claude_desktop_config.json`（Codex、Cursor 與 VS Code 使用相同的值；兩個目錄變數為選用，預設為上述工作區）：

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

想先在沒有 Revit 的情況下看看這些工具嗎？請設定 `"MCP_REVIT_MODE": "mock"`。伺服器可在任何地方啟動，列出所有工具及其結構描述，並回傳預先準備的回應，完全不會碰觸任何模型。同樣用於 mock 模式的 `Dockerfile` 位於儲存庫根目錄（`docker build -t aec-model-bridge .`，然後 `docker run -i --rm aec-model-bridge`）。

使用 VS Code 嗎？[擴充功能原始碼與本機安裝步驟](../../extensions/vscode/README.md)會註冊 MCP 伺服器並顯示 Revit 連線狀態。此擴充功能尚未發布到 Marketplace。

### 工具總覽

| 領域 | 工具數 | 功能 |
| --- | --- | --- |
| Revit | 103 | 讀取模型，建立與編輯元件、參數、視圖、圖紙、明細表，匯出，工作共享(worksharing) |
| 核准 | 6 | 規劃、檢視、核准、執行並復原模型變更 |
| 模組 | 34 | 快照檢查、參數表格、QA/QC 檢查、配方、報告、選取集 |
| Rhino 與 Grasshopper | 19 | 幾何、圖層、材質、布林運算 |
| Speckle | 17 | 專案、模型、版本、傳送與接收 |
| Navisworks | 15 | 模型樹、視點、碰撞檢查（開發中） |
| IFC | 7 | 無需 Revit 即可讀取 IFC 檔案：結構、屬性、驗證 |
| 圖譜、快照、匯出、作業 | 18 | 語意圖譜稽核、快照差異比對、SQLite 匯出、背景作業 |

預設設定下共列出 219 個工具（在 mock 模式下由目前的伺服器統計）。設定 APS 憑證後，Autodesk Data 工具才會出現。[工具參考](../tools-generated.md)列出所有工具。每個工具都帶有 MCP 註解（`readOnlyHint`、`destructiveHint`、`idempotentHint`、`openWorldHint`），讓用戶端能分辨讀取與寫入。

### 進階 Revit 自動化

除了模型查詢與參數更新，Revit 工具還能建立建築元件、視圖、圖紙、明細表、標記與尺寸標註，並匯出 IFC、DWG、圖片與 Navisworks 檔案。支援的操作與輸入請參閱[工具參考](../tools-generated.md)。

對於工具目錄未涵蓋的需求，`revit_invoke_method`、`revit_reflect_get` 與 `revit_reflect_set` 可操作公開的 Revit API 成員，`revit_execute_python` 則會在 Revit 內執行 IronPython。這些進階工具擁有與 Revit 程序相同的權限，請只搭配你信任的 MCP 用戶端與提示詞使用。

## 運作方式

MCP 用戶端與一個 Python hub 溝通。hub 會把每次呼叫轉送給擁有該工具的提供者。桌面應用程式的提供者則透過 localhost，與該應用程式內的小型增益集溝通。

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../images/architecture-dark.png">
    <img src="../images/architecture-light.png" alt="Architecture of AEC Model Bridge: an MCP client such as Claude or Codex calls the Python MCP hub, which routes tool calls to the Revit, Rhino, Navisworks, IFC and Speckle providers. The Revit and Rhino providers talk to add-ins over localhost HTTP, the IFC provider reads IFC files with IfcOpenShell, and Navisworks is still in progress." width="900">
  </picture>
</p>

<sub>圖表來源：[architecture.mmd](../diagrams/architecture.mmd)。使用 `python scripts/render_diagrams.py` 重新產生圖片。</sub>

青綠色方框表示目前已可運作，琥珀色虛線方框表示開發中，靛藍色形狀則是資料與外部服務。

### 核准如何運作

除非附有已核准的計畫，否則 hub 會攔下任何會變更模型的工具呼叫。預設模式為 `required`。AI 提出計畫，你在 Revit 側邊面板中檢視，接著增益集會在 Revit 主執行緒中執行，參數與模型編輯類動作各自在獨立的具名交易（transaction）中運行；儲存、同步與腳本類動作則不是，因此 Ctrl+Z 無法復原它們。

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/Sam-AEC/aec-model-bridge/main/docs/images/readme/readme-workflow-dark.png">
    <img src="https://raw.githubusercontent.com/Sam-AEC/aec-model-bridge/main/docs/images/readme/readme-workflow-light.png" alt="Inspect, Propose, Approve, Verify. Four steps: inspect finds an empty Mark, propose drafts a change, approve is a human decision, verify reads the value back. Example values are illustrative." width="900">
  </picture>
</p>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../images/approval-flow-dark.png">
    <img src="../images/approval-flow-light.png" alt="Approval flow: the AI assistant drafts a plan with plan_actions, the side panel shows the proposed changes (counts, scope, before and after), and a human approves in the panel or with the aec-model-bridge-approve CLI, never over MCP. The hub checks that the plan matches the approved tool and arguments, once only. Revit then runs each action in its own transaction, so Ctrl+Z undoes one action per press. If you reject or never approve, the call is blocked and the model stays untouched." width="900">
  </picture>
</p>

<sub>圖表來源：[approval-flow.mmd](../diagrams/approval-flow.mmd)。使用 `python scripts/render_diagrams.py` 重新產生圖片。</sub>

若計畫有誤，請在 Revit 中用 Ctrl+Z 復原。每次參數寫入都是各自獨立的具名交易，因此一個計畫可能需要按多次。整個計畫一步復原的功能已列入規劃，尚未實作。第二種方式是還原計畫：助理根據已執行計畫的憑證，以 `plan_revert` 起草一個新計畫，再像核准其他計畫一樣核准它。`rollback_plan` 僅供人使用，既不是按鈕也不是指令，因此不要指望它。這些方式目前都尚未在真實的 Revit 工作階段中驗證（UNVERIFIED）。無法復原的操作（例如檔案輸出）這些方式都無法復原，目前也尚未要求再次確認（已列入規劃）。面板的 Plans 清單只顯示待處理的計畫；`aec-model-bridge-approve show <plan_id>` 適用於任何狀態的計畫，而 `proofs/` 套件只存在於已執行（或嘗試執行）的計畫。完整生命週期請見 [ADR 0008](../0008-approval-gate-lifecycle.md)。

對於無人值守的流程，可以設定 `MCP_REVIT_APPROVAL_MODE=auto`。這會關閉人工檢查，因此請只在受控環境中使用。

## 支援的 Revit 版本

| Revit 版本 | 增益集目標 | 建置工具 |
|---|---|---|
| 2024 | .NET Framework 4.8 | .NET 8 SDK 與 .NET Framework 4.8 開發人員套件 |
| 2025 | .NET 8 for Windows | .NET 8 SDK |
| 2026 | .NET 8 for Windows | .NET 8 SDK |
| 2027 | .NET 10 for Windows | .NET 10 SDK |

你還需要 Windows 10 或 11、Python 3.11 或更新版本，以及所用版本的已授權的 Revit。Mock 模式可在沒有 Revit 的情況下執行伺服器，適合用於開發與測試。

### 其他整合

| 整合 | 狀態 |
|---|---|
| Revit | 可使用。原生 C# 增益集。 |
| IFC (IfcOpenShell) | 可使用。無需執行 Revit 即可讀取 IFC 檔案。 |
| Rhino 與 Grasshopper | 可使用。連接到位於 `localhost:3004` 的 Rhino 增益集。 |
| Speckle | 可使用。需要在環境中提供 Speckle 用戶端 ID。 |
| Navisworks Manage | 開發中。提供者及其工具已註冊，Navisworks 增益集尚未完成。 |
| Power BI | 開發中。提供者與工具已存在，但尚未在 hub 中註冊。 |
| Excel、Parquet 與 DuckDB | 規劃中。 |

產品名稱與標誌屬於其各自的擁有者。橫幅使用它們，僅用於說明本專案可搭配哪些產品使用。

## 安裝 Revit 增益集

**最簡單的方式（Windows）：**從[最新版本](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)下載 `AECModelBridge-Setup-<version>.exe`，按兩下執行，選擇你的 Revit 版本並重新啟動 Revit。它會安裝增益集、內建的 Python 伺服器，若勾選相關選項，還會寫入 Claude Desktop 與 VS Code 設定，並備份你目前的設定。可從 Windows 設定中解除安裝。以下步驟適用於從原始碼建置。

你需要安裝兩個部分：Python MCP 伺服器與 Revit 增益集。Revit 即時自動化兩者缺一不可。

### 1. 安裝 MCP 伺服器

```powershell
git clone https://github.com/Sam-AEC/aec-model-bridge.git
cd aec-model-bridge

py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e packages/mcp-server-revit
```

### 2. 安裝 Revit 增益集

請將版本設為與你安裝的 Revit 相同。如果 Windows 封鎖了下載的指令碼，請在每個 `.ps1` 檔案上按一下滑鼠右鍵，開啟「內容」，執行前先選取「解除封鎖」。

```powershell
$RevitVersion = Read-Host "Revit year (2024, 2025, 2026, or 2027)"

.\scripts\package.ps1 -RevitVersion $RevitVersion
.\scripts\install.ps1 -RevitVersion $RevitVersion
```

安裝程式會將各版本專用的二進位檔放在：

```text
C:\ProgramData\AECModelBridge\bin\<year>
```

增益集資訊清單(manifest)會依使用者安裝在：

```text
%APPDATA%\Autodesk\Revit\Addins\<year>
```

在 `install.ps1` 加上 `-AllUsers`，可改為將資訊清單安裝到 `C:\ProgramData\Autodesk\Revit\Addins\<year>`。

一次準備所有支援版本的二進位檔：

```powershell
.\scripts\package.ps1 -RevitVersion All
```

每個 [GitHub 版本](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)都為每個 Revit 年份提供現成的套件，例如 `aec-model-bridge-revit-2026-<version>.zip`。解壓縮後執行 `.\install.ps1 -RevitVersion 2026`，即可省去從原始碼建置。如需按兩下即可安裝的 Windows 安裝程式，`scripts/build-installer.ps1` 可使用 Inno Setup 建置。含疑難排解的完整指南請見 [docs/install.md](../install.md)。

## 將 Claude Desktop 連接到 Revit

將伺服器加入你的 MCP 用戶端設定。以 Claude Desktop 而言，就是 `claude_desktop_config.json` 的 `mcpServers` 區段。Codex、Cursor、VS Code 與其他 MCP 用戶端會在各自的設定格式中使用相同的 `command`、`args` 與 `env` 值。

請使用虛擬環境中的 Python 執行檔，並選擇伺服器可存取的工作區資料夾：

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

省略 `MCP_REVIT_HOST_VERSION` 時，會連接最新開啟的 Revit 執行個體。將它設為 `2024` 或 `2026` 等年份，可把該用戶端項目鎖定在對應的 Revit 版本。`MCP_REVIT_BRIDGE_URL` 可在進階設定中覆寫端點。

VS Code 使用者可以從 [`.vscode/mcp.json`](../../.vscode/mcp.json) 開始。Hermes Desktop 使用者在替換預留位置的 Python 路徑後，可以從 [`docs/examples/hermes-desktop.json`](../examples/hermes-desktop.json) 開始。支援 MCP Bundles 的用戶端可從[最新版本](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)安裝 `.mcpb` 檔案。由於伺服器要與執行中的桌面應用程式溝通，仍然需要 Revit 增益集。

### 檢查連線

安裝增益集後重新啟動 Revit，開啟一個模型，然後執行：

```powershell
$registry = Get-ChildItem "$env:LOCALAPPDATA\AECModelBridge\registry\revit-*.json" | Select-Object -First 1
$switch = Get-Content $registry.FullName -Raw | ConvertFrom-Json
Invoke-RestMethod "$($switch.endpoint)/health"
```

回應應顯示 `healthy` 與執行中的 Revit 版本。在 Revit 中尋找 `AEC Bridge` 功能區索引標籤。其 Workflows 面板包含 Open Panel、Health Check、Pending Actions 與 Reports；Tools 面板包含 Config、Help 與 About。

## 安全性

- Revit 橋接只在 localhost 上監聽。
- 伺服器只會在 `MCP_REVIT_ALLOWED_DIRECTORIES` 所列的資料夾內讀寫。
- 除非關閉核准，否則會變更模型的工具都需要已核准的計畫。
- 工具呼叫會寫入稽核記錄，機密資訊會被遮蔽。

詳細資訊請見 [docs/security.md](../security.md)。若要通報安全漏洞，請依照 [SECURITY.md](../../SECURITY.md) 的說明。

## 常見問題

### Revit 的 MCP 伺服器是什麼？

Model Context Protocol（MCP）是一項開放標準，讓 AI 助理能夠呼叫其他軟體中的工具。Revit 的 MCP 伺服器會把 Revit 的操作發布為工具。助理挑選工具，增益集則在 Revit 內執行。

### 哪些 AI 助理可以搭配使用？

任何能啟動本機 stdio 伺服器的 MCP 用戶端都可以。我們為 Claude Desktop、搭配 GitHub Copilot 的 VS Code、Cursor 與 Codex，以及讀取標準 `mcpServers` 設定的用戶端提供了文件。Windsurf、Cline、Roo Code、Continue、Zed、Claude Code 與 Gemini CLI 應該也能以相同方式運作，但尚未測試。請參閱[相容性說明](../compatibility.md)。面板聊天也可以使用 Anthropic API 金鑰，或已安裝的 `claude`、`codex` 命令列工具。請參閱 [ADR 0012](../0012-native-agent-chat-backend.md)。

### AI 會在沒有詢問的情況下更動我的模型嗎？

預設模式下不會。會變更模型的工具在計畫於 Revit 面板中核准前會被擋下。唯讀工具不需核准即可執行。若設定 `MCP_REVIT_APPROVAL_MODE=auto`，則會略過核准。

### 它會把我的模型傳送到雲端嗎？

伺服器與增益集都在你的電腦上執行，橋接只在 localhost 上監聽。AI 助理能看到什麼，取決於你使用的用戶端：工具的結果會傳送給該用戶端的模型提供者。像 Speckle 這類連向雲端的提供者，只有在你設定並呼叫其工具時才會執行。

### 沒有 Revit 也能處理 IFC 檔案嗎？

可以。IFC 提供者使用 IfcOpenShell 讀取檔案。它可以回傳檔案中繼資料、空間結構、元件屬性與邊界框，依類別、GUID、名稱或屬性執行查詢，並驗證結構描述。它不會編輯 IFC 檔案。

### 沒有安裝 Revit 也能使用嗎？

你可以在 mock 模式下執行伺服器，用於開發與測試。實際操作模型則需要 Revit 2024 至 2027 與增益集。

## 發行與版本

AEC Model Bridge 遵循語意化版本（Semantic Versioning）。發行版本在 GitHub 上以 `vX.Y.Z` 標記，根目錄的 `VERSION` 檔案存放版本號碼。發行流程請見 [docs/versioning.md](../versioning.md)，各版本的異動請見 [CHANGELOG.md](../../CHANGELOG.md)。

## 開發

```powershell
# Python tests
python -m pytest packages/mcp-server-revit/tests

# Build one Revit version, for example 2026
.\scripts\build-addin.ps1 -RevitVersion 2026 -Configuration Release

# Build all supported versions
.\scripts\package.ps1 -RevitVersion All
```

CI 會建置 Python 伺服器，以及適用於 Revit 2024 至 2027 的增益集目標。開啟 Pull Request 之前，請先閱讀 [CONTRIBUTING.md](../../CONTRIBUTING.md)。

## 文件

- [安裝指南](../install.md)
- [工具參考](../tools-generated.md)
- [架構](../0001-multi-provider-architecture.md)
- [設定參考](../configuration-reference.md)
- [安全性](../security.md)
- [MCP 用戶端與登錄表](../marketplaces.md)
- [版本與發行](../versioning.md)
- [全部文件](../README.md)
- [貢獻指南](../../CONTRIBUTING.md) 與 [行為準則](../../CODE_OF_CONDUCT.md)
- [貢獻者](../../CONTRIBUTORS.md)

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

## 專案與授權

由 [A. Sam Mohammad](https://github.com/Sam-AEC) 維護。
[LinkedIn](https://www.linkedin.com/in/a-sam-mohammad-92790416b) |
[Issues](https://github.com/Sam-AEC/aec-model-bridge/issues)

[GPL-3.0-or-later 並附 Revit Linking Exception，或商業授權](../../LICENSING.md)。
