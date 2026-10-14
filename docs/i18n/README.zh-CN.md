<div align="center">

<img src="../../assets/logo.svg" alt="AEC Model Bridge logo: an isometric model cube with a bridge arch" height="120">

[English](../../README.md) | **简体中文** | [Español](README.es.md) | [हिन्दी](README.hi.md) | [العربية](README.ar.md) | [Português (BR)](README.pt-BR.md) | [Русский](README.ru.md) | [日本語](README.ja.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Bahasa Indonesia](README.id.md) | [Türkçe](README.tr.md) | [한국어](README.ko.md) | [Tiếng Việt](README.vi.md) | [Italiano](README.it.md) | [Polski](README.pl.md) | [繁體中文](README.zh-TW.md)

> 本文为 AI 辅助翻译。内容以英文版 [README](../../README.md) 为准；发现错误或有改进建议，欢迎通过 Pull Request 提交，详见 [CONTRIBUTING.md](../../CONTRIBUTING.md)。

**就你当前打开的 Revit 模型向 AI 提问。默认情况下，在你批准计划之前，写入类工具会被拦截。**

面向 Revit 2024 – 2027 的开源 MCP 服务器和原生插件，可与 Claude、Codex 及其他 MCP 客户端配合使用。

[![CI](https://img.shields.io/github/actions/workflow/status/Sam-AEC/aec-model-bridge/ci.yml?branch=main&style=flat-square&label=CI)](https://github.com/Sam-AEC/aec-model-bridge/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Sam-AEC/aec-model-bridge?style=flat-square&color=0F766E)](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)
[![Revit](https://img.shields.io/badge/Revit-2024--2027-0696D7?style=flat-square)](#支持的-revit-版本)
[![License](https://img.shields.io/badge/license-GPL--3.0%20%2B%20commercial-2563EB?style=flat-square)](../../LICENSING.md)

[快速开始](#快速开始) | [示例工作流](#示例工作流) | [工具](../tools-generated.md) | [文档](#文档) | [下载](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)

</div>

<p align="center">
  <img src="../images/readme/revit-villa-panel.png" alt="Revit 别墅模型位于 AEC Model Bridge 面板旁，Dev 模式已开启。" width="900">
</p>

AEC Model Bridge 是开源的 Revit MCP 服务器，让 Claude、Codex、Cursor 等 AI 助手读取并编辑你正在打开的 Revit 模型，且每一项变更都须先经你批准。它由 Python MCP 服务器和原生 Revit 插件组成：只读工具可立即检查模型，而默认情况下，模型变更必须有已批准的计划。[查看审批流程](#审批如何运作)。

<p align="center">
  <img src="../images/readme/works-with.svg" alt="兼容：Claude Desktop、搭配 GitHub Copilot 的 VS Code、Cursor 和 Codex 已有设置文档。Claude Code、Windsurf、Cline、Continue、Zed 和 Gemini CLI 等其他 MCP 客户端应当也能使用。应用程序：Revit 2024 至 2027、Rhino、Grasshopper、Navisworks（开发中）。数据：IFC、Speckle、Excel、SQLite。协议：带审批关卡的 stdio MCP。" width="900">
</p>

已提供 Claude Desktop、搭配 GitHub Copilot 的 VS Code、Cursor 和 Codex 的设置文档。它是标准的 MCP stdio 服务器，因此 Claude Code、Windsurf、Cline、Continue、Zed 和 Gemini CLI 等其他客户端应当也能使用。哪些已有文档、哪些尚未测试，请参阅[兼容性说明](../compatibility.md)。

同一个服务器还包含 IFC 检查、Rhino 与 Grasshopper 自动化以及 Speckle 集成。[集成状态](#其他集成)区分了已可用的提供程序和仍在开发中的部分。

## 示例工作流

面向 BIM 协调人员：检查模型质量，审阅受影响的构件，批准参数修复，然后核对结果并导出报告。
这些示例使用[当前工具目录](../tools-generated.md)中的工具。

| 工作流 | 示例请求 | 使用的工具 |
| --- | --- | --- |
| 模型审查 | "显示当前文档，列出其警告并找出受影响的构件。" | `revit_get_document_info`, `revit_get_warnings`, `revit_get_elements_by_type` |
| 参数更新 | "查找 Level 02 上的墙，显示其 Comments 参数值，并提议批量更新。" | `revit_get_elements_by_type`, `revit_get_element_parameters`, `revit_batch_set_parameters` |
| 出图 | "根据这个 CSV 准备图纸列表，然后提议创建图纸并放置视图。" | `revit_batch_create_sheets_from_csv`, `revit_place_viewport_on_sheet` |
| IFC 审查 | "显示这个 IFC 文件的楼层，检查墙的属性，并报告模式校验问题。" | `ifc_get_spatial_structure`, `ifc_get_properties`, `ifc_validate` |

首次在 Revit 中试用，可以这样提问：

```text
Read the active model's warnings. Group them by description and show the
affected element IDs. Then suggest which issues to investigate first.
```

然后试试修正参数，请将标高和值替换为你项目中的实际内容：

```text
Find walls on Level 02 and show their current Comments values. Propose setting
Comments to "Coordination reviewed" for the elements I choose. After I approve
the plan in Revit, apply it and read the values back to confirm the result.
```

对于修改操作，助手会用 `plan_actions` 创建计划；你在 Revit 面板中审阅后，`execute_plan` 才会执行。IFC 审查无需 Revit 即可运行。

快照 QA/QC 和报告模块需要兼容的已保存快照。目前从 Revit 到模块的快照交接需要文件名和工作区保持一致；省略 `snapshot_id` 可能会返回生成的示例数据。实时检查请使用上面的 Revit 直接工具。[计划中的修复与演示](../roadmap.md)。

## 快速开始

**一键安装**

[![Install in VS Code](https://img.shields.io/badge/Install_in-VS_Code-0098FF?style=for-the-badge)](../install-buttons.md#vs-code)
[![Install in Cursor](https://img.shields.io/badge/Install_in-Cursor-111111?style=for-the-badge)](https://cursor.com/en/install-mcp?name=aec-model-bridge&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyItLWZyb20iLCJnaXQraHR0cHM6Ly9naXRodWIuY29tL1NhbS1BRUMvYWVjLW1vZGVsLWJyaWRnZSNzdWJkaXJlY3Rvcnk9cGFja2FnZXMvbWNwLXNlcnZlci1yZXZpdCIsImFlYy1tb2RlbC1icmlkZ2UiXSwiZW52Ijp7Ik1DUF9SRVZJVF9NT0RFIjoiYnJpZGdlIn19)
[![Claude Desktop bundle](https://img.shields.io/badge/Claude_Desktop-.mcpb_bundle-D97757?style=for-the-badge)](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)

这些按钮只需要 [uv](https://docs.astral.sh/uv/getting-started/installation/)，无需其他设置：除非你另行指定，服务器会使用 `~/Documents/AEC Model Bridge` 作为工作区。使用 Claude Desktop 时，请从最新发布版本下载 `.mcpb` 文件并打开。实际操作 Revit 仍需安装 Revit 和[插件](#安装-revit-插件)；mock 模式则无需任何依赖。

**手动设置**

要进行实时 Revit 自动化，你需要 Windows、已授权的 Revit 2024 至 2027、Python 3.11 或更新版本、[uv](https://docs.astral.sh/uv/getting-started/installation/)以及 Revit 插件（[安装步骤](#安装-revit-插件)）。然后将以下内容添加到 `claude_desktop_config.json`（Codex、Cursor 和 VS Code 使用相同的值；两个目录变量是可选的，默认使用上述工作区）：

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

想先在没有 Revit 的情况下看看这些工具？请设置 `"MCP_REVIT_MODE": "mock"`。服务器可在任何机器上启动，列出所有工具及其 schema，并返回预设的响应，而不会触碰任何模型。仓库根目录提供了同样用于 mock 模式的 `Dockerfile`（`docker build -t aec-model-bridge .`，然后 `docker run -i --rm aec-model-bridge`）。

使用 VS Code？[扩展源码和本地安装步骤](../../extensions/vscode/README.md)会注册 MCP 服务器并显示 Revit 连接状态。该扩展尚未发布到 Marketplace。

### 工具一览

| 领域 | 工具数 | 功能 |
| --- | --- | --- |
| Revit | 103 | 读取模型，创建和编辑构件、参数、视图、图纸、明细表，导出，工作共享 |
| 审批 | 6 | 规划、审阅、批准、执行并回滚模型变更 |
| 模块 | 34 | 快照检查、参数网格、QA/QC 检查、配方、报告、选择集 |
| Rhino 与 Grasshopper | 19 | 几何体、图层、材质、布尔运算 |
| Speckle | 17 | 项目、模型、版本、发送与接收 |
| Navisworks | 15 | 模型树、视点、碰撞测试（开发中） |
| IFC | 7 | 无需 Revit 即可读取 IFC 文件：结构、属性、校验 |
| 图谱、快照、导出、作业 | 18 | 语义图谱审计、快照差异比对、SQLite 导出、后台作业 |

默认配置下共列出 219 个工具（在 mock 模式下统计自当前服务器）。配置 APS 凭据后会出现 Autodesk Data 工具。[工具参考](../tools-generated.md)列出了所有工具。每个工具都带有 MCP 注解（`readOnlyHint`、`destructiveHint`、`idempotentHint`、`openWorldHint`），客户端据此区分读取和写入。

### 高级 Revit 自动化

除了模型查询和参数更新，Revit 工具还可以创建建筑构件、视图、图纸、明细表、标记和尺寸标注，并导出 IFC、DWG、图像和 Navisworks 文件。支持的操作和输入请参阅[工具参考](../tools-generated.md)。

对于工具目录未覆盖的需求，`revit_invoke_method`、`revit_reflect_get` 和 `revit_reflect_set` 可操作公开的 Revit API 成员，`revit_execute_python` 则在 Revit 内运行 IronPython。这些高级工具拥有与 Revit 进程相同的权限，请仅配合你信任的 MCP 客户端和提示词使用。

## 工作原理

MCP 客户端与一个 Python hub 通信。hub 将每次调用转发给拥有该工具的提供程序。面向桌面应用的提供程序通过 localhost 与该应用内的小型插件通信。

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../images/architecture-dark.png">
    <img src="../images/architecture-light.png" alt="Architecture of AEC Model Bridge: an MCP client such as Claude or Codex calls the Python MCP hub, which routes tool calls to the Revit, Rhino, Navisworks, IFC and Speckle providers. The Revit and Rhino providers talk to add-ins over localhost HTTP, the IFC provider reads IFC files with IfcOpenShell, and Navisworks is still in progress." width="900">
  </picture>
</p>

<sub>图表源文件：[architecture.mmd](../diagrams/architecture.mmd)。使用 `python scripts/render_diagrams.py` 重新生成图片。</sub>

青色方框表示已可用，琥珀色虚线方框表示开发中，靛蓝色形状表示数据和外部服务。

### 审批如何运作

hub 会拦截任何会修改模型的工具调用，除非它附带已批准的计划。默认模式为 `required`。AI 提出计划，你在 Revit 侧边面板中审阅，然后插件在 Revit 主线程中执行，参数和模型编辑类操作各自在独立的命名事务（transaction）中运行；保存、同步和脚本类操作则不是，因此 Ctrl+Z 无法撤销它们。

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

<sub>图表源文件：[approval-flow.mmd](../diagrams/approval-flow.mmd)。使用 `python scripts/render_diagrams.py` 重新生成图片。</sub>

如果计划有误，请在 Revit 中用 Ctrl+Z 撤销。每次参数写入都是各自独立的命名事务，因此一个计划可能需要按多次。整个计划一步撤销的功能已列入计划，尚未实现。第二种方式是还原计划：助手根据已执行计划的凭证，用 `plan_revert` 起草一个新计划，再像批准其他计划一样批准它。`rollback_plan` 仅供人使用，既不是按钮也不是命令，因此不要指望它。这些方式目前都尚未在真实的 Revit 会话中验证（UNVERIFIED）。无法撤销的操作（例如文件输出）这些方式都无法撤销，目前也尚未要求再次确认（已列入计划）。面板的 Plans 列表只显示待处理的计划；`aec-model-bridge-approve show <plan_id>` 适用于任何状态的计划，而 `proofs/` 包只存在于已执行（或尝试执行）的计划。完整生命周期见 [ADR 0008](../0008-approval-gate-lifecycle.md)。

对于无人值守的流水线，可以设置 `MCP_REVIT_APPROVAL_MODE=auto`。这会关闭人工检查，因此请仅在受控环境中使用。

## 支持的 Revit 版本

| Revit 版本 | 插件目标框架 | 构建工具 |
|---|---|---|
| 2024 | .NET Framework 4.8 | .NET 8 SDK 和 .NET Framework 4.8 开发者包 |
| 2025 | .NET 8 for Windows | .NET 8 SDK |
| 2026 | .NET 8 for Windows | .NET 8 SDK |
| 2027 | .NET 10 for Windows | .NET 10 SDK |

你还需要 Windows 10 或 11、Python 3.11 或更新版本，以及所用版本的已授权 Revit。Mock 模式无需 Revit 即可运行服务器，适合开发和测试。

### 其他集成

| 集成 | 状态 |
|---|---|
| Revit | 可用。原生 C# 插件。 |
| IFC (IfcOpenShell) | 可用。无需运行 Revit 即可读取 IFC 文件。 |
| Rhino 与 Grasshopper | 可用。连接到位于 `localhost:3004` 的 Rhino 插件。 |
| Speckle | 可用。需要在环境中提供 Speckle 客户端 ID。 |
| Navisworks Manage | 开发中。提供程序及其工具已注册，Navisworks 插件尚未完成。 |
| Power BI | 开发中。提供程序和工具已存在，但尚未在 hub 中注册。 |
| Excel、Parquet 与 DuckDB | 计划中。 |

产品名称和徽标归其各自所有者所有。横幅使用它们，仅用于说明本项目可配合哪些产品使用。

## 安装 Revit 插件

**最简单的方式（Windows）：**从[最新发布版本](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)下载 `AECModelBridge-Setup-<version>.exe`，双击运行，选择你的 Revit 版本并重启 Revit。它会安装插件、内置的 Python 服务器，如果勾选相应选项，还会写入 Claude Desktop 和 VS Code 设置，并备份你当前的设置。可在 Windows 设置中卸载。以下步骤用于从源码构建。

需要安装两部分：Python MCP 服务器和 Revit 插件。实时 Revit 自动化两者缺一不可。

### 1. 安装 MCP 服务器

```powershell
git clone https://github.com/Sam-AEC/aec-model-bridge.git
cd aec-model-bridge

py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e packages/mcp-server-revit
```

### 2. 安装 Revit 插件

将版本设置为与你安装的 Revit 一致。如果 Windows 阻止了下载的脚本，请右键单击每个 `.ps1` 文件，打开“属性”，在运行前选择“解除锁定”。

```powershell
$RevitVersion = Read-Host "Revit year (2024, 2025, 2026, or 2027)"

.\scripts\package.ps1 -RevitVersion $RevitVersion
.\scripts\install.ps1 -RevitVersion $RevitVersion
```

安装程序会将对应版本的二进制文件放在：

```text
C:\ProgramData\AECModelBridge\bin\<year>
```

插件清单按用户安装在：

```text
%APPDATA%\Autodesk\Revit\Addins\<year>
```

在 `install.ps1` 中使用 `-AllUsers`，可改为将清单安装到 `C:\ProgramData\Autodesk\Revit\Addins\<year>`。

一次性为所有受支持的版本准备二进制文件：

```powershell
.\scripts\package.ps1 -RevitVersion All
```

每个 [GitHub 发布版本](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)都为每个 Revit 年份提供现成的安装包，例如 `aec-model-bridge-revit-2026-<version>.zip`。解压后运行 `.\install.ps1 -RevitVersion 2026`，即可免去从源码构建。如需双击运行的 Windows 安装程序，`scripts/build-installer.ps1` 可使用 Inno Setup 构建。包含故障排查的完整指南见 [docs/install.md](../install.md)。

## 将 Claude Desktop 连接到 Revit

将服务器添加到你的 MCP 客户端配置中。对于 Claude Desktop，即 `claude_desktop_config.json` 的 `mcpServers` 部分。Codex、Cursor、VS Code 和其他 MCP 客户端在各自的配置格式中使用相同的 `command`、`args` 和 `env` 值。

请使用虚拟环境中的 Python 可执行文件，并选择服务器可访问的工作区文件夹：

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

省略 `MCP_REVIT_HOST_VERSION` 时，将连接最新打开的 Revit 实例。将其设置为 `2024` 或 `2026` 等年份，可将该客户端条目锁定到对应的 Revit 版本。`MCP_REVIT_BRIDGE_URL` 可在高级配置中覆盖端点。

VS Code 用户可以从 [`.vscode/mcp.json`](../../.vscode/mcp.json) 开始。Hermes Desktop 用户在替换占位的 Python 路径后，可以从 [`docs/examples/hermes-desktop.json`](../examples/hermes-desktop.json) 开始。支持 MCP Bundles 的客户端可以从[最新发布版本](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)安装 `.mcpb` 文件。由于服务器要与正在运行的桌面应用通信，仍然需要 Revit 插件。

### 检查连接

安装插件后重启 Revit，打开一个模型，然后运行：

```powershell
$registry = Get-ChildItem "$env:LOCALAPPDATA\AECModelBridge\registry\revit-*.json" | Select-Object -First 1
$switch = Get-Content $registry.FullName -Raw | ConvertFrom-Json
Invoke-RestMethod "$($switch.endpoint)/health"
```

响应应报告 `healthy` 以及正在运行的 Revit 版本。在 Revit 中查找 `AEC Bridge` 功能区选项卡。其 Workflows 面板包含 Open Panel、Health Check、Pending Actions 和 Reports；Tools 面板包含 Config、Help 和 About。

## 安全

- Revit 桥接仅监听 localhost。
- 服务器仅在 `MCP_REVIT_ALLOWED_DIRECTORIES` 所列文件夹内读写。
- 除非关闭审批，否则会修改模型的工具都需要已批准的计划。
- 工具调用会写入审计日志，并对机密信息脱敏。

详情见 [docs/security.md](../security.md)。如需报告漏洞，请遵循 [SECURITY.md](../../SECURITY.md)。

## 常见问题

### Revit 的 MCP 服务器是什么？

Model Context Protocol（MCP）是一项开放标准，让 AI 助手能够调用其他软件中的工具。Revit 的 MCP 服务器将 Revit 的操作发布为工具。助手选择工具，插件在 Revit 内运行它们。

### 哪些 AI 助手可以使用？

任何能够启动本地 stdio 服务器的 MCP 客户端。我们为 Claude Desktop、搭配 GitHub Copilot 的 VS Code、Cursor 和 Codex，以及读取标准 `mcpServers` 配置的客户端提供了文档。Windsurf、Cline、Roo Code、Continue、Zed、Claude Code 和 Gemini CLI 应当也能以同样方式工作，但尚未测试。参见[兼容性说明](../compatibility.md)。面板聊天也可以使用 Anthropic API 密钥，或已安装的 `claude` 或 `codex` 命令行工具。参见 [ADR 0012](../0012-native-agent-chat-backend.md)。

### AI 会未经询问就修改我的模型吗？

默认模式下不会。修改模型的工具会被阻止，直到计划在 Revit 面板中获得批准。只读工具无需批准即可运行。如果设置 `MCP_REVIT_APPROVAL_MODE=auto`，则会跳过审批。

### 它会把我的模型发送到云端吗？

服务器和插件都在你的机器上运行，桥接仅监听 localhost。AI 助手能看到什么取决于你使用的客户端：工具结果会发送给该客户端的模型提供方。面向云端的提供程序（如 Speckle）只有在你配置并调用其工具时才会运行。

### 没有 Revit 也能处理 IFC 文件吗？

可以。IFC 提供程序使用 IfcOpenShell 读取文件。它可以返回文件元数据、空间结构、构件属性和包围盒，按类、GUID、名称或属性执行查询，并校验模式。它不会编辑 IFC 文件。

### 没有安装 Revit 可以使用吗？

你可以在 mock 模式下运行服务器，用于开发和测试。实际的模型操作需要 Revit 2024 至 2027 和插件。

## 发布与版本

AEC Model Bridge 遵循语义化版本（Semantic Versioning）。发布版本在 GitHub 上以 `vX.Y.Z` 打标签，根目录的 `VERSION` 文件保存版本号。发布流程见 [docs/versioning.md](../versioning.md)，各版本的变更见 [CHANGELOG.md](../../CHANGELOG.md)。

## 开发

```powershell
# Python tests
python -m pytest packages/mcp-server-revit/tests

# Build one Revit version, for example 2026
.\scripts\build-addin.ps1 -RevitVersion 2026 -Configuration Release

# Build all supported versions
.\scripts\package.ps1 -RevitVersion All
```

CI 会构建 Python 服务器以及面向 Revit 2024 至 2027 的插件目标。提交 Pull Request 之前请先阅读 [CONTRIBUTING.md](../../CONTRIBUTING.md)。

## 文档

- [安装指南](../install.md)
- [工具参考](../tools-generated.md)
- [架构](../0001-multi-provider-architecture.md)
- [配置参考](../configuration-reference.md)
- [安全](../security.md)
- [MCP 客户端与注册表](../marketplaces.md)
- [版本与发布](../versioning.md)
- [全部文档](../README.md)
- [贡献指南](../../CONTRIBUTING.md) 和 [行为准则](../../CODE_OF_CONDUCT.md)
- [贡献者](../../CONTRIBUTORS.md)

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

## 项目与许可证

由 [A. Sam Mohammad](https://github.com/Sam-AEC) 维护。
[LinkedIn](https://www.linkedin.com/in/a-sam-mohammad-92790416b) |
[Issues](https://github.com/Sam-AEC/aec-model-bridge/issues)

[GPL-3.0-or-later 并附 Revit Linking Exception，或商业许可证](../../LICENSING.md)。
