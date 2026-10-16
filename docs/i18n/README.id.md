<div align="center">

<img src="../../assets/logo.svg" alt="AEC Model Bridge logo: an isometric model cube with a bridge arch" height="120">

[English](../../README.md) | [简体中文](README.zh-CN.md) | [Español](README.es.md) | [हिन्दी](README.hi.md) | [العربية](README.ar.md) | [Português (BR)](README.pt-BR.md) | [Русский](README.ru.md) | [日本語](README.ja.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | **Bahasa Indonesia** | [Türkçe](README.tr.md) | [한국어](README.ko.md) | [Tiếng Việt](README.vi.md) | [Italiano](README.it.md) | [Polski](README.pl.md) | [繁體中文](README.zh-TW.md)

> Terjemahan ini dibuat dengan bantuan AI. README bahasa Inggris ([README](../../README.md)) adalah sumber acuan; koreksi sangat kami hargai melalui pull request (lihat [CONTRIBUTING.md](../../CONTRIBUTING.md)).

**Tanyakan model Revit yang sedang Anda buka kepada AI Anda. Secara default, tool penulisan diblokir sampai Anda menyetujui sebuah rencana.**

Server MCP sumber terbuka dan add-in native untuk Revit 2024 – 2027. Bekerja dengan Claude, Codex, dan klien MCP lainnya.

[![CI](https://img.shields.io/github/actions/workflow/status/Sam-AEC/aec-model-bridge/ci.yml?branch=main&style=flat-square&label=CI)](https://github.com/Sam-AEC/aec-model-bridge/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Sam-AEC/aec-model-bridge?style=flat-square&color=0F766E)](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)
[![Revit](https://img.shields.io/badge/Revit-2024--2027-0696D7?style=flat-square)](#versi-revit-yang-didukung)
[![License](https://img.shields.io/badge/license-GPL--3.0%20%2B%20commercial-2563EB?style=flat-square)](../../LICENSING.md)

[Mulai](#mulai-cepat) | [Contoh alur kerja](#contoh-alur-kerja) | [Tool](../tools-generated.md) | [Dokumentasi](#dokumentasi) | [Unduh](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)

</div>

<p align="center">
  <img src="../images/readme/revit-villa-panel.png" alt="Model vila di Revit di samping panel AEC Model Bridge dengan mode Dev aktif." width="900">
</p>

AEC Model Bridge adalah server MCP Revit sumber terbuka yang memungkinkan Claude, Codex, Cursor, dan asisten AI lain membaca dan mengedit model Revit yang sedang Anda buka, dengan setiap perubahan Anda setujui lebih dulu. Proyek ini menggabungkan server MCP berbasis Python dengan add-in Revit native: tool hanya baca langsung memeriksa model, sedangkan perubahan pada model secara default memerlukan rencana yang sudah disetujui. [Lihat alur persetujuan](#cara-kerja-persetujuan).

<p align="center">
  <img src="../images/readme/works-with.svg" alt="Bekerja dengan: Claude Desktop, VS Code dengan GitHub Copilot, Cursor, dan Codex memiliki pengaturan yang terdokumentasi. Klien MCP lain seperti Claude Code, Windsurf, Cline, Continue, Zed, dan Gemini CLI seharusnya juga dapat bekerja. Aplikasi: Revit 2024 sampai 2027, Rhino, Grasshopper, Navisworks (dalam pengerjaan). Data: IFC, Speckle, Excel, SQLite. Protokol: MCP lewat stdio dengan gerbang persetujuan." width="900">
</p>

Pengaturan didokumentasikan untuk Claude Desktop, VS Code dengan GitHub Copilot, Cursor, dan Codex. Ini adalah server MCP stdio standar, sehingga klien lain seperti Claude Code, Windsurf, Cline, Continue, Zed, dan Gemini CLI seharusnya juga dapat bekerja. Lihat [kompatibilitas](../compatibility.md) untuk bagian yang sudah didokumentasikan dan yang belum diuji.

Server yang sama juga mencakup pemeriksaan IFC, otomatisasi Rhino dan Grasshopper, serta integrasi Speckle. [Status integrasi](#integrasi-lainnya) membedakan provider yang sudah tersedia dari yang masih dalam pengerjaan.

## Contoh alur kerja

Untuk koordinator BIM: periksa kualitas model, tinjau elemen yang terdampak, setujui perbaikan parameter, lalu cek hasilnya dan ekspor laporan. Contoh-contoh ini memakai tool dalam [katalog saat ini](../tools-generated.md).

| Alur kerja | Contoh permintaan | Tool yang dipakai |
| --- | --- | --- |
| Tinjauan model | "Tampilkan dokumen aktif, daftarkan peringatannya, dan temukan elemen yang terdampak." | `revit_get_document_info`, `revit_get_warnings`, `revit_get_elements_by_type` |
| Pembaruan parameter | "Cari dinding di Level 02, tampilkan nilai Comments-nya, dan usulkan pembaruan massal." | `revit_get_elements_by_type`, `revit_get_element_parameters`, `revit_batch_set_parameters` |
| Produksi gambar | "Siapkan daftar sheet dari CSV ini, lalu usulkan pembuatan sheet dan penempatan view." | `revit_batch_create_sheets_from_csv`, `revit_place_viewport_on_sheet` |
| Tinjauan IFC | "Tampilkan lantai (storey) pada file IFC ini, periksa properti dinding, dan laporkan masalah validasi skema." | `ifc_get_spatial_structure`, `ifc_get_properties`, `ifc_validate` |

Untuk percobaan pertama di Revit, coba:

```text
Read the active model's warnings. Group them by description and show the
affected element IDs. Then suggest which issues to investigate first.
```

Lalu coba koreksi parameter, dengan mengganti level dan nilainya sesuai proyek Anda:

```text
Find walls on Level 02 and show their current Comments values. Propose setting
Comments to "Coordination reviewed" for the elements I choose. After I approve
the plan in Revit, apply it and read the values back to confirm the result.
```

Untuk perubahan, asisten membuat rencana dengan `plan_actions`; Anda meninjaunya di panel Revit sebelum `execute_plan` menerapkannya. Tinjauan IFC berjalan tanpa Revit.

Modul QA/QC dan laporan berbasis snapshot memerlukan snapshot tersimpan yang kompatibel. Serah terima snapshot dari Revit ke modul saat ini membutuhkan kecocokan nama file dan workspace; jika `snapshot_id` dihilangkan, data contoh buatan bisa dikembalikan. Gunakan tool Revit langsung di atas untuk pemeriksaan langsung. [Perbaikan yang direncanakan dan demo](../roadmap.md).

## Mulai cepat

**Instalasi sekali klik**

[![Install in VS Code](https://img.shields.io/badge/Install_in-VS_Code-0098FF?style=for-the-badge)](../install-buttons.md#vs-code)
[![Install in Cursor](https://img.shields.io/badge/Install_in-Cursor-111111?style=for-the-badge)](https://cursor.com/en/install-mcp?name=aec-model-bridge&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyItLWZyb20iLCJnaXQraHR0cHM6Ly9naXRodWIuY29tL1NhbS1BRUMvYWVjLW1vZGVsLWJyaWRnZSNzdWJkaXJlY3Rvcnk9cGFja2FnZXMvbWNwLXNlcnZlci1yZXZpdCIsImFlYy1tb2RlbC1icmlkZ2UiXSwiZW52Ijp7Ik1DUF9SRVZJVF9NT0RFIjoiYnJpZGdlIn19)
[![Claude Desktop bundle](https://img.shields.io/badge/Claude_Desktop-.mcpb_bundle-D97757?style=for-the-badge)](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)

Tombol ini hanya membutuhkan [uv](https://docs.astral.sh/uv/getting-started/installation/) tanpa pengaturan lain: server memakai `~/Documents/AEC Model Bridge` sebagai workspace kecuali Anda menentukan sendiri. Untuk Claude Desktop, unduh file `.mcpb` dari rilis terbaru lalu buka. Pekerjaan Revit secara langsung tetap memerlukan Revit dan [add-in](#memasang-add-in-revit); mode mock tidak memerlukan apa pun.

**Pengaturan manual**

Untuk otomatisasi Revit secara langsung, Anda memerlukan Windows, Revit 2024 sampai 2027 berlisensi, Python 3.11 atau lebih baru, [uv](https://docs.astral.sh/uv/getting-started/installation/), dan add-in Revit ([langkah instalasi](#memasang-add-in-revit)). Lalu tambahkan ini ke `claude_desktop_config.json` Anda (Codex, Cursor, dan VS Code memakai nilai yang sama; kedua variabel direktori bersifat opsional dan secara default mengarah ke workspace di atas):

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

Ingin melihat tool-nya dulu tanpa Revit? Atur `"MCP_REVIT_MODE": "mock"`. Server lalu bisa berjalan di mana saja, menampilkan semua tool beserta skemanya, dan mengembalikan respons contoh tanpa menyentuh model. `Dockerfile` untuk mode mock yang sama ada di root repositori (`docker build -t aec-model-bridge .`, lalu `docker run -i --rm aec-model-bridge`).

Memakai VS Code? [Sumber ekstensi dan langkah instalasi lokal](../../extensions/vscode/README.md) mendaftarkan server MCP dan menampilkan status koneksi Revit. Ekstensi ini belum dipublikasikan di Marketplace.

### Ringkasan tool

| Bidang | Tool | Fungsinya |
| --- | --- | --- |
| Revit | 110 | Membaca model, membuat dan mengedit elemen, parameter, view, sheet, schedule, ekspor, worksharing |
| Persetujuan | 5 | Merencanakan, meninjau, menyetujui, menjalankan, dan membatalkan perubahan model |
| Modul | 108 | Inspeksi snapshot, grid parameter, pemeriksaan QA/QC, resep, laporan, seleksi |
| Rhino dan Grasshopper | 19 | Geometri, layer, material, operasi boolean |
| Speckle | 17 | Proyek, model, versi, kirim dan terima |
| Navisworks | 15 | Model tree, viewpoint, uji clash (dalam pengerjaan) |
| IFC | 7 | Membaca file IFC tanpa Revit: struktur, properti, validasi |
| Graf, snapshot, ekspor, job | 21 | Audit graf semantik, selisih snapshot, ekspor SQLite, job latar belakang |

Ada 302 tool yang terdaftar pada pengaturan default (dihitung dari server saat ini dalam mode mock). Tool Autodesk Data muncul saat kredensial APS dikonfigurasi. [Referensi tool](../tools-generated.md) mencantumkan setiap tool. Setiap tool membawa anotasi MCP (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`), sehingga klien dapat membedakan operasi baca dari tulis.

### Otomatisasi Revit lanjutan

Selain kueri model dan pembaruan parameter, tool Revit dapat membuat elemen bangunan, view, sheet, schedule, tag, dan dimensi, serta mengekspor file IFC, DWG, gambar, dan Navisworks. Lihat [referensi tool](../tools-generated.md) untuk operasi dan input yang didukung.

Untuk hal yang tidak tercakup katalog tool, `revit_invoke_method`, `revit_reflect_get`, dan `revit_reflect_set` bekerja dengan anggota Revit API yang bersifat publik, dan `revit_execute_python` menjalankan IronPython di dalam Revit. Tool lanjutan ini memiliki izin yang sama dengan proses Revit. Gunakan hanya dengan klien MCP dan prompt yang Anda percaya.

## Cara kerja

Klien MCP berbicara dengan satu hub Python. Hub meneruskan setiap panggilan ke provider yang memiliki tool tersebut. Provider untuk aplikasi desktop berkomunikasi lewat localhost dengan add-in kecil di dalam aplikasi itu.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../images/architecture-dark.png">
    <img src="../images/architecture-light.png" alt="Architecture of AEC Model Bridge: an MCP client such as Claude or Codex calls the Python MCP hub, which routes tool calls to the Revit, Rhino, Navisworks, IFC and Speckle providers. The Revit and Rhino providers talk to add-ins over localhost HTTP, the IFC provider reads IFC files with IfcOpenShell, and Navisworks is still in progress." width="900">
  </picture>
</p>

<sub>Sumber diagram: [architecture.mmd](../diagrams/architecture.mmd). Buat ulang gambar dengan `python scripts/render_diagrams.py`.</sub>

Kotak berwarna teal sudah berfungsi saat ini. Kotak putus-putus berwarna amber masih dalam pengerjaan. Bentuk berwarna indigo adalah data dan layanan eksternal.

### Cara kerja persetujuan

Hub menghentikan setiap panggilan tool yang mengubah model kecuali panggilan itu membawa rencana yang sudah disetujui. Mode default-nya adalah `required`. AI mengusulkan rencana, Anda meninjaunya di panel samping Revit, lalu add-in menjalankannya di main thread Revit, aksi parameter dan pengeditan model masing-masing dalam transaksi bernamanya sendiri; aksi simpan, sinkronisasi, dan skrip tidak, sehingga Ctrl+Z tidak mencakupnya.

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

<sub>Sumber diagram: [approval-flow.mmd](../diagrams/approval-flow.mmd). Buat ulang gambar dengan `python scripts/render_diagrams.py`.</sub>

Jika sebuah rencana ternyata keliru, batalkan dengan Ctrl+Z di Revit. Setiap penulisan parameter adalah transaksi bernama tersendiri, jadi satu rencana bisa memerlukan beberapa kali penekanan. Undo satu langkah untuk seluruh rencana masih direncanakan, belum dibangun. Jalur kedua adalah rencana pembalikan: asisten menyusunnya dengan `plan_revert` dari bukti rencana yang sudah dieksekusi, dan Anda menyetujuinya seperti rencana lainnya. `rollback_plan` hanya untuk manusia dan bukan tombol maupun perintah, jadi jangan mengandalkannya. Belum ada jalur ini yang diverifikasi di sesi Revit yang sebenarnya (UNVERIFIED). Operasi yang tidak dapat dibatalkan, seperti keluaran file, tidak dibatalkan oleh jalur mana pun dan belum meminta konfirmasi kedua (direncanakan). Daftar Plans di panel hanya menampilkan rencana yang tertunda; `aec-model-bridge-approve show <plan_id>` berfungsi untuk rencana dalam status apa pun, sedangkan bundel `proofs/` hanya ada untuk rencana yang dieksekusi (atau dicoba). Siklus hidupnya ada di [ADR 0008](../0008-approval-gate-lifecycle.md).

Untuk pipeline tanpa pengawasan, Anda dapat mengatur `MCP_REVIT_APPROVAL_MODE=auto`. Ini mematikan pemeriksaan manusia, jadi gunakan hanya di lingkungan yang terkendali.

## Versi Revit yang didukung

| Versi Revit | Target add-in | Tool build |
|---|---|---|
| 2024 | .NET Framework 4.8 | .NET 8 SDK dan .NET Framework 4.8 developer pack |
| 2025 | .NET 8 for Windows | .NET 8 SDK |
| 2026 | .NET 8 for Windows | .NET 8 SDK |
| 2027 | .NET 10 for Windows | .NET 10 SDK |

Anda juga memerlukan Windows 10 atau 11, Python 3.11 atau lebih baru, dan instalasi Revit berlisensi untuk versi yang Anda pakai. Mode mock menjalankan server tanpa Revit, yang berguna untuk pengembangan dan pengujian.

### Integrasi lainnya

| Integrasi | Status |
|---|---|
| Revit | Tersedia. Add-in C# native. |
| IFC (IfcOpenShell) | Tersedia. Membaca file IFC tanpa Revit berjalan. |
| Rhino dan Grasshopper | Tersedia. Terhubung ke add-in Rhino di `localhost:3004`. |
| Speckle | Tersedia. Memerlukan client ID Speckle di lingkungan Anda. |
| Navisworks Manage | Dalam pengerjaan. Provider dan tool-nya sudah terdaftar. Add-in Navisworks belum selesai. |
| Power BI | Dalam pengerjaan. Provider dan tool sudah ada tetapi belum terdaftar di hub. |
| Excel, Parquet, dan DuckDB | Direncanakan. |

Nama produk dan logo adalah milik pemiliknya masing-masing. Banner memakainya hanya untuk menunjukkan apa saja yang dapat bekerja bersama proyek ini.

## Memasang add-in Revit

**Paling mudah (Windows):** unduh `AECModelBridge-Setup-<version>.exe` dari [rilis terbaru](https://github.com/Sam-AEC/aec-model-bridge/releases/latest), klik dua kali, pilih versi Revit Anda, lalu mulai ulang Revit. Installer memasang add-in, server Python bawaan, dan, jika kotaknya Anda centang, pengaturan Claude Desktop dan VS Code, dengan cadangan pengaturan Anda saat ini. Copot pemasangan lewat Pengaturan Windows. Langkah di bawah ini untuk build dari sumber.

Anda memasang dua bagian: server MCP Python dan add-in Revit. Otomatisasi Revit secara langsung membutuhkan keduanya.

### 1. Pasang server MCP

```powershell
git clone https://github.com/Sam-AEC/aec-model-bridge.git
cd aec-model-bridge

py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e packages/mcp-server-revit
```

### 2. Pasang add-in Revit

Atur versi agar sesuai dengan instalasi Revit Anda. Jika Windows memblokir skrip yang diunduh, klik kanan setiap file `.ps1`, buka Properties, dan pilih Unblock sebelum menjalankannya.

```powershell
$RevitVersion = Read-Host "Revit year (2024, 2025, 2026, or 2027)"

.\scripts\package.ps1 -RevitVersion $RevitVersion
.\scripts\install.ps1 -RevitVersion $RevitVersion
```

Installer menaruh binary khusus tiap versi di:

```text
C:\ProgramData\AECModelBridge\bin\<year>
```

Manifest add-in dipasang per pengguna di:

```text
%APPDATA%\Autodesk\Revit\Addins\<year>
```

Gunakan `-AllUsers` pada `install.ps1` untuk memasang manifest di `C:\ProgramData\Autodesk\Revit\Addins\<year>` sebagai gantinya.

Untuk menyiapkan binary semua versi yang didukung sekaligus:

```powershell
.\scripts\package.ps1 -RevitVersion All
```

Setiap [rilis GitHub](https://github.com/Sam-AEC/aec-model-bridge/releases/latest) memiliki paket siap pakai untuk tiap tahun Revit, misalnya `aec-model-bridge-revit-2026-<version>.zip`. Ekstrak lalu jalankan `.\install.ps1 -RevitVersion 2026` alih-alih build dari sumber. Untuk installer Windows yang cukup diklik dua kali, `scripts/build-installer.ps1` membuatnya dengan Inno Setup. Panduan lengkap beserta pemecahan masalah ada di [docs/install.md](../install.md).

## Menghubungkan Claude Desktop ke Revit

Tambahkan server ke konfigurasi klien MCP Anda. Untuk Claude Desktop, itu adalah bagian `mcpServers` di `claude_desktop_config.json`. Codex, Cursor, VS Code, dan klien MCP lain memakai nilai `command`, `args`, dan `env` yang sama dalam format konfigurasi masing-masing.

Gunakan executable Python dari virtual environment Anda, dan pilih folder workspace yang boleh diakses server:

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

Hilangkan `MCP_REVIT_HOST_VERSION` untuk menargetkan instance Revit terbuka yang terbaru. Atur ke tahun seperti `2024` atau `2026` untuk mengunci entri klien ke versi Revit tersebut. `MCP_REVIT_BRIDGE_URL` menimpa endpoint untuk pengaturan lanjutan.

Pengguna VS Code dapat memulai dari [`.vscode/mcp.json`](../../.vscode/mcp.json). Pengguna Hermes Desktop dapat memulai dari [`docs/examples/hermes-desktop.json`](../examples/hermes-desktop.json) setelah mengganti path Python placeholder. Klien yang mendukung MCP Bundles dapat memasang file `.mcpb` dari [rilis terbaru](https://github.com/Sam-AEC/aec-model-bridge/releases/latest). Add-in Revit tetap diperlukan, karena server berkomunikasi dengan aplikasi desktop yang sedang berjalan.

### Memeriksa koneksi

Mulai ulang Revit setelah memasang add-in, buka sebuah model, lalu jalankan:

```powershell
$registry = Get-ChildItem "$env:LOCALAPPDATA\AECModelBridge\registry\revit-*.json" | Select-Object -First 1
$switch = Get-Content $registry.FullName -Raw | ConvertFrom-Json
Invoke-RestMethod "$($switch.endpoint)/health"
```

Respons harus menunjukkan `healthy` dan versi Revit yang berjalan. Di Revit, cari tab ribbon `AEC Bridge`. Panel Workflows berisi Open Panel, Health Check, Pending Actions, dan Reports. Panel Tools berisi Config, Help, dan About.

## Keamanan

- Bridge Revit hanya mendengarkan di localhost.
- Server hanya membaca dan menulis di dalam folder yang tercantum di `MCP_REVIT_ALLOWED_DIRECTORIES`.
- Tool yang mengubah model memerlukan rencana yang disetujui kecuali Anda mematikan persetujuan.
- Panggilan tool dicatat dalam log audit, dan rahasia disamarkan.

Detailnya ada di [docs/security.md](../security.md). Untuk melaporkan kerentanan, ikuti [SECURITY.md](../../SECURITY.md).

## FAQ

### Apa itu server MCP untuk Revit?

Model Context Protocol (MCP) adalah standar terbuka yang memungkinkan asisten AI memanggil tool di perangkat lunak lain. Server MCP untuk Revit menyediakan operasi Revit sebagai tool. Asisten memilih tool-nya, dan add-in menjalankannya di dalam Revit.

### Asisten AI apa saja yang bisa dipakai?

Klien MCP apa pun yang dapat menjalankan server stdio lokal. Kami mendokumentasikan Claude Desktop, VS Code dengan GitHub Copilot, Cursor, dan Codex, serta klien yang membaca konfigurasi `mcpServers` standar. Windsurf, Cline, Roo Code, Continue, Zed, Claude Code, dan Gemini CLI seharusnya bekerja dengan cara yang sama, tetapi belum diuji. Lihat [kompatibilitas](../compatibility.md). Chat di panel juga dapat memakai API key Anthropic atau tool command-line `claude` atau `codex` jika terpasang. Lihat [ADR 0012](../0012-native-agent-chat-backend.md).

### Bisakah AI mengubah model saya tanpa bertanya?

Tidak pada mode default. Tool yang mengubah model diblokir sampai rencana disetujui di panel Revit. Tool hanya baca berjalan tanpa persetujuan. Jika Anda mengatur `MCP_REVIT_APPROVAL_MODE=auto`, persetujuan dilewati.

### Apakah model saya dikirim ke cloud?

Server dan add-in berjalan di komputer Anda, dan bridge mendengarkan di localhost. Apa yang dilihat asisten AI bergantung pada klien yang Anda pakai: hasil tool dikirim ke penyedia model klien tersebut. Provider yang terhubung ke cloud, seperti Speckle, hanya berjalan saat Anda mengonfigurasinya dan memanggil tool-nya.

### Apakah bisa bekerja dengan file IFC tanpa Revit?

Ya. Provider IFC membaca file dengan IfcOpenShell. Provider ini dapat mengembalikan metadata file, struktur spasial, properti elemen dan bounding box, menjalankan kueri berdasarkan class, GUID, nama, atau properti, serta memvalidasi skema. Provider ini tidak mengedit file IFC.

### Bisakah dipakai tanpa Revit terpasang?

Anda dapat menjalankan server dalam mode mock untuk pengembangan dan pengujian. Pekerjaan model secara langsung memerlukan Revit 2024 sampai 2027 dan add-in.

## Rilis dan versi

AEC Model Bridge mengikuti Semantic Versioning. Rilis diberi tag `vX.Y.Z` di GitHub, dan file `VERSION` di root menyimpan nomor versinya. Lihat [docs/versioning.md](../versioning.md) untuk proses rilis dan [CHANGELOG.md](../../CHANGELOG.md) untuk perubahan di tiap versi.

## Pengembangan

```powershell
# Python tests
python -m pytest packages/mcp-server-revit/tests

# Build one Revit version, for example 2026
.\scripts\build-addin.ps1 -RevitVersion 2026 -Configuration Release

# Build all supported versions
.\scripts\package.ps1 -RevitVersion All
```

CI membangun server Python dan target add-in untuk Revit 2024 sampai 2027. Baca [CONTRIBUTING.md](../../CONTRIBUTING.md) sebelum membuka pull request.

## Dokumentasi

- [Panduan instalasi](../install.md)
- [Referensi tool](../tools-generated.md)
- [Arsitektur](../0001-multi-provider-architecture.md)
- [Referensi konfigurasi](../configuration-reference.md)
- [Keamanan](../security.md)
- [Klien MCP dan registry](../marketplaces.md)
- [Versioning dan rilis](../versioning.md)
- [Semua dokumentasi](../README.md)
- [Kontribusi](../../CONTRIBUTING.md) dan [Kode Etik](../../CODE_OF_CONDUCT.md)
- [Kontributor](../../CONTRIBUTORS.md)

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

## Proyek dan lisensi

Dikelola oleh [A. Sam Mohammad](https://github.com/Sam-AEC).
[LinkedIn](https://www.linkedin.com/in/a-sam-mohammad-92790416b) |
[Issues](https://github.com/Sam-AEC/aec-model-bridge/issues)

[GPL-3.0-or-later dengan Revit Linking Exception, atau lisensi komersial](../../LICENSING.md).
