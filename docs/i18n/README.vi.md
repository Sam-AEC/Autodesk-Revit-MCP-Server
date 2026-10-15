<div align="center">

<img src="../../assets/logo.svg" alt="AEC Model Bridge logo: an isometric model cube with a bridge arch" height="120">

[English](../../README.md) | [简体中文](README.zh-CN.md) | [Español](README.es.md) | [हिन्दी](README.hi.md) | [العربية](README.ar.md) | [Português (BR)](README.pt-BR.md) | [Русский](README.ru.md) | [日本語](README.ja.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Bahasa Indonesia](README.id.md) | [Türkçe](README.tr.md) | [한국어](README.ko.md) | **Tiếng Việt** | [Italiano](README.it.md) | [Polski](README.pl.md) | [繁體中文](README.zh-TW.md)

> Bản dịch này được thực hiện với sự hỗ trợ của AI. [README](../../README.md) tiếng Anh là bản gốc; rất hoan nghênh các chỉnh sửa qua pull request (xem [CONTRIBUTING.md](../../CONTRIBUTING.md)).

**Hỏi AI về mô hình Revit bạn đang mở. Theo mặc định, các công cụ ghi bị chặn cho đến khi bạn phê duyệt một kế hoạch.**

Máy chủ MCP mã nguồn mở và add-in gốc cho Revit 2024 – 2027. Hoạt động với Claude, Codex và các ứng dụng khách MCP khác.

[![CI](https://img.shields.io/github/actions/workflow/status/Sam-AEC/aec-model-bridge/ci.yml?branch=main&style=flat-square&label=CI)](https://github.com/Sam-AEC/aec-model-bridge/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Sam-AEC/aec-model-bridge?style=flat-square&color=0F766E)](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)
[![Revit](https://img.shields.io/badge/Revit-2024--2027-0696D7?style=flat-square)](#các-phiên-bản-revit-được-hỗ-trợ)
[![License](https://img.shields.io/badge/license-GPL--3.0%20%2B%20commercial-2563EB?style=flat-square)](../../LICENSING.md)

[Bắt đầu](#bắt-đầu-nhanh) | [Quy trình mẫu](#quy-trình-mẫu) | [Công cụ](../tools-generated.md) | [Tài liệu](#tài-liệu) | [Tải xuống](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)

</div>

<p align="center">
  <img src="../images/readme/revit-villa-panel.png" alt="Mô hình biệt thự trong Revit bên cạnh bảng AEC Model Bridge với chế độ Dev được bật." width="900">
</p>

AEC Model Bridge là máy chủ MCP mã nguồn mở cho Revit, cho phép Claude, Codex, Cursor và các trợ lý AI khác đọc và chỉnh sửa mô hình Revit bạn đang mở, với mọi thay đổi đều do bạn phê duyệt trước. Công cụ này kết hợp máy chủ MCP viết bằng Python với add-in Revit gốc: các công cụ chỉ đọc kiểm tra mô hình ngay lập tức, còn thay đổi trên mô hình mặc định cần một kế hoạch đã được phê duyệt. [Xem luồng phê duyệt](#cách-phê-duyệt-hoạt-động).

<p align="center">
  <img src="../images/readme/works-with.svg" alt="Hoạt động với: Claude Desktop, VS Code với GitHub Copilot, Cursor và Codex đã có tài liệu thiết lập. Các ứng dụng khách MCP khác như Claude Code, Windsurf, Cline, Continue, Zed và Gemini CLI cũng nên hoạt động được. Ứng dụng: Revit 2024 đến 2027, Rhino, Grasshopper, Navisworks (đang phát triển). Dữ liệu: IFC, Speckle, Excel, SQLite. Giao thức: MCP qua stdio với cổng phê duyệt." width="900">
</p>

Có tài liệu thiết lập cho Claude Desktop, VS Code với GitHub Copilot, Cursor và Codex. Đây là máy chủ MCP stdio tiêu chuẩn, nên các ứng dụng khách khác như Claude Code, Windsurf, Cline, Continue, Zed và Gemini CLI cũng nên hoạt động được. Xem [khả năng tương thích](../compatibility.md) để biết phần nào đã có tài liệu và phần nào chưa được kiểm thử.

Cùng máy chủ này còn có chức năng kiểm tra IFC, tự động hóa Rhino và Grasshopper, và tích hợp Speckle. [Trạng thái tích hợp](#các-tích-hợp-khác) phân biệt các nhà cung cấp đã sẵn sàng với những phần đang được phát triển.

## Quy trình mẫu

Dành cho điều phối viên BIM: kiểm tra chất lượng mô hình, xem xét các phần tử bị ảnh hưởng, phê duyệt việc sửa tham số (parameter), sau đó kiểm tra kết quả và xuất báo cáo. Các ví dụ này dùng công cụ trong [danh mục hiện tại](../tools-generated.md).

| Quy trình | Yêu cầu mẫu | Công cụ sử dụng |
| --- | --- | --- |
| Rà soát mô hình | "Hiển thị tài liệu đang hoạt động, liệt kê các cảnh báo và tìm các phần tử bị ảnh hưởng." | `revit_get_document_info`, `revit_get_warnings`, `revit_get_elements_by_type` |
| Cập nhật tham số | "Tìm các bức tường ở Level 02, hiển thị giá trị Comments của chúng và đề xuất cập nhật hàng loạt." | `revit_get_elements_by_type`, `revit_get_element_parameters`, `revit_batch_set_parameters` |
| Triển khai bản vẽ | "Chuẩn bị danh sách sheet từ tệp CSV này, rồi đề xuất tạo các sheet và đặt các view." | `revit_batch_create_sheets_from_csv`, `revit_place_viewport_on_sheet` |
| Rà soát IFC | "Hiển thị các tầng của tệp IFC này, kiểm tra thuộc tính của tường và báo cáo các lỗi xác thực lược đồ." | `ifc_get_spatial_structure`, `ifc_get_properties`, `ifc_validate` |

Để thử lần đầu trong Revit, hãy nhập:

```text
Read the active model's warnings. Group them by description and show the
affected element IDs. Then suggest which issues to investigate first.
```

Sau đó thử sửa một tham số, thay cao độ (level) và giá trị cho phù hợp với dự án của bạn:

```text
Find walls on Level 02 and show their current Comments values. Propose setting
Comments to "Coordination reviewed" for the elements I choose. After I approve
the plan in Revit, apply it and read the values back to confirm the result.
```

Với các thao tác chỉnh sửa, trợ lý tạo kế hoạch bằng `plan_actions`; bạn xem xét kế hoạch trong bảng điều khiển Revit trước khi `execute_plan` áp dụng. Việc rà soát IFC chạy được mà không cần Revit.

Các mô-đun QA/QC và báo cáo dựa trên snapshot cần một snapshot đã lưu tương thích. Hiện tại, việc chuyển snapshot từ Revit sang mô-đun đòi hỏi tên tệp và workspace phải khớp nhau; nếu bỏ qua `snapshot_id`, dữ liệu mẫu được tạo sẵn có thể được trả về. Hãy dùng trực tiếp các công cụ Revit ở trên để kiểm tra theo thời gian thực. [Các bản sửa dự kiến và bản demo](../roadmap.md).

## Bắt đầu nhanh

**Cài đặt một cú nhấp**

[![Install in VS Code](https://img.shields.io/badge/Install_in-VS_Code-0098FF?style=for-the-badge)](../install-buttons.md#vs-code)
[![Install in Cursor](https://img.shields.io/badge/Install_in-Cursor-111111?style=for-the-badge)](https://cursor.com/en/install-mcp?name=aec-model-bridge&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyItLWZyb20iLCJnaXQraHR0cHM6Ly9naXRodWIuY29tL1NhbS1BRUMvYWVjLW1vZGVsLWJyaWRnZSNzdWJkaXJlY3Rvcnk9cGFja2FnZXMvbWNwLXNlcnZlci1yZXZpdCIsImFlYy1tb2RlbC1icmlkZ2UiXSwiZW52Ijp7Ik1DUF9SRVZJVF9NT0RFIjoiYnJpZGdlIn19)
[![Claude Desktop bundle](https://img.shields.io/badge/Claude_Desktop-.mcpb_bundle-D97757?style=for-the-badge)](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)

Các nút này chỉ cần [uv](https://docs.astral.sh/uv/getting-started/installation/) và không cần thiết lập nào khác: máy chủ dùng `~/Documents/AEC Model Bridge` làm workspace trừ khi bạn tự chỉ định. Với Claude Desktop, hãy tải tệp `.mcpb` từ bản phát hành mới nhất và mở nó. Làm việc trực tiếp với Revit vẫn cần Revit và [add-in](#cài-đặt-add-in-revit); chế độ mock thì không cần gì cả.

**Thiết lập thủ công**

Để tự động hóa Revit trực tiếp, bạn cần Windows, Revit 2024 đến 2027 có bản quyền, Python 3.11 trở lên, [uv](https://docs.astral.sh/uv/getting-started/installation/) và add-in Revit ([các bước cài đặt](#cài-đặt-add-in-revit)). Sau đó thêm đoạn sau vào `claude_desktop_config.json` (Codex, Cursor và VS Code dùng cùng giá trị; hai biến thư mục là tùy chọn và mặc định là workspace ở trên):

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

Muốn xem các công cụ trước mà chưa có Revit? Hãy đặt `"MCP_REVIT_MODE": "mock"`. Khi đó máy chủ chạy được ở bất kỳ đâu, liệt kê mọi công cụ cùng lược đồ của chúng và trả về các phản hồi dựng sẵn mà không chạm vào mô hình nào. Một `Dockerfile` cho cùng chế độ mock này nằm ở thư mục gốc của kho mã (`docker build -t aec-model-bridge .`, sau đó `docker run -i --rm aec-model-bridge`).

Dùng VS Code? [Mã nguồn tiện ích mở rộng và các bước cài đặt cục bộ](../../extensions/vscode/README.md) sẽ đăng ký máy chủ MCP và hiển thị trạng thái kết nối Revit. Tiện ích này chưa được đăng lên Marketplace.

### Tổng quan công cụ

| Lĩnh vực | Công cụ | Chức năng |
| --- | --- | --- |
| Revit | 110 | Đọc mô hình, tạo và chỉnh sửa phần tử, tham số, view, sheet, bảng thống kê (schedule), xuất dữ liệu, làm việc chung (worksharing) |
| Phê duyệt | 5 | Lập kế hoạch, xem xét, phê duyệt, thực thi và hoàn tác các thay đổi mô hình |
| Mô-đun | 83 | Kiểm tra snapshot, lưới tham số, kiểm tra QA/QC, recipe, báo cáo, vùng chọn |
| Rhino và Grasshopper | 19 | Hình học, layer, vật liệu, phép toán boolean |
| Speckle | 17 | Dự án, mô hình, phiên bản, gửi và nhận |
| Navisworks | 15 | Cây mô hình, viewpoint, kiểm tra va chạm (đang phát triển) |
| IFC | 7 | Đọc tệp IFC mà không cần Revit: cấu trúc, thuộc tính, xác thực |
| Đồ thị, snapshot, xuất dữ liệu, tác vụ | 21 | Kiểm toán đồ thị ngữ nghĩa, so sánh snapshot, xuất SQLite, tác vụ nền |

Cấu hình mặc định liệt kê 277 công cụ (đếm từ máy chủ hiện tại ở chế độ mock). Các công cụ Autodesk Data xuất hiện khi đã cấu hình thông tin xác thực APS. [Tài liệu tham khảo công cụ](../tools-generated.md) liệt kê từng công cụ. Mỗi công cụ đều có chú thích MCP (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`) để ứng dụng khách phân biệt thao tác đọc với ghi.

### Tự động hóa Revit nâng cao

Ngoài truy vấn mô hình và cập nhật tham số, các công cụ Revit còn tạo phần tử công trình, view, sheet, bảng thống kê, tag và kích thước, đồng thời xuất tệp IFC, DWG, hình ảnh và Navisworks. Xem [tài liệu tham khảo công cụ](../tools-generated.md) để biết các thao tác và đầu vào được hỗ trợ.

Với những gì danh mục công cụ chưa bao quát, `revit_invoke_method`, `revit_reflect_get` và `revit_reflect_set` làm việc với các thành viên công khai của Revit API, còn `revit_execute_python` chạy IronPython bên trong Revit. Các công cụ nâng cao này có quyền hạn giống tiến trình Revit. Chỉ dùng chúng với các ứng dụng khách MCP và prompt mà bạn tin tưởng.

## Cách hoạt động

Ứng dụng khách MCP làm việc với một hub Python. Hub chuyển từng lệnh gọi đến nhà cung cấp sở hữu công cụ đó. Các nhà cung cấp cho ứng dụng máy tính giao tiếp qua localhost với một add-in nhỏ nằm trong ứng dụng đó.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../images/architecture-dark.png">
    <img src="../images/architecture-light.png" alt="Architecture of AEC Model Bridge: an MCP client such as Claude or Codex calls the Python MCP hub, which routes tool calls to the Revit, Rhino, Navisworks, IFC and Speckle providers. The Revit and Rhino providers talk to add-ins over localhost HTTP, the IFC provider reads IFC files with IfcOpenShell, and Navisworks is still in progress." width="900">
  </picture>
</p>

<sub>Nguồn sơ đồ: [architecture.mmd](../diagrams/architecture.mmd). Tạo lại hình ảnh bằng `python scripts/render_diagrams.py`.</sub>

Các khung màu xanh mòng két đã hoạt động. Các khung nét đứt màu hổ phách đang được phát triển. Các hình màu chàm là dữ liệu và dịch vụ bên ngoài.

### Cách phê duyệt hoạt động

Hub chặn mọi lệnh gọi công cụ làm thay đổi mô hình nếu không kèm kế hoạch đã được phê duyệt. Chế độ mặc định là `required`. AI đề xuất kế hoạch, bạn xem xét trong bảng bên của Revit, và add-in chạy nó trên luồng chính của Revit, các hành động sửa tham số và chỉnh sửa mô hình mỗi hành động chạy trong một transaction có tên riêng; các hành động lưu, đồng bộ và script thì không, nên Ctrl+Z không bao gồm chúng.

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

<sub>Nguồn sơ đồ: [approval-flow.mmd](../diagrams/approval-flow.mmd). Tạo lại hình ảnh bằng `python scripts/render_diagrams.py`.</sub>

Nếu một kế hoạch hóa ra sai, hãy hoàn tác bằng Ctrl+Z trong Revit. Mỗi lần ghi tham số là một giao dịch có tên riêng, nên một kế hoạch có thể cần nhấn nhiều lần. Hoàn tác cả kế hoạch chỉ trong một bước đã được lên kế hoạch nhưng chưa được xây dựng. Cách thứ hai là kế hoạch hoàn nguyên: trợ lý soạn một kế hoạch bằng `plan_revert` từ bằng chứng của một kế hoạch đã thực thi, và bạn phê duyệt nó như mọi kế hoạch khác. `rollback_plan` chỉ dành cho con người và không phải là nút hay lệnh, vì vậy đừng trông cậy vào nó. Chưa cách nào trong số này được xác minh trong một phiên Revit thực tế (UNVERIFIED). Các thao tác không thể đảo ngược, chẳng hạn xuất tệp, không thể hoàn tác bằng cách nào trong số đó và hiện chưa yêu cầu xác nhận lần hai (đã lên kế hoạch). Danh sách Plans của bảng điều khiển chỉ hiển thị các kế hoạch đang chờ; `aec-model-bridge-approve show <plan_id>` dùng được cho kế hoạch ở bất kỳ trạng thái nào, còn các gói `proofs/` chỉ tồn tại cho những kế hoạch đã được thực thi (hoặc đã thử thực thi). Vòng đời được mô tả trong [ADR 0008](../0008-approval-gate-lifecycle.md).

Với các pipeline chạy tự động, bạn có thể đặt `MCP_REVIT_APPROVAL_MODE=auto`. Thiết lập này tắt bước kiểm tra của con người, vì vậy chỉ dùng trong môi trường được kiểm soát.

## Các phiên bản Revit được hỗ trợ

| Phiên bản Revit | Mục tiêu của add-in | Công cụ build |
|---|---|---|
| 2024 | .NET Framework 4.8 | .NET 8 SDK và .NET Framework 4.8 developer pack |
| 2025 | .NET 8 for Windows | .NET 8 SDK |
| 2026 | .NET 8 for Windows | .NET 8 SDK |
| 2027 | .NET 10 for Windows | .NET 10 SDK |

Bạn cũng cần Windows 10 hoặc 11, Python 3.11 trở lên và bản Revit có bản quyền cho phiên bản bạn dùng. Chế độ mock chạy máy chủ mà không cần Revit, hữu ích cho phát triển và kiểm thử.

### Các tích hợp khác

| Tích hợp | Trạng thái |
|---|---|
| Revit | Sẵn sàng. Add-in C# gốc. |
| IFC (IfcOpenShell) | Sẵn sàng. Đọc tệp IFC mà không cần Revit đang chạy. |
| Rhino và Grasshopper | Sẵn sàng. Kết nối với add-in Rhino tại `localhost:3004`. |
| Speckle | Sẵn sàng. Cần client ID của Speckle trong môi trường của bạn. |
| Navisworks Manage | Đang phát triển. Nhà cung cấp và các công cụ của nó đã được đăng ký. Add-in Navisworks chưa hoàn thiện. |
| Power BI | Đang phát triển. Nhà cung cấp và công cụ đã có nhưng chưa được đăng ký trong hub. |
| Excel, Parquet và DuckDB | Dự kiến. |

Tên sản phẩm và logo thuộc về chủ sở hữu của chúng. Banner chỉ dùng chúng để cho biết dự án này hoạt động với những gì.

## Cài đặt add-in Revit

**Dễ nhất (Windows):** tải `AECModelBridge-Setup-<version>.exe` từ [bản phát hành mới nhất](https://github.com/Sam-AEC/aec-model-bridge/releases/latest), nhấp đúp vào tệp, chọn các phiên bản Revit của bạn và khởi động lại Revit. Trình cài đặt sẽ cài add-in, máy chủ Python đi kèm và, nếu bạn đánh dấu ô tương ứng, cả cài đặt Claude Desktop và VS Code, đồng thời sao lưu cài đặt hiện tại của bạn. Gỡ cài đặt từ Cài đặt của Windows. Các bước bên dưới dành cho việc build từ mã nguồn.

Bạn cài hai phần: máy chủ MCP Python và add-in Revit. Tự động hóa Revit trực tiếp cần cả hai.

### 1. Cài đặt máy chủ MCP

```powershell
git clone https://github.com/Sam-AEC/aec-model-bridge.git
cd aec-model-bridge

py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e packages/mcp-server-revit
```

### 2. Cài đặt add-in Revit

Đặt phiên bản khớp với bản Revit bạn đã cài. Nếu Windows chặn các script đã tải về, hãy nhấp chuột phải vào từng tệp `.ps1`, mở Properties và chọn Unblock trước khi chạy.

```powershell
$RevitVersion = Read-Host "Revit year (2024, 2025, 2026, or 2027)"

.\scripts\package.ps1 -RevitVersion $RevitVersion
.\scripts\install.ps1 -RevitVersion $RevitVersion
```

Trình cài đặt đặt các tệp nhị phân theo từng phiên bản vào:

```text
C:\ProgramData\AECModelBridge\bin\<year>
```

Tệp manifest của add-in được cài theo từng người dùng tại:

```text
%APPDATA%\Autodesk\Revit\Addins\<year>
```

Dùng `-AllUsers` với `install.ps1` để cài manifest vào `C:\ProgramData\Autodesk\Revit\Addins\<year>`.

Để chuẩn bị tệp nhị phân cho mọi phiên bản được hỗ trợ trong một lần:

```powershell
.\scripts\package.ps1 -RevitVersion All
```

Mỗi [bản phát hành trên GitHub](https://github.com/Sam-AEC/aec-model-bridge/releases/latest) có sẵn một gói cho từng năm Revit, ví dụ `aec-model-bridge-revit-2026-<version>.zip`. Hãy giải nén và chạy `.\install.ps1 -RevitVersion 2026` thay vì build từ mã nguồn. Để có trình cài đặt Windows chỉ cần nhấp đúp, `scripts/build-installer.ps1` tạo ra một bản bằng Inno Setup. Hướng dẫn đầy đủ, kèm phần xử lý sự cố, nằm trong [docs/install.md](../install.md).

## Kết nối Claude Desktop với Revit

Thêm máy chủ vào cấu hình ứng dụng khách MCP của bạn. Với Claude Desktop, đó là mục `mcpServers` trong `claude_desktop_config.json`. Codex, Cursor, VS Code và các ứng dụng khách MCP khác dùng cùng các giá trị `command`, `args` và `env` theo định dạng cấu hình riêng của chúng.

Dùng tệp thực thi Python trong môi trường ảo của bạn, và chọn một thư mục workspace mà máy chủ được phép truy cập:

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

Bỏ `MCP_REVIT_HOST_VERSION` để nhắm tới phiên bản Revit đang mở mới nhất. Đặt nó thành một năm như `2024` hoặc `2026` để cố định mục ứng dụng khách vào phiên bản Revit đó. `MCP_REVIT_BRIDGE_URL` ghi đè endpoint cho các thiết lập nâng cao.

Người dùng VS Code có thể bắt đầu từ [`.vscode/mcp.json`](../../.vscode/mcp.json). Người dùng Hermes Desktop có thể bắt đầu từ [`docs/examples/hermes-desktop.json`](../examples/hermes-desktop.json) sau khi thay đường dẫn Python giữ chỗ. Các ứng dụng khách hỗ trợ MCP Bundles có thể cài tệp `.mcpb` từ [bản phát hành mới nhất](https://github.com/Sam-AEC/aec-model-bridge/releases/latest). Add-in Revit vẫn là bắt buộc vì máy chủ giao tiếp với ứng dụng máy tính đang chạy.

### Kiểm tra kết nối

Khởi động lại Revit sau khi cài add-in, mở một mô hình và chạy:

```powershell
$registry = Get-ChildItem "$env:LOCALAPPDATA\AECModelBridge\registry\revit-*.json" | Select-Object -First 1
$switch = Get-Content $registry.FullName -Raw | ConvertFrom-Json
Invoke-RestMethod "$($switch.endpoint)/health"
```

Phản hồi phải cho biết `healthy` và phiên bản Revit đang chạy. Trong Revit, hãy tìm tab ribbon `AEC Bridge`. Bảng Workflows có Open Panel, Health Check, Pending Actions và Reports. Bảng Tools có Config, Help và About.

## Bảo mật

- Cầu nối Revit chỉ lắng nghe trên localhost.
- Máy chủ chỉ đọc và ghi bên trong các thư mục được liệt kê trong `MCP_REVIT_ALLOWED_DIRECTORIES`.
- Các công cụ thay đổi mô hình cần một kế hoạch đã phê duyệt trừ khi bạn tắt phê duyệt.
- Các lệnh gọi công cụ được ghi vào nhật ký kiểm toán, và thông tin bí mật được che đi.

Chi tiết nằm trong [docs/security.md](../security.md). Để báo cáo lỗ hổng bảo mật, hãy làm theo [SECURITY.md](../../SECURITY.md).

## Câu hỏi thường gặp

### Máy chủ MCP cho Revit là gì?

Model Context Protocol (MCP) là một tiêu chuẩn mở cho phép trợ lý AI gọi các công cụ trong phần mềm khác. Máy chủ MCP cho Revit công bố các thao tác của Revit dưới dạng công cụ. Trợ lý chọn công cụ, còn add-in chạy chúng bên trong Revit.

### Những trợ lý AI nào dùng được?

Bất kỳ ứng dụng khách MCP nào có thể khởi chạy máy chủ stdio cục bộ. Chúng tôi có tài liệu cho Claude Desktop, VS Code với GitHub Copilot, Cursor và Codex, cùng các ứng dụng khách đọc cấu hình `mcpServers` tiêu chuẩn. Windsurf, Cline, Roo Code, Continue, Zed, Claude Code và Gemini CLI cũng nên hoạt động theo cách tương tự nhưng chưa được kiểm thử. Xem [khả năng tương thích](../compatibility.md). Trò chuyện trong bảng điều khiển cũng có thể dùng khóa API của Anthropic hoặc các công cụ dòng lệnh `claude` hay `codex` nếu đã cài. Xem [ADR 0012](../0012-native-agent-chat-backend.md).

### AI có thể thay đổi mô hình của tôi mà không hỏi không?

Không ở chế độ mặc định. Các công cụ làm thay đổi mô hình bị chặn cho đến khi kế hoạch được phê duyệt trong bảng điều khiển Revit. Các công cụ chỉ đọc chạy mà không cần phê duyệt. Nếu bạn đặt `MCP_REVIT_APPROVAL_MODE=auto`, bước phê duyệt sẽ bị bỏ qua.

### Nó có gửi mô hình của tôi lên đám mây không?

Máy chủ và add-in chạy trên máy của bạn, còn cầu nối lắng nghe trên localhost. Những gì trợ lý AI nhìn thấy phụ thuộc vào ứng dụng khách bạn dùng: kết quả công cụ được gửi tới nhà cung cấp mô hình của ứng dụng khách đó. Các nhà cung cấp hướng tới đám mây, như Speckle, chỉ chạy khi bạn cấu hình và gọi công cụ của chúng.

### Nó có làm việc với tệp IFC mà không cần Revit không?

Có. Nhà cung cấp IFC đọc tệp bằng IfcOpenShell. Nó có thể trả về siêu dữ liệu tệp, cấu trúc không gian, thuộc tính phần tử và hộp bao (bounding box), chạy truy vấn theo lớp, GUID, tên hoặc thuộc tính, và xác thực lược đồ. Nó không chỉnh sửa tệp IFC.

### Tôi có thể dùng mà không cài Revit không?

Bạn có thể chạy máy chủ ở chế độ mock để phát triển và kiểm thử. Làm việc trực tiếp với mô hình cần Revit 2024 đến 2027 và add-in.

## Phát hành và phiên bản

AEC Model Bridge tuân theo Semantic Versioning. Các bản phát hành được gắn thẻ `vX.Y.Z` trên GitHub, và tệp `VERSION` ở thư mục gốc lưu số phiên bản. Xem [docs/versioning.md](../versioning.md) về quy trình phát hành và [CHANGELOG.md](../../CHANGELOG.md) về những thay đổi trong từng phiên bản.

## Phát triển

```powershell
# Python tests
python -m pytest packages/mcp-server-revit/tests

# Build one Revit version, for example 2026
.\scripts\build-addin.ps1 -RevitVersion 2026 -Configuration Release

# Build all supported versions
.\scripts\package.ps1 -RevitVersion All
```

CI build máy chủ Python và các mục tiêu add-in cho Revit 2024 đến 2027. Hãy đọc [CONTRIBUTING.md](../../CONTRIBUTING.md) trước khi mở pull request.

## Tài liệu

- [Hướng dẫn cài đặt](../install.md)
- [Tài liệu tham khảo công cụ](../tools-generated.md)
- [Kiến trúc](../0001-multi-provider-architecture.md)
- [Tài liệu tham khảo cấu hình](../configuration-reference.md)
- [Bảo mật](../security.md)
- [Ứng dụng khách MCP và registry](../marketplaces.md)
- [Quản lý phiên bản và phát hành](../versioning.md)
- [Toàn bộ tài liệu](../README.md)
- [Hướng dẫn đóng góp](../../CONTRIBUTING.md) và [Quy tắc ứng xử](../../CODE_OF_CONDUCT.md)
- [Những người đóng góp](../../CONTRIBUTORS.md)

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

## Dự án và giấy phép

Được duy trì bởi [A. Sam Mohammad](https://github.com/Sam-AEC).
[LinkedIn](https://www.linkedin.com/in/a-sam-mohammad-92790416b) |
[Issues](https://github.com/Sam-AEC/aec-model-bridge/issues)

[GPL-3.0-or-later kèm Revit Linking Exception, hoặc giấy phép thương mại](../../LICENSING.md).
