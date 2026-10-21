<div align="center">

<img src="../../assets/logo.svg" alt="AEC Model Bridge logo: an isometric model cube with a bridge arch" height="120">

[English](../../README.md) | [简体中文](README.zh-CN.md) | [Español](README.es.md) | [हिन्दी](README.hi.md) | [العربية](README.ar.md) | [Português (BR)](README.pt-BR.md) | [Русский](README.ru.md) | [日本語](README.ja.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Bahasa Indonesia](README.id.md) | [Türkçe](README.tr.md) | **한국어** | [Tiếng Việt](README.vi.md) | [Italiano](README.it.md) | [Polski](README.pl.md) | [繁體中文](README.zh-TW.md)

> 이 문서는 AI의 도움으로 번역되었습니다. 영문 [README](../../README.md)가 기준 문서이며, 오류나 개선 사항은 Pull Request로 알려 주세요. 자세한 내용은 [CONTRIBUTING.md](../../CONTRIBUTING.md)를 참고하세요.

**열려 있는 Revit 모델에 대해 AI에게 물어보세요. 기본 설정에서는 계획을 승인하기 전까지 쓰기 도구가 차단됩니다.**

Revit 2024 – 2027용 오픈소스 MCP 서버와 네이티브 애드인. Claude, Codex 및 다른 MCP 클라이언트와 함께 사용할 수 있습니다.

[![CI](https://img.shields.io/github/actions/workflow/status/Sam-AEC/aec-model-bridge/ci.yml?branch=main&style=flat-square&label=CI)](https://github.com/Sam-AEC/aec-model-bridge/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Sam-AEC/aec-model-bridge?style=flat-square&color=0F766E)](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)
[![Revit](https://img.shields.io/badge/Revit-2024--2027-0696D7?style=flat-square)](#지원하는-revit-버전)
[![License](https://img.shields.io/badge/license-GPL--3.0%20%2B%20commercial-2563EB?style=flat-square)](../../LICENSING.md)

[시작하기](#빠른-시작) | [워크플로 예시](#워크플로-예시) | [도구](../tools-generated.md) | [문서](#문서) | [다운로드](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)

</div>

<p align="center">
  <img src="../images/readme/revit-villa-panel.png" alt="Dev 모드가 활성화된 AEC Model Bridge 패널 옆의 Revit 빌라 모델." width="900">
</p>

AEC Model Bridge는 Claude, Codex, Cursor 등의 AI 어시스턴트가 현재 열려 있는 Revit 모델을 읽고 편집할 수 있게 해 주는 오픈소스 Revit MCP 서버이며, 모든 변경은 먼저 사용자가 승인해야 적용됩니다. Python MCP 서버와 네이티브 Revit 애드인으로 구성됩니다. 읽기 전용 도구는 모델을 즉시 조회하며, 모델 변경에는 기본적으로 승인된 계획이 필요합니다. [승인 흐름 보기](#승인-방식).

<p align="center">
  <img src="../images/readme/works-with.svg" alt="호환: Claude Desktop, GitHub Copilot과 함께 쓰는 VS Code, Cursor, Codex는 설정 문서가 있습니다. Claude Code, Windsurf, Cline, Continue, Zed, Gemini CLI 같은 다른 MCP 클라이언트도 동작할 것으로 예상됩니다. 애플리케이션: Revit 2024~2027, Rhino, Grasshopper, Navisworks(개발 중). 데이터: IFC, Speckle, Excel, SQLite. 프로토콜: 승인 게이트가 있는 stdio 기반 MCP." width="900">
</p>

Claude Desktop, GitHub Copilot과 함께 쓰는 VS Code, Cursor, Codex에 대한 설정 문서를 제공합니다. 표준 MCP stdio 서버이므로 Claude Code, Windsurf, Cline, Continue, Zed, Gemini CLI 같은 다른 클라이언트에서도 동작할 것으로 예상됩니다. 문서화된 범위와 테스트되지 않은 범위는 [호환성](../compatibility.md)을 참고하세요.

같은 서버에 IFC 검사, Rhino 및 Grasshopper 자동화, Speckle 연동도 포함되어 있습니다. [연동 현황](#기타-연동)에서 사용 가능한 프로바이더와 개발 중인 항목을 구분해 보여 줍니다.

## 스타 기록

<a href="https://www.star-history.com/?repos=sam-aec%2Faec-model-bridge&type=date&legend=top-right">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=sam-aec/aec-model-bridge&type=date&theme=dark&legend=bottom-right" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=sam-aec/aec-model-bridge&type=date&legend=bottom-right" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=sam-aec/aec-model-bridge&type=date&legend=bottom-right" />
 </picture>
</a>

## 워크플로 예시

BIM 코디네이터를 위한 흐름입니다. 모델 품질을 점검하고, 영향받는 요소를 검토하고, 매개변수 수정을 승인한 뒤, 결과를 확인하고 보고서를 내보냅니다. 이 예시는 [현재 도구 카탈로그](../tools-generated.md)의 도구를 사용합니다.

| 워크플로 | 요청 예시 | 사용하는 도구 |
| --- | --- | --- |
| 모델 검토 | "활성 문서를 보여 주고, 경고를 나열하고, 영향받는 요소를 찾아 주세요." | `revit_get_document_info`, `revit_get_warnings`, `revit_get_elements_by_type` |
| 매개변수 업데이트 | "Level 02의 벽을 찾아 Comments 값을 보여 주고, 일괄 업데이트를 제안해 주세요." | `revit_get_elements_by_type`, `revit_get_element_parameters`, `revit_batch_set_parameters` |
| 도면 작성 | "이 CSV로 시트 목록을 준비하고, 시트 생성과 뷰 배치를 제안해 주세요." | `revit_batch_create_sheets_from_csv`, `revit_place_viewport_on_sheet` |
| IFC 검토 | "이 IFC 파일의 층을 보여 주고, 벽 속성을 확인하고, 스키마 검증 문제를 보고해 주세요." | `ifc_get_spatial_structure`, `ifc_get_properties`, `ifc_validate` |

Revit에서 처음 사용해 본다면 이렇게 요청해 보세요.

```text
Read the active model's warnings. Group them by description and show the
affected element IDs. Then suggest which issues to investigate first.
```

이어서 매개변수 수정을 시도해 보세요. 레벨과 값은 프로젝트에 맞게 바꾸세요.

```text
Find walls on Level 02 and show their current Comments values. Propose setting
Comments to "Coordination reviewed" for the elements I choose. After I approve
the plan in Revit, apply it and read the values back to confirm the result.
```

편집할 때는 어시스턴트가 `plan_actions`로 계획을 만들고, `execute_plan`이 적용하기 전에 Revit 패널에서 검토합니다. IFC 검토는 Revit 없이 실행됩니다.

스냅샷 QA/QC 및 보고서 모듈에는 호환되는 저장된 스냅샷이 필요합니다. 현재 Revit에서 모듈로 스냅샷을 넘기려면 파일 이름과 작업 공간이 일치해야 하며, `snapshot_id`를 생략하면 생성된 샘플 데이터가 반환될 수 있습니다. 실시간 조회에는 위의 Revit 도구를 직접 사용하세요. [예정된 수정 사항과 데모](../roadmap.md).

## 빠른 시작

**원클릭 설치**

[![Install in VS Code](https://img.shields.io/badge/Install_in-VS_Code-0098FF?style=for-the-badge)](../install-buttons.md#vs-code)
[![Install in Cursor](https://img.shields.io/badge/Install_in-Cursor-111111?style=for-the-badge)](https://cursor.com/en/install-mcp?name=aec-model-bridge&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyItLWZyb20iLCJnaXQraHR0cHM6Ly9naXRodWIuY29tL1NhbS1BRUMvYWVjLW1vZGVsLWJyaWRnZSNzdWJkaXJlY3Rvcnk9cGFja2FnZXMvbWNwLXNlcnZlci1yZXZpdCIsImFlYy1tb2RlbC1icmlkZ2UiXSwiZW52Ijp7Ik1DUF9SRVZJVF9NT0RFIjoiYnJpZGdlIn19)
[![Claude Desktop bundle](https://img.shields.io/badge/Claude_Desktop-.mcpb_bundle-D97757?style=for-the-badge)](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)

버튼에는 [uv](https://docs.astral.sh/uv/getting-started/installation/)만 있으면 되며 다른 설정은 필요 없습니다. 별도로 지정하지 않으면 서버는 `~/Documents/AEC Model Bridge`를 작업 공간으로 사용합니다. Claude Desktop은 최신 릴리스에서 `.mcpb` 파일을 내려받아 열면 됩니다. 실제 Revit 작업에는 여전히 Revit과 [애드인](#revit-애드인-설치)이 필요하며, mock 모드에는 아무것도 필요하지 않습니다.

**수동 설정**

실시간 Revit 자동화에는 Windows, 정식 라이선스의 Revit 2024~2027, Python 3.11 이상, [uv](https://docs.astral.sh/uv/getting-started/installation/), 그리고 Revit 애드인이 필요합니다([설치 단계](#revit-애드인-설치)). 그런 다음 아래 내용을 `claude_desktop_config.json`에 추가하세요(Codex, Cursor, VS Code도 같은 값을 사용하며, 두 디렉터리 변수는 선택 사항이고 기본값은 위의 작업 공간입니다).

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

먼저 Revit 없이 도구를 살펴보고 싶다면 `"MCP_REVIT_MODE": "mock"`으로 설정하세요. 서버는 어디서든 시작되고, 모든 도구를 스키마와 함께 나열하며, 모델을 건드리지 않고 미리 정해진 응답을 반환합니다. 같은 mock 모드용 `Dockerfile`이 저장소 루트에 있습니다(`docker build -t aec-model-bridge .` 후 `docker run -i --rm aec-model-bridge`).

VS Code를 사용하시나요? [확장 프로그램 소스와 로컬 설치 단계](../../extensions/vscode/README.md)에서 MCP 서버를 등록하고 Revit 연결 상태를 확인할 수 있습니다. Marketplace에는 게시되지 않았습니다.

### 도구 한눈에 보기

| 영역 | 도구 수 | 기능 |
| --- | --- | --- |
| Revit | 103 | 모델 읽기, 요소·매개변수·뷰·시트·일람표 생성 및 편집, 내보내기, 워크셰어링 |
| 승인 | 6 | 모델 변경의 계획, 검토, 승인, 실행, 롤백 |
| 모듈 | 34 | 스냅샷 검사, 매개변수 그리드, QA/QC 점검, 레시피, 보고서, 선택 |
| Rhino 및 Grasshopper | 19 | 지오메트리, 레이어, 재료, 불리언 연산 |
| Speckle | 17 | 프로젝트, 모델, 버전, 전송 및 수신 |
| Navisworks | 15 | 모델 트리, 뷰포인트, 간섭 검토(개발 중) |
| IFC | 7 | Revit 없이 IFC 파일 읽기: 구조, 속성, 검증 |
| 그래프, 스냅샷, 내보내기, 작업 | 18 | 시맨틱 그래프 감사, 스냅샷 비교, SQLite 내보내기, 백그라운드 작업 |

기본 설정에서는 219개의 도구가 나열됩니다(mock 모드에서 현재 서버 기준으로 집계). Autodesk Data 도구는 APS 자격 증명을 구성하면 나타납니다. [도구 레퍼런스](../tools-generated.md)에서 모든 도구를 확인할 수 있습니다. 각 도구에는 MCP 어노테이션(`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`)이 있어 클라이언트가 읽기와 쓰기를 구분할 수 있습니다.

### 고급 Revit 자동화

모델 조회와 매개변수 업데이트 외에도 Revit 도구는 건축 요소, 뷰, 시트, 일람표, 태그, 치수를 만들고 IFC, DWG, 이미지, Navisworks 파일을 내보냅니다. 지원하는 작업과 입력은 [도구 레퍼런스](../tools-generated.md)를 참고하세요.

도구 카탈로그가 다루지 않는 작업에는 `revit_invoke_method`, `revit_reflect_get`, `revit_reflect_set`으로 공개된 Revit API 멤버를 다루고, `revit_execute_python`으로 Revit 안에서 IronPython을 실행할 수 있습니다. 이러한 고급 도구는 Revit 프로세스와 동일한 권한을 가지므로, 신뢰하는 MCP 클라이언트와 프롬프트에서만 사용하세요.

## 동작 방식

MCP 클라이언트는 하나의 Python 허브와 통신합니다. 허브는 각 호출을 해당 도구를 가진 프로바이더로 보냅니다. 데스크톱 앱용 프로바이더는 localhost를 통해 그 앱 안의 작은 애드인과 통신합니다.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../images/architecture-dark.png">
    <img src="../images/architecture-light.png" alt="Architecture of AEC Model Bridge: an MCP client such as Claude or Codex calls the Python MCP hub, which routes tool calls to the Revit, Rhino, Navisworks, IFC and Speckle providers. The Revit and Rhino providers talk to add-ins over localhost HTTP, the IFC provider reads IFC files with IfcOpenShell, and Navisworks is still in progress." width="900">
  </picture>
</p>

<sub>다이어그램 소스: [architecture.mmd](../diagrams/architecture.mmd). 이미지는 `python scripts/render_diagrams.py`로 다시 생성합니다.</sub>

청록색 상자는 현재 동작하는 부분이고, 호박색 점선 상자는 개발 중인 부분이며, 남색 도형은 데이터와 외부 서비스입니다.

### 승인 방식

허브는 승인된 계획이 없는 한 모델을 변경하는 모든 도구 호출을 막습니다. 기본 모드는 `required`입니다. AI가 계획을 제안하면 Revit 사이드 패널에서 검토하고, 애드인이 Revit 메인 스레드에서 실행하며, 매개변수 및 모델 편집 작업은 각각 이름이 붙은 별도 트랜잭션으로 실행되지만, 저장·동기화·스크립트 작업은 그렇지 않아 Ctrl+Z로 되돌릴 수 없습니다.

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

<sub>다이어그램 소스: [approval-flow.mmd](../diagrams/approval-flow.mmd). 이미지는 `python scripts/render_diagrams.py`로 다시 생성합니다.</sub>

계획이 잘못된 것으로 드러나면 Revit의 Ctrl+Z로 되돌리세요. 매개변수 쓰기는 각각 이름이 붙은 별도 트랜잭션이므로, 계획 하나를 되돌리려면 여러 번 눌러야 할 수 있습니다. 계획 전체를 한 번에 되돌리는 기능은 계획 단계이며 아직 구현되지 않았습니다. 두 번째 방법은 되돌리기 계획입니다. 어시스턴트가 실행된 계획의 증빙으로 `plan_revert`를 사용해 초안을 만들고, 다른 계획과 똑같이 사용자가 승인합니다. `rollback_plan`은 사람 전용이며 버튼도 명령도 아니므로 기대하지 마세요. 이 방법들은 모두 실제 Revit 세션에서 아직 검증되지 않았습니다(UNVERIFIED). 파일 출력처럼 되돌릴 수 없는 작업은 어떤 방법으로도 되돌릴 수 없으며, 한 번 더 확인하는 기능은 아직 없습니다(계획 단계). 패널의 Plans 목록에는 대기 중인 계획만 표시됩니다. `aec-model-bridge-approve show <plan_id>`는 어떤 상태의 계획에도 사용할 수 있지만, `proofs/` 번들은 실행된(또는 실행을 시도한) 계획에만 존재합니다. 전체 수명 주기는 [ADR 0008](../0008-approval-gate-lifecycle.md)에 있습니다.

무인 파이프라인에서는 `MCP_REVIT_APPROVAL_MODE=auto`를 설정할 수 있습니다. 사람의 확인을 끄는 설정이므로 통제된 환경에서만 사용하세요.

## 지원하는 Revit 버전

| Revit 버전 | 애드인 대상 | 빌드 도구 |
|---|---|---|
| 2024 | .NET Framework 4.8 | .NET 8 SDK 및 .NET Framework 4.8 개발자 팩 |
| 2025 | .NET 8 for Windows | .NET 8 SDK |
| 2026 | .NET 8 for Windows | .NET 8 SDK |
| 2027 | .NET 10 for Windows | .NET 10 SDK |

또한 Windows 10 또는 11, Python 3.11 이상, 그리고 사용하는 버전의 정식 라이선스 Revit이 필요합니다. mock 모드는 Revit 없이 서버를 실행하므로 개발과 테스트에 유용합니다.

### 기타 연동

| 연동 | 상태 |
|---|---|
| Revit | 사용 가능. 네이티브 C# 애드인. |
| IFC (IfcOpenShell) | 사용 가능. Revit을 실행하지 않고 IFC 파일을 읽습니다. |
| Rhino 및 Grasshopper | 사용 가능. `localhost:3004`의 Rhino 애드인에 연결합니다. |
| Speckle | 사용 가능. 환경에 Speckle 클라이언트 ID가 필요합니다. |
| Navisworks Manage | 개발 중. 프로바이더와 도구는 등록되어 있지만 Navisworks 애드인은 완성되지 않았습니다. |
| Power BI | 개발 중. 프로바이더와 도구는 있으나 허브에 등록되어 있지 않습니다. |
| Excel, Parquet 및 DuckDB | 예정. |

제품 이름과 로고는 각 소유자에게 귀속됩니다. 배너는 이 프로젝트가 함께 동작하는 대상을 보여 주기 위한 용도로만 사용합니다.

## Revit 애드인 설치

**가장 쉬운 방법(Windows):** [최신 릴리스](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)에서 `AECModelBridge-Setup-<version>.exe`를 내려받아 더블클릭하고, 사용하는 Revit 버전을 고른 뒤 Revit을 다시 시작하세요. 애드인과 번들된 Python 서버가 설치되며, 체크박스를 선택하면 Claude Desktop과 VS Code 설정도 적용되고 기존 설정은 백업됩니다. 제거는 Windows 설정에서 합니다. 아래 단계는 소스에서 빌드하는 경우를 위한 것입니다.

Python MCP 서버와 Revit 애드인, 두 부분을 설치해야 합니다. 실시간 Revit 자동화에는 둘 다 필요합니다.

### 1. MCP 서버 설치

```powershell
git clone https://github.com/Sam-AEC/aec-model-bridge.git
cd aec-model-bridge

py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e packages/mcp-server-revit
```

### 2. Revit 애드인 설치

설치된 Revit에 맞게 버전을 설정하세요. 내려받은 스크립트를 Windows가 차단하면, 각 `.ps1` 파일을 마우스 오른쪽 버튼으로 클릭해 속성을 열고, 실행 전에 차단 해제를 선택하세요.

```powershell
$RevitVersion = Read-Host "Revit year (2024, 2025, 2026, or 2027)"

.\scripts\package.ps1 -RevitVersion $RevitVersion
.\scripts\install.ps1 -RevitVersion $RevitVersion
```

설치 프로그램은 버전별 바이너리를 다음 위치에 둡니다.

```text
C:\ProgramData\AECModelBridge\bin\<year>
```

애드인 매니페스트는 사용자별로 다음 위치에 설치됩니다.

```text
%APPDATA%\Autodesk\Revit\Addins\<year>
```

`install.ps1`에 `-AllUsers`를 사용하면 매니페스트가 대신 `C:\ProgramData\Autodesk\Revit\Addins\<year>`에 설치됩니다.

지원하는 모든 버전의 바이너리를 한 번에 준비하려면:

```powershell
.\scripts\package.ps1 -RevitVersion All
```

각 [GitHub 릴리스](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)에는 Revit 연도별로 준비된 패키지(예: `aec-model-bridge-revit-2026-<version>.zip`)가 있습니다. 소스에서 빌드하는 대신 압축을 풀고 `.\install.ps1 -RevitVersion 2026`을 실행하세요. 더블클릭으로 설치하는 Windows 설치 프로그램은 `scripts/build-installer.ps1`이 Inno Setup으로 만듭니다. 문제 해결을 포함한 전체 가이드는 [docs/install.md](../install.md)에 있습니다.

## Claude Desktop을 Revit에 연결

MCP 클라이언트 설정에 서버를 추가하세요. Claude Desktop에서는 `claude_desktop_config.json`의 `mcpServers` 섹션입니다. Codex, Cursor, VS Code 및 기타 MCP 클라이언트도 각자의 설정 형식에서 같은 `command`, `args`, `env` 값을 사용합니다.

가상 환경의 Python 실행 파일을 사용하고, 서버가 접근할 수 있는 작업 폴더를 선택하세요.

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

`MCP_REVIT_HOST_VERSION`을 생략하면 열려 있는 가장 최신 Revit 인스턴스를 대상으로 합니다. `2024`나 `2026` 같은 연도로 설정하면 해당 클라이언트 항목을 그 Revit 버전에 고정합니다. `MCP_REVIT_BRIDGE_URL`은 고급 구성에서 엔드포인트를 재정의합니다.

VS Code 사용자는 [`.vscode/mcp.json`](../../.vscode/mcp.json)에서 시작할 수 있습니다. Hermes Desktop 사용자는 자리 표시자 Python 경로를 바꾼 뒤 [`docs/examples/hermes-desktop.json`](../examples/hermes-desktop.json)에서 시작할 수 있습니다. MCP Bundles를 지원하는 클라이언트는 [최신 릴리스](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)의 `.mcpb` 파일을 설치할 수 있습니다. 서버가 실행 중인 데스크톱 앱과 통신하므로 Revit 애드인은 여전히 필요합니다.

### 연결 확인

애드인을 설치한 뒤 Revit을 다시 시작하고, 모델을 연 다음 실행하세요.

```powershell
$registry = Get-ChildItem "$env:LOCALAPPDATA\AECModelBridge\registry\revit-*.json" | Select-Object -First 1
$switch = Get-Content $registry.FullName -Raw | ConvertFrom-Json
Invoke-RestMethod "$($switch.endpoint)/health"
```

응답에 `healthy`와 실행 중인 Revit 버전이 표시되어야 합니다. Revit에서 `AEC Bridge` 리본 탭을 찾아보세요. Workflows 패널에는 Open Panel, Health Check, Pending Actions, Reports가 있고, Tools 패널에는 Config, Help, About이 있습니다.

## 보안

- Revit 브리지는 localhost에서만 수신합니다.
- 서버는 `MCP_REVIT_ALLOWED_DIRECTORIES`에 지정된 폴더 안에서만 읽고 씁니다.
- 승인을 끄지 않는 한, 모델을 변경하는 도구에는 승인된 계획이 필요합니다.
- 도구 호출은 감사 로그에 기록되며, 시크릿은 마스킹됩니다.

자세한 내용은 [docs/security.md](../security.md)에 있습니다. 취약점을 신고하려면 [SECURITY.md](../../SECURITY.md)를 따르세요.

## FAQ

### Revit용 MCP 서버란 무엇인가요?

Model Context Protocol(MCP)은 AI 어시스턴트가 다른 소프트웨어의 도구를 호출할 수 있게 하는 개방형 표준입니다. Revit용 MCP 서버는 Revit 작업을 도구로 제공합니다. 어시스턴트가 도구를 고르면 애드인이 Revit 안에서 실행합니다.

### 어떤 AI 어시스턴트와 함께 쓸 수 있나요?

로컬 stdio 서버를 시작할 수 있는 모든 MCP 클라이언트에서 사용할 수 있습니다. Claude Desktop, GitHub Copilot과 함께 쓰는 VS Code, Cursor, Codex, 그리고 표준 `mcpServers` 설정을 읽는 클라이언트에 대한 문서를 제공합니다. Windsurf, Cline, Roo Code, Continue, Zed, Claude Code, Gemini CLI도 같은 방식으로 동작할 것으로 예상되지만 테스트되지 않았습니다. [호환성](../compatibility.md)을 참고하세요. 패널 채팅은 Anthropic API 키나, 설치되어 있다면 `claude` 또는 `codex` 명령줄 도구도 사용할 수 있습니다. [ADR 0012](../0012-native-agent-chat-backend.md)를 참고하세요.

### AI가 묻지 않고 모델을 변경할 수 있나요?

기본 모드에서는 불가능합니다. 모델을 변경하는 도구는 Revit 패널에서 계획이 승인될 때까지 차단됩니다. 읽기 전용 도구는 승인 없이 실행됩니다. `MCP_REVIT_APPROVAL_MODE=auto`로 설정하면 승인이 생략됩니다.

### 모델이 클라우드로 전송되나요?

서버와 애드인은 사용자의 컴퓨터에서 실행되고, 브리지는 localhost에서만 수신합니다. AI 어시스턴트가 무엇을 보는지는 사용하는 클라이언트에 달려 있으며, 도구 결과는 그 클라이언트의 모델 제공자에게 전달됩니다. Speckle 같은 클라우드 연결 프로바이더는 사용자가 구성하고 해당 도구를 호출할 때만 실행됩니다.

### Revit 없이 IFC 파일을 다룰 수 있나요?

네. IFC 프로바이더는 IfcOpenShell로 파일을 읽습니다. 파일 메타데이터, 공간 구조, 요소 속성과 바운딩 박스를 반환하고, 클래스·GUID·이름·속성으로 조회하며, 스키마를 검증할 수 있습니다. IFC 파일을 편집하지는 않습니다.

### Revit이 설치되어 있지 않아도 사용할 수 있나요?

개발과 테스트용으로 서버를 mock 모드에서 실행할 수 있습니다. 실제 모델 작업에는 Revit 2024~2027과 애드인이 필요합니다.

## 릴리스와 버전

AEC Model Bridge는 시맨틱 버저닝을 따릅니다. 릴리스는 GitHub에서 `vX.Y.Z` 태그로 관리되고, 루트의 `VERSION` 파일에 버전 번호가 있습니다. 릴리스 절차는 [docs/versioning.md](../versioning.md), 버전별 변경 사항은 [CHANGELOG.md](../../CHANGELOG.md)를 참고하세요.

## 개발

```powershell
# Python tests
python -m pytest packages/mcp-server-revit/tests

# Build one Revit version, for example 2026
.\scripts\build-addin.ps1 -RevitVersion 2026 -Configuration Release

# Build all supported versions
.\scripts\package.ps1 -RevitVersion All
```

CI는 Python 서버와 Revit 2024~2027용 애드인 대상을 빌드합니다. Pull Request를 열기 전에 [CONTRIBUTING.md](../../CONTRIBUTING.md)를 읽어 보세요.

## 문서

- [설치 가이드](../install.md)
- [도구 레퍼런스](../tools-generated.md)
- [아키텍처](../0001-multi-provider-architecture.md)
- [구성 레퍼런스](../configuration-reference.md)
- [보안](../security.md)
- [MCP 클라이언트와 레지스트리](../marketplaces.md)
- [버전 관리와 릴리스](../versioning.md)
- [전체 문서](../README.md)
- [기여 가이드](../../CONTRIBUTING.md) 및 [행동 강령](../../CODE_OF_CONDUCT.md)
- [기여자](../../CONTRIBUTORS.md)

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

## 프로젝트와 라이선스

메인테이너: [A. Sam Mohammad](https://github.com/Sam-AEC).
[LinkedIn](https://www.linkedin.com/in/a-sam-mohammad-92790416b) |
[Issues](https://github.com/Sam-AEC/aec-model-bridge/issues)

[Revit Linking Exception이 포함된 GPL-3.0-or-later 또는 상용 라이선스](../../LICENSING.md).
