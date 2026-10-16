<div align="center">

<img src="../../assets/logo.svg" alt="AEC Model Bridge logo: an isometric model cube with a bridge arch" height="120">

[English](../../README.md) | [简体中文](README.zh-CN.md) | [Español](README.es.md) | [हिन्दी](README.hi.md) | [العربية](README.ar.md) | [Português (BR)](README.pt-BR.md) | [Русский](README.ru.md) | **日本語** | [Deutsch](README.de.md) | [Français](README.fr.md) | [Bahasa Indonesia](README.id.md) | [Türkçe](README.tr.md) | [한국어](README.ko.md) | [Tiếng Việt](README.vi.md) | [Italiano](README.it.md) | [Polski](README.pl.md) | [繁體中文](README.zh-TW.md)

> この文書は AI の支援で翻訳されたものです。内容は英語版の [README](../../README.md) が正であり、誤りや改善点があれば Pull Request でお寄せください。詳しくは [CONTRIBUTING.md](../../CONTRIBUTING.md) をご覧ください。

**開いている Revit モデルについて AI に質問できます。デフォルトでは、プランを承認するまで書き込みツールはブロックされます。**

Revit 2024 – 2027 向けのオープンソースの MCP サーバーとネイティブアドイン。Claude、Codex などの MCP クライアントで使えます。

[![CI](https://img.shields.io/github/actions/workflow/status/Sam-AEC/aec-model-bridge/ci.yml?branch=main&style=flat-square&label=CI)](https://github.com/Sam-AEC/aec-model-bridge/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Sam-AEC/aec-model-bridge?style=flat-square&color=0F766E)](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)
[![Revit](https://img.shields.io/badge/Revit-2024--2027-0696D7?style=flat-square)](#対応する-revit-バージョン)
[![License](https://img.shields.io/badge/license-GPL--3.0%20%2B%20commercial-2563EB?style=flat-square)](../../LICENSING.md)

[はじめに](#クイックスタート) | [ワークフローの例](#ワークフローの例) | [ツール](../tools-generated.md) | [ドキュメント](#ドキュメント) | [ダウンロード](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)

</div>

<p align="center">
  <img src="../images/readme/revit-villa-panel.png" alt="Dev モードが有効な AEC Model Bridge パネルの横に表示された Revit のヴィラモデル。" width="900">
</p>

AEC Model Bridge は、Claude、Codex、Cursor などの AI アシスタントが、開いている Revit モデルを読み取り・編集できるようにするオープンソースの Revit MCP サーバーです。変更はすべて、先にあなたが承認します。Python 製の MCP サーバーとネイティブの Revit アドインで構成され、読み取り専用ツールはすぐにモデルを調査でき、モデルの変更にはデフォルトで承認済みのプランが必要です。[承認フローを見る](#承認の仕組み)。

<p align="center">
  <img src="../images/readme/works-with.svg" alt="対応：Claude Desktop、GitHub Copilot を併用する VS Code、Cursor、Codex はセットアップ手順があります。Claude Code、Windsurf、Cline、Continue、Zed、Gemini CLI などの他の MCP クライアントも動作するはずです。アプリケーション：Revit 2024～2027、Rhino、Grasshopper、Navisworks（開発中）。データ：IFC、Speckle、Excel、SQLite。プロトコル：承認ゲート付きの stdio 経由 MCP。" width="900">
</p>

セットアップ手順を用意しているのは、Claude Desktop、GitHub Copilot を併用する VS Code、Cursor、Codex です。標準的な MCP の stdio サーバーなので、Claude Code、Windsurf、Cline、Continue、Zed、Gemini CLI などの他のクライアントでも動作するはずです。ドキュメント化されている範囲と未検証の範囲は[互換性](../compatibility.md)をご覧ください。

同じサーバーに、IFC の検査、Rhino と Grasshopper の自動化、Speckle 連携も含まれます。[連携の状況](#その他の連携)で、利用可能なプロバイダーと開発中のものを区別しています。

## ワークフローの例

BIM コーディネーター向け：モデルの品質を調べ、影響を受ける要素を確認し、パラメータの修正を承認してから、結果を検証してレポートを書き出します。これらの例は[現行のカタログ](../tools-generated.md)にあるツールを使います。

| ワークフロー | リクエスト例 | 使用するツール |
| --- | --- | --- |
| モデルレビュー | "アクティブなドキュメントを表示し、警告を一覧にして、影響を受ける要素を見つけて。" | `revit_get_document_info`, `revit_get_warnings`, `revit_get_elements_by_type` |
| パラメータの更新 | "Level 02 の壁を探して Comments の値を表示し、一括更新を提案して。" | `revit_get_elements_by_type`, `revit_get_element_parameters`, `revit_batch_set_parameters` |
| 図面作成 | "この CSV からシートリストを作成し、シートの作成とビューの配置を提案して。" | `revit_batch_create_sheets_from_csv`, `revit_place_viewport_on_sheet` |
| IFC レビュー | "この IFC ファイルの階を表示し、壁のプロパティを調べ、スキーマ検証の問題を報告して。" | `ifc_get_spatial_structure`, `ifc_get_properties`, `ifc_validate` |

Revit で最初に試すなら、次のように依頼します。

```text
Read the active model's warnings. Group them by description and show the
affected element IDs. Then suggest which issues to investigate first.
```

続いてパラメータの修正を試します。レベルと値はプロジェクトに合わせて置き換えてください。

```text
Find walls on Level 02 and show their current Comments values. Propose setting
Comments to "Coordination reviewed" for the elements I choose. After I approve
the plan in Revit, apply it and read the values back to confirm the result.
```

編集では、アシスタントが `plan_actions` でプランを作成します。`execute_plan` が適用する前に、Revit のパネルで内容を確認します。IFC のレビューは Revit なしで実行できます。

スナップショットの QA/QC とレポートのモジュールには、互換性のある保存済みスナップショットが必要です。現在、Revit からモジュールへのスナップショットの受け渡しでは、ファイル名とワークスペースの整合が必要です。`snapshot_id` を省略すると、生成されたサンプルデータが返されることがあります。ライブの調査には、上記の Revit 用ツールを直接使ってください。[今後の修正とデモ](../roadmap.md)。

## クイックスタート

**ワンクリックインストール**

[![Install in VS Code](https://img.shields.io/badge/Install_in-VS_Code-0098FF?style=for-the-badge)](../install-buttons.md#vs-code)
[![Install in Cursor](https://img.shields.io/badge/Install_in-Cursor-111111?style=for-the-badge)](https://cursor.com/en/install-mcp?name=aec-model-bridge&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyItLWZyb20iLCJnaXQraHR0cHM6Ly9naXRodWIuY29tL1NhbS1BRUMvYWVjLW1vZGVsLWJyaWRnZSNzdWJkaXJlY3Rvcnk9cGFja2FnZXMvbWNwLXNlcnZlci1yZXZpdCIsImFlYy1tb2RlbC1icmlkZ2UiXSwiZW52Ijp7Ik1DUF9SRVZJVF9NT0RFIjoiYnJpZGdlIn19)
[![Claude Desktop bundle](https://img.shields.io/badge/Claude_Desktop-.mcpb_bundle-D97757?style=for-the-badge)](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)

ボタンに必要なのは [uv](https://docs.astral.sh/uv/getting-started/installation/) だけで、他の設定は不要です。独自に指定しない限り、サーバーは `~/Documents/AEC Model Bridge` をワークスペースとして使います。Claude Desktop の場合は、最新リリースから `.mcpb` ファイルをダウンロードして開きます。実際に Revit を操作するには、Revit と[アドイン](#revit-アドインのインストール)が必要です。モックモードには何も必要ありません。

**手動セットアップ**

ライブの Revit 自動化には、Windows、ライセンスのある Revit 2024〜2027、Python 3.11 以降、[uv](https://docs.astral.sh/uv/getting-started/installation/)、そして Revit アドインが必要です（[インストール手順](#revit-アドインのインストール)）。そのうえで、次を `claude_desktop_config.json` に追加します（Codex、Cursor、VS Code でも同じ値を使います。2 つのディレクトリ変数は任意で、省略すると上記のワークスペースが使われます）。

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

まず Revit なしでツールを確認したい場合は、`"MCP_REVIT_MODE": "mock"` を設定します。サーバーはどの環境でも起動し、すべてのツールをスキーマ付きで一覧表示し、モデルには触れずに定型のレスポンスを返します。同じモックモード用の `Dockerfile` がリポジトリのルートにあります（`docker build -t aec-model-bridge .` のあと `docker run -i --rm aec-model-bridge`）。

VS Code をお使いですか？[拡張機能のソースとローカルへのインストール手順](../../extensions/vscode/README.md)で、MCP サーバーの登録と Revit の接続状態の表示ができます。Marketplace では公開されていません。

### ツール一覧

| 分野 | ツール数 | できること |
| --- | --- | --- |
| Revit | 110 | モデルの読み取り、要素・パラメータ・ビュー・シート・集計表の作成と編集、エクスポート、ワークシェアリング |
| 承認 | 5 | モデル変更の計画、レビュー、承認、実行、ロールバック |
| モジュール | 83 | スナップショットの検査、パラメータグリッド、QA/QC チェック、レシピ、レポート、選択 |
| Rhino と Grasshopper | 19 | ジオメトリ、レイヤー、マテリアル、ブーリアン演算 |
| Speckle | 17 | プロジェクト、モデル、バージョン、送信と受信 |
| Navisworks | 15 | モデルツリー、ビューポイント、干渉チェック（開発中） |
| IFC | 7 | Revit なしで IFC ファイルを読み取り：構造、プロパティ、検証 |
| グラフ、スナップショット、エクスポート、ジョブ | 21 | セマンティックグラフの監査、スナップショットの差分、SQLite へのエクスポート、バックグラウンドジョブ |

デフォルト構成では 277 個のツールが一覧に表示されます（モックモードで現行サーバーから集計）。Autodesk Data のツールは、APS の認証情報を設定すると表示されます。[ツールリファレンス](../tools-generated.md)にすべてのツールを掲載しています。各ツールには MCP アノテーション（`readOnlyHint`、`destructiveHint`、`idempotentHint`、`openWorldHint`）が付いており、クライアントは読み取りと書き込みを区別できます。

### Revit 自動化の応用

モデルの照会やパラメータの更新に加えて、Revit のツールは建築要素、ビュー、シート、集計表、タグ、寸法を作成し、IFC、DWG、画像、Navisworks ファイルを書き出せます。対応する操作と入力については[ツールリファレンス](../tools-generated.md)をご覧ください。

ツールカタログにないものには、`revit_invoke_method`、`revit_reflect_get`、`revit_reflect_set` が公開されている Revit API のメンバーを操作し、`revit_execute_python` が Revit 内で IronPython を実行します。これらの高度なツールは Revit プロセスと同じ権限を持ちます。信頼できる MCP クライアントとプロンプトでのみ使ってください。

## 仕組み

MCP クライアントは 1 つの Python ハブと通信します。ハブは各呼び出しを、そのツールを担当するプロバイダーに振り分けます。デスクトップアプリ向けのプロバイダーは、localhost 経由でそのアプリ内の小さなアドインと通信します。

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../images/architecture-dark.png">
    <img src="../images/architecture-light.png" alt="Architecture of AEC Model Bridge: an MCP client such as Claude or Codex calls the Python MCP hub, which routes tool calls to the Revit, Rhino, Navisworks, IFC and Speckle providers. The Revit and Rhino providers talk to add-ins over localhost HTTP, the IFC provider reads IFC files with IfcOpenShell, and Navisworks is still in progress." width="900">
  </picture>
</p>

<sub>図のソース：[architecture.mmd](../diagrams/architecture.mmd)。画像は `python scripts/render_diagrams.py` で再生成できます。</sub>

ティールの箱は現在動作するもの、アンバーの破線の箱は開発中のもの、インディゴの図形はデータと外部サービスです。

### 承認の仕組み

ハブは、承認済みのプランを伴わない限り、モデルを変更するツール呼び出しをすべて止めます。デフォルトのモードは `required` です。AI がプランを提案し、あなたが Revit のサイドパネルで確認すると、アドインが Revit のメインスレッド上で実行します。パラメータ編集やモデル編集のアクションはそれぞれ個別の名前付きトランザクションですが、保存・同期・スクリプトのアクションはそうではないため、Ctrl+Z では戻せません。

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

<sub>図のソース：[approval-flow.mmd](../diagrams/approval-flow.mmd)。画像は `python scripts/render_diagrams.py` で再生成できます。</sub>

プランが誤りだと分かった場合は、Revit の Ctrl+Z で元に戻してください。パラメータの書き込みはそれぞれ個別の名前付きトランザクションなので、1 つのプランで複数回押す必要があることがあります。プラン全体を 1 ステップで元に戻す機能は計画中で、まだ実装されていません。もう 1 つの方法は取り消しプランです。アシスタントが実行済みプランの証跡から `plan_revert` で作成し、ほかのプランと同様に承認します。`rollback_plan` は人専用で、ボタンでもコマンドでもないため、あてにしないでください。これらのいずれの方法も、実際の Revit セッションではまだ検証されていません（UNVERIFIED）。ファイル出力など元に戻せない操作はどの方法でも戻せず、再度の確認もまだ求めません（計画中）。パネルの Plans 一覧に表示されるのは保留中のプランだけです。`aec-model-bridge-approve show <plan_id>` はどの状態のプランでも使えますが、`proofs/` のバンドルは実行された（または実行を試みた）プランにしか存在しません。ライフサイクルは [ADR 0008](../0008-approval-gate-lifecycle.md) をご覧ください。

無人で動かすパイプラインでは `MCP_REVIT_APPROVAL_MODE=auto` を設定できます。これは人による確認を無効にするため、管理された環境でのみ使ってください。

## 対応する Revit バージョン

| Revit バージョン | アドインのターゲット | ビルドツール |
|---|---|---|
| 2024 | .NET Framework 4.8 | .NET 8 SDK と .NET Framework 4.8 Developer Pack |
| 2025 | .NET 8 for Windows | .NET 8 SDK |
| 2026 | .NET 8 for Windows | .NET 8 SDK |
| 2027 | .NET 10 for Windows | .NET 10 SDK |

このほか、Windows 10 または 11、Python 3.11 以降、使用するバージョンのライセンス済み Revit が必要です。モックモードでは Revit なしでサーバーを実行でき、開発やテストに役立ちます。

### その他の連携

| 連携 | 状況 |
|---|---|
| Revit | 利用可能。ネイティブの C# アドイン。 |
| IFC (IfcOpenShell) | 利用可能。Revit を起動せずに IFC ファイルを読み取ります。 |
| Rhino と Grasshopper | 利用可能。`localhost:3004` の Rhino アドインに接続します。 |
| Speckle | 利用可能。環境に Speckle のクライアント ID が必要です。 |
| Navisworks Manage | 開発中。プロバイダーとそのツールは登録済みですが、Navisworks アドインは未完成です。 |
| Power BI | 開発中。プロバイダーとツールはありますが、ハブには登録されていません。 |
| Excel、Parquet、DuckDB | 計画中。 |

製品名とロゴはそれぞれの所有者に帰属します。バナーでは、このプロジェクトが対応するものを示す目的でのみ使用しています。

## Revit アドインのインストール

**いちばん簡単な方法（Windows）：**[最新リリース](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)から `AECModelBridge-Setup-<version>.exe` をダウンロードし、ダブルクリックして、使用する Revit のバージョンを選び、Revit を再起動します。アドインと同梱の Python サーバーがインストールされ、チェックを入れれば Claude Desktop と VS Code の設定も書き込まれます（現在の設定はバックアップされます）。アンインストールは Windows の設定から行えます。以下の手順はソースからビルドする場合のものです。

インストールするのは Python MCP サーバーと Revit アドインの 2 つです。ライブの Revit 自動化には両方が必要です。

### 1. MCP サーバーをインストールする

```powershell
git clone https://github.com/Sam-AEC/aec-model-bridge.git
cd aec-model-bridge

py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e packages/mcp-server-revit
```

### 2. Revit アドインをインストールする

バージョンは、インストールされている Revit に合わせて設定します。ダウンロードしたスクリプトを Windows がブロックする場合は、各 `.ps1` ファイルを右クリックして [プロパティ] を開き、実行前に [ブロックの解除] を選びます。

```powershell
$RevitVersion = Read-Host "Revit year (2024, 2025, 2026, or 2027)"

.\scripts\package.ps1 -RevitVersion $RevitVersion
.\scripts\install.ps1 -RevitVersion $RevitVersion
```

インストーラーは、バージョンごとのバイナリを次の場所に配置します。

```text
C:\ProgramData\AECModelBridge\bin\<year>
```

アドインのマニフェストは、ユーザーごとに次の場所にインストールされます。

```text
%APPDATA%\Autodesk\Revit\Addins\<year>
```

`install.ps1` に `-AllUsers` を付けると、代わりにマニフェストが `C:\ProgramData\Autodesk\Revit\Addins\<year>` にインストールされます。

対応するすべてのバージョンのバイナリを一度に用意するには：

```powershell
.\scripts\package.ps1 -RevitVersion All
```

各 [GitHub リリース](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)には、Revit の年ごとのビルド済みパッケージ（例：`aec-model-bridge-revit-2026-<version>.zip`）があります。ソースからビルドする代わりに、これを展開して `.\install.ps1 -RevitVersion 2026` を実行します。ダブルクリックで使える Windows インストーラーは、`scripts/build-installer.ps1` が Inno Setup で作成します。トラブルシューティングを含む詳しいガイドは [docs/install.md](../install.md) にあります。

## Claude Desktop を Revit に接続する

サーバーを MCP クライアントの設定に追加します。Claude Desktop の場合は、`claude_desktop_config.json` の `mcpServers` セクションです。Codex、Cursor、VS Code などの MCP クライアントも、それぞれの設定形式で同じ `command`、`args`、`env` の値を使います。

仮想環境の Python 実行ファイルを指定し、サーバーがアクセスしてよいワークスペースフォルダーを選びます。

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

`MCP_REVIT_HOST_VERSION` を省略すると、開いている最新の Revit インスタンスが対象になります。`2024` や `2026` などの年を設定すると、そのクライアントのエントリを特定の Revit バージョンに固定できます。`MCP_REVIT_BRIDGE_URL` は、高度な構成でエンドポイントを上書きします。

VS Code では [`.vscode/mcp.json`](../../.vscode/mcp.json) から始められます。Hermes Desktop では、プレースホルダーの Python パスを置き換えたうえで [`docs/examples/hermes-desktop.json`](../examples/hermes-desktop.json) から始められます。MCP Bundles に対応するクライアントは、[最新リリース](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)の `.mcpb` ファイルをインストールできます。サーバーは実行中のデスクトップアプリと通信するため、Revit アドインは引き続き必要です。

### 接続を確認する

アドインをインストールしたら Revit を再起動し、モデルを開いて、次を実行します。

```powershell
$registry = Get-ChildItem "$env:LOCALAPPDATA\AECModelBridge\registry\revit-*.json" | Select-Object -First 1
$switch = Get-Content $registry.FullName -Raw | ConvertFrom-Json
Invoke-RestMethod "$($switch.endpoint)/health"
```

レスポンスに `healthy` と実行中の Revit バージョンが表示されるはずです。Revit では、`AEC Bridge` リボンタブを探してください。Workflows パネルには Open Panel、Health Check、Pending Actions、Reports があり、Tools パネルには Config、Help、About があります。

## セキュリティ

- Revit ブリッジは localhost でのみ待ち受けます。
- サーバーは `MCP_REVIT_ALLOWED_DIRECTORIES` に指定したフォルダー内でのみ読み書きします。
- 承認をオフにしない限り、モデルを変更するツールには承認済みのプランが必要です。
- ツール呼び出しは監査ログに記録され、機密情報はマスクされます。

詳細は [docs/security.md](../security.md) をご覧ください。脆弱性を報告するには [SECURITY.md](../../SECURITY.md) に従ってください。

## FAQ

### Revit 用の MCP サーバーとは何ですか？

Model Context Protocol（MCP）は、AI アシスタントが他のソフトウェアのツールを呼び出せるようにするオープンな標準です。Revit 用の MCP サーバーは、Revit の操作をツールとして公開します。アシスタントがツールを選び、アドインが Revit 内でそれを実行します。

### どの AI アシスタントで使えますか？

ローカルの stdio サーバーを起動できる MCP クライアントであれば使えます。ドキュメントがあるのは、Claude Desktop、GitHub Copilot を併用する VS Code、Cursor、Codex、および標準的な `mcpServers` 設定を読み込むクライアントです。Windsurf、Cline、Roo Code、Continue、Zed、Claude Code、Gemini CLI も同じ方法で動作するはずですが、未検証です。[互換性](../compatibility.md)をご覧ください。パネルのチャットでは、Anthropic API キー、またはインストール済みの `claude` や `codex` のコマンドラインツールも使えます。[ADR 0012](../0012-native-agent-chat-backend.md) をご覧ください。

### AI が確認なしにモデルを変更することはありますか？

デフォルトのモードではありません。モデルを変更するツールは、Revit のパネルでプランが承認されるまでブロックされます。読み取り専用のツールは承認なしで実行されます。`MCP_REVIT_APPROVAL_MODE=auto` を設定すると、承認はスキップされます。

### モデルがクラウドに送信されますか？

サーバーとアドインはお使いのマシン上で動作し、ブリッジは localhost でのみ待ち受けます。AI アシスタントに何が見えるかは、使用するクライアントによります。ツールの結果は、そのクライアントのモデルプロバイダーに送られます。Speckle のようなクラウド向けのプロバイダーは、設定してそのツールを呼び出したときにだけ動作します。

### Revit なしで IFC ファイルを扱えますか？

はい。IFC プロバイダーは IfcOpenShell でファイルを読み取ります。ファイルのメタデータ、空間構造、要素のプロパティとバウンディングボックスを返し、クラス、GUID、名前、プロパティによる検索を実行し、スキーマを検証できます。IFC ファイルの編集はできません。

### Revit がインストールされていなくても使えますか？

開発やテストのために、サーバーをモックモードで実行できます。ライブのモデル操作には、Revit 2024〜2027 とアドインが必要です。

## リリースとバージョン

AEC Model Bridge はセマンティックバージョニングに従います。リリースは GitHub で `vX.Y.Z` のタグが付けられ、ルートの `VERSION` ファイルにバージョン番号があります。リリース手順は [docs/versioning.md](../versioning.md)、各バージョンの変更点は [CHANGELOG.md](../../CHANGELOG.md) をご覧ください。

## 開発

```powershell
# Python tests
python -m pytest packages/mcp-server-revit/tests

# Build one Revit version, for example 2026
.\scripts\build-addin.ps1 -RevitVersion 2026 -Configuration Release

# Build all supported versions
.\scripts\package.ps1 -RevitVersion All
```

CI は、Python サーバーと、Revit 2024〜2027 向けのアドインのターゲットをビルドします。Pull Request を作成する前に [CONTRIBUTING.md](../../CONTRIBUTING.md) をお読みください。

## ドキュメント

- [インストールガイド](../install.md)
- [ツールリファレンス](../tools-generated.md)
- [アーキテクチャ](../0001-multi-provider-architecture.md)
- [設定リファレンス](../configuration-reference.md)
- [セキュリティ](../security.md)
- [MCP クライアントとレジストリ](../marketplaces.md)
- [バージョニングとリリース](../versioning.md)
- [すべてのドキュメント](../README.md)
- [コントリビューション](../../CONTRIBUTING.md) と [行動規範](../../CODE_OF_CONDUCT.md)
- [コントリビューター](../../CONTRIBUTORS.md)

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

## プロジェクトとライセンス

メンテナー：[A. Sam Mohammad](https://github.com/Sam-AEC)。
[LinkedIn](https://www.linkedin.com/in/a-sam-mohammad-92790416b) |
[Issues](https://github.com/Sam-AEC/aec-model-bridge/issues)

[Revit Linking Exception 付きの GPL-3.0-or-later、または商用ライセンス](../../LICENSING.md)。
