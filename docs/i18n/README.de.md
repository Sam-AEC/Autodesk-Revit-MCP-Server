<div align="center">

<img src="../../assets/logo.svg" alt="AEC Model Bridge logo: an isometric model cube with a bridge arch" height="120">

[English](../../README.md) | [简体中文](README.zh-CN.md) | [Español](README.es.md) | [हिन्दी](README.hi.md) | [العربية](README.ar.md) | [Português (BR)](README.pt-BR.md) | [Русский](README.ru.md) | [日本語](README.ja.md) | **Deutsch** | [Français](README.fr.md) | [Bahasa Indonesia](README.id.md) | [Türkçe](README.tr.md) | [한국어](README.ko.md) | [Tiếng Việt](README.vi.md) | [Italiano](README.it.md) | [Polski](README.pl.md) | [繁體中文](README.zh-TW.md)

> Diese Übersetzung wurde mit KI-Unterstützung erstellt. Maßgeblich ist die englische [README](../../README.md); Korrekturen sind per Pull Request willkommen (siehe [CONTRIBUTING.md](../../CONTRIBUTING.md)).

**Fragen Sie Ihre KI zum geöffneten Revit-Modell. Standardmäßig sind Schreibwerkzeuge gesperrt, bis Sie einen Plan freigeben.**

Open-Source-MCP-Server und natives Add-in für Revit 2024 – 2027. Funktioniert mit Claude, Codex und anderen MCP-Clients.

[![CI](https://img.shields.io/github/actions/workflow/status/Sam-AEC/aec-model-bridge/ci.yml?branch=main&style=flat-square&label=CI)](https://github.com/Sam-AEC/aec-model-bridge/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Sam-AEC/aec-model-bridge?style=flat-square&color=0F766E)](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)
[![Revit](https://img.shields.io/badge/Revit-2024--2027-0696D7?style=flat-square)](#unterstützte-revit-versionen)
[![License](https://img.shields.io/badge/license-GPL--3.0%20%2B%20commercial-2563EB?style=flat-square)](../../LICENSING.md)

[Erste Schritte](#schnellstart) | [Beispiel-Workflows](#beispiel-workflows) | [Werkzeuge](../tools-generated.md) | [Dokumentation](#dokumentation) | [Download](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)

</div>

<p align="center">
  <img src="../images/readme/revit-villa-panel.png" alt="Villenmodell in Revit neben dem AEC Model Bridge-Panel mit aktiviertem Dev-Modus." width="900">
</p>

AEC Model Bridge ist der Open-Source-Revit-MCP-Server, mit dem Claude, Codex, Cursor und andere KI-Assistenten Ihr geöffnetes Revit-Modell lesen und bearbeiten können – jede Änderung erst nach Ihrer Freigabe. Er kombiniert einen MCP-Server in Python mit einem nativen Revit-Add-in: Schreibgeschützte Werkzeuge untersuchen das Modell sofort, und Änderungen am Modell erfordern standardmäßig einen freigegebenen Plan. [So funktioniert die Freigabe](#so-funktioniert-die-freigabe).

<p align="center">
  <img src="../images/readme/works-with.svg" alt="Funktioniert mit: Für Claude Desktop, VS Code mit GitHub Copilot, Cursor und Codex gibt es eine dokumentierte Einrichtung. Andere MCP-Clients wie Claude Code, Windsurf, Cline, Continue, Zed und Gemini CLI sollten ebenfalls funktionieren. Anwendungen: Revit 2024 bis 2027, Rhino, Grasshopper, Navisworks (in Arbeit). Daten: IFC, Speckle, Excel, SQLite. Protokoll: MCP über stdio mit Freigabe-Schranke." width="900">
</p>

Die Einrichtung ist für Claude Desktop, VS Code mit GitHub Copilot, Cursor und Codex dokumentiert. Es handelt sich um einen Standard-MCP-Server über stdio, daher sollten auch andere Clients wie Claude Code, Windsurf, Cline, Continue, Zed und Gemini CLI funktionieren. Was dokumentiert und was ungetestet ist, steht unter [Kompatibilität](../compatibility.md).

Derselbe Server enthält außerdem IFC-Prüfung, Rhino- und Grasshopper-Automatisierung sowie die Speckle-Anbindung. Der [Status der Integrationen](#weitere-integrationen) trennt verfügbare Provider von solchen, die noch in Arbeit sind.

## Beispiel-Workflows

Für BIM-Koordinatoren: Modellqualität prüfen, betroffene Elemente ansehen, eine Parameterkorrektur freigeben, dann das Ergebnis kontrollieren und einen Bericht exportieren. Die Beispiele nutzen Werkzeuge aus dem [aktuellen Katalog](../tools-generated.md).

| Workflow | Beispielanfrage | Verwendete Werkzeuge |
| --- | --- | --- |
| Modellprüfung | "Zeige das aktive Dokument, liste die Warnungen auf und finde die betroffenen Elemente." | `revit_get_document_info`, `revit_get_warnings`, `revit_get_elements_by_type` |
| Parameteraktualisierung | "Finde die Wände auf Level 02, zeige ihre Comments-Werte und schlage eine Stapelaktualisierung vor." | `revit_get_elements_by_type`, `revit_get_element_parameters`, `revit_batch_set_parameters` |
| Planerstellung | "Erstelle aus dieser CSV eine Planliste und schlage vor, die Pläne anzulegen und die Ansichten zu platzieren." | `revit_batch_create_sheets_from_csv`, `revit_place_viewport_on_sheet` |
| IFC-Prüfung | "Zeige die Geschosse dieser IFC-Datei, prüfe die Wandeigenschaften und melde Probleme bei der Schemavalidierung." | `ifc_get_spatial_structure`, `ifc_get_properties`, `ifc_validate` |

Für einen ersten Versuch in Revit probieren Sie:

```text
Read the active model's warnings. Group them by description and show the
affected element IDs. Then suggest which issues to investigate first.
```

Probieren Sie dann eine Parameterkorrektur und ersetzen Sie Ebene und Wert durch die Angaben Ihres Projekts:

```text
Find walls on Level 02 and show their current Comments values. Propose setting
Comments to "Coordination reviewed" for the elements I choose. After I approve
the plan in Revit, apply it and read the values back to confirm the result.
```

Für Änderungen erstellt der Assistent mit `plan_actions` einen Plan; Sie prüfen ihn im Revit-Panel, bevor `execute_plan` ihn anwendet. Die IFC-Prüfung läuft ohne Revit.

Die Snapshot-basierten QA/QC- und Berichtsmodule benötigen einen kompatiblen gespeicherten Snapshot. Die aktuelle Übergabe des Snapshots von Revit an das Modul erfordert übereinstimmenden Dateinamen und Arbeitsbereich; ohne `snapshot_id` können generierte Beispieldaten zurückkommen. Für die Live-Prüfung nutzen Sie die direkten Revit-Werkzeuge oben. [Geplante Korrekturen und Demo](../roadmap.md).

## Schnellstart

**Installation mit einem Klick**

[![Install in VS Code](https://img.shields.io/badge/Install_in-VS_Code-0098FF?style=for-the-badge)](../install-buttons.md#vs-code)
[![Install in Cursor](https://img.shields.io/badge/Install_in-Cursor-111111?style=for-the-badge)](https://cursor.com/en/install-mcp?name=aec-model-bridge&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyItLWZyb20iLCJnaXQraHR0cHM6Ly9naXRodWIuY29tL1NhbS1BRUMvYWVjLW1vZGVsLWJyaWRnZSNzdWJkaXJlY3Rvcnk9cGFja2FnZXMvbWNwLXNlcnZlci1yZXZpdCIsImFlYy1tb2RlbC1icmlkZ2UiXSwiZW52Ijp7Ik1DUF9SRVZJVF9NT0RFIjoiYnJpZGdlIn19)
[![Claude Desktop bundle](https://img.shields.io/badge/Claude_Desktop-.mcpb_bundle-D97757?style=for-the-badge)](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)

Die Schaltflächen benötigen nur [uv](https://docs.astral.sh/uv/getting-started/installation/) und sonst keine Einrichtung: Der Server verwendet `~/Documents/AEC Model Bridge` als Arbeitsbereich, sofern Sie keinen eigenen festlegen. Für Claude Desktop laden Sie die `.mcpb`-Datei aus dem neuesten Release herunter und öffnen sie. Für die Arbeit mit einem laufenden Revit brauchen Sie weiterhin Revit und [das Add-in](#revit-add-in-installieren); der Mock-Modus braucht nichts davon.

**Manuelle Einrichtung**

Für die Live-Automatisierung von Revit benötigen Sie Windows, ein lizenziertes Revit 2024 bis 2027, Python 3.11 oder neuer, [uv](https://docs.astral.sh/uv/getting-started/installation/) und das Revit-Add-in ([Installationsschritte](#revit-add-in-installieren)). Fügen Sie dann Folgendes in Ihre `claude_desktop_config.json` ein (Codex, Cursor und VS Code verwenden dieselben Werte; die beiden Verzeichnisvariablen sind optional und verweisen standardmäßig auf den oben genannten Arbeitsbereich):

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

Möchten Sie die Werkzeuge zuerst ohne Revit ansehen? Setzen Sie `"MCP_REVIT_MODE": "mock"`. Der Server startet dann überall, listet jedes Werkzeug mit seinem Schema auf und liefert vorgefertigte Antworten, ohne ein Modell anzufassen. Ein `Dockerfile` für denselben Mock-Modus liegt im Repository-Stammverzeichnis (`docker build -t aec-model-bridge .`, dann `docker run -i --rm aec-model-bridge`).

Sie nutzen VS Code? Der [Quellcode der Erweiterung und die lokalen Installationsschritte](../../extensions/vscode/README.md) registrieren den MCP-Server und zeigen den Verbindungsstatus zu Revit an. Sie ist nicht im Marketplace veröffentlicht.

### Werkzeuge im Überblick

| Bereich | Werkzeuge | Was sie tun |
| --- | --- | --- |
| Revit | 110 | Modell lesen, Elemente, Parameter, Ansichten, Pläne und Bauteillisten erstellen und bearbeiten, Exporte, Worksharing |
| Freigabe | 5 | Modelländerungen planen, prüfen, freigeben, ausführen und zurücksetzen |
| Module | 83 | Snapshot-Prüfung, Parametertabellen, QA/QC-Prüfungen, Rezepte, Berichte, Auswahlen |
| Rhino und Grasshopper | 19 | Geometrie, Layer, Materialien, boolesche Operationen |
| Speckle | 17 | Projekte, Modelle, Versionen, Senden und Empfangen |
| Navisworks | 15 | Modellbaum, Ansichtspunkte, Kollisionsprüfungen (in Arbeit) |
| IFC | 7 | IFC-Dateien ohne Revit lesen: Struktur, Eigenschaften, Validierung |
| Graph, Snapshots, Exporte, Jobs | 21 | Audits des semantischen Graphen, Snapshot-Vergleiche, SQLite-Export, Hintergrundjobs |

In der Standardkonfiguration werden 277 Werkzeuge aufgelistet (gezählt am aktuellen Server im Mock-Modus). Die Autodesk-Data-Werkzeuge erscheinen, wenn APS-Zugangsdaten konfiguriert sind. Die [Werkzeugreferenz](../tools-generated.md) listet jedes Werkzeug auf. Jedes Werkzeug trägt MCP-Annotationen (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`), sodass Clients Lese- von Schreibzugriffen unterscheiden können.

### Erweiterte Revit-Automatisierung

Neben Modellabfragen und Parameteraktualisierungen erstellen die Revit-Werkzeuge Bauteile, Ansichten, Pläne, Bauteillisten, Beschriftungen und Bemaßungen und exportieren IFC-, DWG-, Bild- und Navisworks-Dateien. Unterstützte Operationen und Eingaben finden Sie in der [Werkzeugreferenz](../tools-generated.md).

Für alles, was der Werkzeugkatalog nicht abdeckt, arbeiten `revit_invoke_method`, `revit_reflect_get` und `revit_reflect_set` mit öffentlichen Mitgliedern der Revit-API, und `revit_execute_python` führt IronPython in Revit aus. Diese erweiterten Werkzeuge haben dieselben Berechtigungen wie der Revit-Prozess. Verwenden Sie sie nur mit MCP-Clients und Prompts, denen Sie vertrauen.

## So funktioniert es

Der MCP-Client spricht mit einem Python-Hub. Der Hub leitet jeden Aufruf an den Provider weiter, dem das Werkzeug gehört. Provider für Desktop-Anwendungen sprechen über localhost mit einem kleinen Add-in in dieser Anwendung.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../images/architecture-dark.png">
    <img src="../images/architecture-light.png" alt="Architecture of AEC Model Bridge: an MCP client such as Claude or Codex calls the Python MCP hub, which routes tool calls to the Revit, Rhino, Navisworks, IFC and Speckle providers. The Revit and Rhino providers talk to add-ins over localhost HTTP, the IFC provider reads IFC files with IfcOpenShell, and Navisworks is still in progress." width="900">
  </picture>
</p>

<sub>Diagrammquelle: [architecture.mmd](../diagrams/architecture.mmd). Die Bilder erzeugen Sie mit `python scripts/render_diagrams.py` neu.</sub>

Türkise Kästen funktionieren bereits. Die gelb gestrichelten Kästen sind in Arbeit. Indigofarbene Formen stehen für Daten und externe Dienste.

### So funktioniert die Freigabe

Der Hub stoppt jeden Werkzeugaufruf, der das Modell ändert, sofern er keinen freigegebenen Plan mitbringt. Der Standardmodus ist `required`. Die KI schlägt einen Plan vor, Sie prüfen ihn im Revit-Seitenpanel, und das Add-in führt ihn im Hauptthread von Revit aus, Parameter- und Modellbearbeitungsaktionen jeweils in ihrer eigenen benannten Transaktion; Speichern, Synchronisieren und Skripte nicht, daher deckt Strg+Z sie nicht ab.

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

<sub>Diagrammquelle: [approval-flow.mmd](../diagrams/approval-flow.mmd). Die Bilder erzeugen Sie mit `python scripts/render_diagrams.py` neu.</sub>

Erweist sich ein Plan als falsch, machen Sie ihn mit Strg+Z in Revit rückgängig. Jeder Parameterschreibvorgang ist eine eigene benannte Transaktion, daher kann ein Plan mehrere Tastendrücke brauchen. Ein Rückgängig in einem Schritt für einen ganzen Plan ist geplant, aber nicht gebaut. Ein zweiter Weg ist ein Revert-Plan: Der Assistent entwirft ihn mit `plan_revert` aus dem Nachweis eines ausgeführten Plans, und Sie geben ihn wie jeden anderen Plan frei. `rollback_plan` ist nur für Menschen gedacht und weder eine Schaltfläche noch ein Befehl; verlassen Sie sich daher nicht darauf. Keiner dieser Wege ist bisher in einer echten Revit-Sitzung geprüft (UNVERIFIED). Nicht umkehrbare Vorgänge, etwa das Schreiben von Dateien, werden von keinem davon rückgängig gemacht und verlangen noch keine zweite Bestätigung (geplant). Die Plans-Liste des Panels zeigt nur ausstehende Pläne; `aec-model-bridge-approve show <plan_id>` funktioniert für einen Plan in jedem Zustand, während `proofs/`-Bündel nur für Pläne existieren, die ausgeführt (oder versucht) wurden. Der Ablauf ist in [ADR 0008](../0008-approval-gate-lifecycle.md) beschrieben.

Für unbeaufsichtigte Pipelines können Sie `MCP_REVIT_APPROVAL_MODE=auto` setzen. Das schaltet die Prüfung durch den Menschen ab; verwenden Sie es daher nur in einer kontrollierten Umgebung.

## Unterstützte Revit-Versionen

| Revit-Version | Add-in-Ziel | Build-Werkzeuge |
|---|---|---|
| 2024 | .NET Framework 4.8 | .NET 8 SDK und .NET Framework 4.8 Developer Pack |
| 2025 | .NET 8 for Windows | .NET 8 SDK |
| 2026 | .NET 8 for Windows | .NET 8 SDK |
| 2027 | .NET 10 for Windows | .NET 10 SDK |

Außerdem benötigen Sie Windows 10 oder 11, Python 3.11 oder neuer und eine lizenzierte Revit-Installation der verwendeten Version. Der Mock-Modus führt den Server ohne Revit aus, was für Entwicklung und Tests nützlich ist.

### Weitere Integrationen

| Integration | Status |
|---|---|
| Revit | Verfügbar. Natives C#-Add-in. |
| IFC (IfcOpenShell) | Verfügbar. Liest IFC-Dateien, ohne dass Revit läuft. |
| Rhino und Grasshopper | Verfügbar. Verbindet sich mit dem Rhino-Add-in auf `localhost:3004`. |
| Speckle | Verfügbar. Benötigt eine Speckle-Client-ID in Ihrer Umgebung. |
| Navisworks Manage | In Arbeit. Der Provider und seine Werkzeuge sind registriert. Das Navisworks-Add-in ist nicht fertig. |
| Power BI | In Arbeit. Provider und Werkzeug existieren, sind aber nicht im Hub registriert. |
| Excel, Parquet und DuckDB | Geplant. |

Produktnamen und Logos gehören ihren jeweiligen Inhabern. Das Banner verwendet sie nur, um zu zeigen, womit dieses Projekt zusammenarbeitet.

## Revit-Add-in installieren

**Am einfachsten (Windows):** Laden Sie `AECModelBridge-Setup-<version>.exe` vom [neuesten Release](https://github.com/Sam-AEC/aec-model-bridge/releases/latest) herunter, starten Sie es per Doppelklick, wählen Sie Ihre Revit-Versionen und starten Sie Revit neu. Es installiert das Add-in, den mitgelieferten Python-Server und, wenn Sie das Kontrollkästchen aktivieren, die Einstellungen für Claude Desktop und VS Code, mit einer Sicherung Ihrer aktuellen Einstellungen. Deinstalliert wird über die Windows-Einstellungen. Die folgenden Schritte sind für den Build aus dem Quellcode.

Sie installieren zwei Teile: den Python-MCP-Server und das Revit-Add-in. Die Live-Automatisierung von Revit braucht beide.

### 1. MCP-Server installieren

```powershell
git clone https://github.com/Sam-AEC/aec-model-bridge.git
cd aec-model-bridge

py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e packages/mcp-server-revit
```

### 2. Revit-Add-in installieren

Stellen Sie die Version passend zu Ihrer Revit-Installation ein. Wenn Windows die heruntergeladenen Skripte blockiert, klicken Sie jede `.ps1`-Datei mit der rechten Maustaste an, öffnen Sie die Eigenschaften und wählen Sie vor dem Ausführen „Zulassen“.

```powershell
$RevitVersion = Read-Host "Revit year (2024, 2025, 2026, or 2027)"

.\scripts\package.ps1 -RevitVersion $RevitVersion
.\scripts\install.ps1 -RevitVersion $RevitVersion
```

Das Installationsprogramm legt die versionsspezifischen Binärdateien ab in:

```text
C:\ProgramData\AECModelBridge\bin\<year>
```

Das Add-in-Manifest wird pro Benutzer installiert in:

```text
%APPDATA%\Autodesk\Revit\Addins\<year>
```

Mit `-AllUsers` bei `install.ps1` wird das Manifest stattdessen unter `C:\ProgramData\Autodesk\Revit\Addins\<year>` installiert.

So bereiten Sie die Binärdateien für alle unterstützten Versionen in einem Durchgang vor:

```powershell
.\scripts\package.ps1 -RevitVersion All
```

Jedes [GitHub-Release](https://github.com/Sam-AEC/aec-model-bridge/releases/latest) enthält ein fertiges Paket pro Revit-Jahr, zum Beispiel `aec-model-bridge-revit-2026-<version>.zip`. Entpacken Sie es und führen Sie `.\install.ps1 -RevitVersion 2026` aus, statt aus dem Quellcode zu bauen. Ein Windows-Installer zum Doppelklicken wird mit `scripts/build-installer.ps1` und Inno Setup erzeugt. Die vollständige Anleitung mit Fehlerbehebung steht in [docs/install.md](../install.md).

## Claude Desktop mit Revit verbinden

Tragen Sie den Server in die Konfiguration Ihres MCP-Clients ein. Bei Claude Desktop ist das der Abschnitt `mcpServers` in `claude_desktop_config.json`. Codex, Cursor, VS Code und andere MCP-Clients verwenden dieselben Werte für `command`, `args` und `env` in ihrem eigenen Konfigurationsformat.

Verwenden Sie die Python-Programmdatei Ihrer virtuellen Umgebung und wählen Sie einen Arbeitsordner, auf den der Server zugreifen darf:

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

Lassen Sie `MCP_REVIT_HOST_VERSION` weg, um die neueste geöffnete Revit-Instanz anzusprechen. Setzen Sie es auf ein Jahr wie `2024` oder `2026`, um einen Client-Eintrag auf diese Revit-Version festzulegen. `MCP_REVIT_BRIDGE_URL` überschreibt den Endpunkt für fortgeschrittene Setups.

VS-Code-Nutzer können mit [`.vscode/mcp.json`](../../.vscode/mcp.json) beginnen. Hermes-Desktop-Nutzer können nach dem Ersetzen des Platzhalter-Python-Pfads mit [`docs/examples/hermes-desktop.json`](../examples/hermes-desktop.json) beginnen. Clients mit Unterstützung für MCP Bundles können die `.mcpb`-Datei aus dem [neuesten Release](https://github.com/Sam-AEC/aec-model-bridge/releases/latest) installieren. Das Revit-Add-in ist weiterhin erforderlich, weil der Server mit der laufenden Desktop-Anwendung spricht.

### Verbindung prüfen

Starten Sie Revit nach der Installation des Add-ins neu, öffnen Sie ein Modell und führen Sie aus:

```powershell
$registry = Get-ChildItem "$env:LOCALAPPDATA\AECModelBridge\registry\revit-*.json" | Select-Object -First 1
$switch = Get-Content $registry.FullName -Raw | ConvertFrom-Json
Invoke-RestMethod "$($switch.endpoint)/health"
```

Die Antwort sollte `healthy` und die laufende Revit-Version melden. Suchen Sie in Revit den Ribbon-Reiter `AEC Bridge`. Das Panel Workflows enthält Open Panel, Health Check, Pending Actions und Reports. Das Panel Tools enthält Config, Help und About.

## Sicherheit

- Die Revit-Bridge ist nur über localhost erreichbar.
- Der Server liest und schreibt nur in den Ordnern aus `MCP_REVIT_ALLOWED_DIRECTORIES`.
- Werkzeuge, die das Modell ändern, benötigen einen freigegebenen Plan, sofern Sie die Freigabe nicht abschalten.
- Werkzeugaufrufe werden in ein Audit-Protokoll geschrieben, Secrets (Zugangsdaten) werden maskiert.

Details stehen in [docs/security.md](../security.md). Um eine Sicherheitslücke zu melden, folgen Sie [SECURITY.md](../../SECURITY.md).

## FAQ

### Was ist ein MCP-Server für Revit?

Das Model Context Protocol (MCP) ist ein offener Standard, mit dem KI-Assistenten Werkzeuge in anderer Software aufrufen können. Ein MCP-Server für Revit stellt Revit-Operationen als Werkzeuge bereit. Der Assistent wählt die Werkzeuge aus, und das Add-in führt sie in Revit aus.

### Mit welchen KI-Assistenten funktioniert es?

Mit jedem MCP-Client, der einen lokalen stdio-Server starten kann. Dokumentiert sind Claude Desktop, VS Code mit GitHub Copilot, Cursor und Codex sowie Clients, die eine Standard-`mcpServers`-Konfiguration lesen. Windsurf, Cline, Roo Code, Continue, Zed, Claude Code und Gemini CLI sollten auf dieselbe Weise funktionieren, wurden aber nicht getestet. Siehe [Kompatibilität](../compatibility.md). Der Panel-Chat kann auch einen Anthropic-API-Schlüssel oder die Kommandozeilenwerkzeuge `claude` oder `codex` nutzen, sofern sie installiert sind. Siehe [ADR 0012](../0012-native-agent-chat-backend.md).

### Kann die KI mein Modell ohne Rückfrage ändern?

Im Standardmodus nicht. Werkzeuge, die das Modell ändern, sind gesperrt, bis ein Plan im Revit-Panel freigegeben wurde. Schreibgeschützte Werkzeuge laufen ohne Freigabe. Wenn Sie `MCP_REVIT_APPROVAL_MODE=auto` setzen, entfällt die Freigabe.

### Wird mein Modell in die Cloud gesendet?

Server und Add-in laufen auf Ihrem Rechner, und die Bridge ist nur über localhost erreichbar. Was der KI-Assistent sieht, hängt vom verwendeten Client ab: Die Werkzeugergebnisse gehen an den Modellanbieter dieses Clients. Cloud-Provider wie Speckle laufen nur, wenn Sie sie konfigurieren und ihre Werkzeuge aufrufen.

### Funktioniert es mit IFC-Dateien ohne Revit?

Ja. Der IFC-Provider liest Dateien mit IfcOpenShell. Er liefert Dateimetadaten, die räumliche Struktur, Elementeigenschaften und Bounding Boxes, führt Abfragen nach Klasse, GUID, Name oder Eigenschaft aus und validiert das Schema. IFC-Dateien bearbeitet er nicht.

### Kann ich es ohne installiertes Revit nutzen?

Sie können den Server für Entwicklung und Tests im Mock-Modus ausführen. Für die Arbeit am Live-Modell benötigen Sie Revit 2024 bis 2027 und das Add-in.

## Releases und Versionen

AEC Model Bridge folgt der semantischen Versionierung. Releases werden auf GitHub mit `vX.Y.Z` getaggt, und eine `VERSION`-Datei im Stammverzeichnis enthält die Versionsnummer. Den Release-Prozess beschreibt [docs/versioning.md](../versioning.md), die Änderungen jeder Version stehen in [CHANGELOG.md](../../CHANGELOG.md).

## Entwicklung

```powershell
# Python tests
python -m pytest packages/mcp-server-revit/tests

# Build one Revit version, for example 2026
.\scripts\build-addin.ps1 -RevitVersion 2026 -Configuration Release

# Build all supported versions
.\scripts\package.ps1 -RevitVersion All
```

Die CI baut den Python-Server und die Add-in-Ziele für Revit 2024 bis 2027. Lesen Sie [CONTRIBUTING.md](../../CONTRIBUTING.md), bevor Sie einen Pull Request öffnen.

## Dokumentation

- [Installationsanleitung](../install.md)
- [Werkzeugreferenz](../tools-generated.md)
- [Architektur](../0001-multi-provider-architecture.md)
- [Konfigurationsreferenz](../configuration-reference.md)
- [Sicherheit](../security.md)
- [MCP-Clients und Registry](../marketplaces.md)
- [Versionierung und Releases](../versioning.md)
- [Gesamte Dokumentation](../README.md)
- [Mitwirken](../../CONTRIBUTING.md) und [Verhaltenskodex](../../CODE_OF_CONDUCT.md)
- [Mitwirkende](../../CONTRIBUTORS.md)

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

## Projekt und Lizenz

Gepflegt von [A. Sam Mohammad](https://github.com/Sam-AEC).
[LinkedIn](https://www.linkedin.com/in/a-sam-mohammad-92790416b) |
[Issues](https://github.com/Sam-AEC/aec-model-bridge/issues)

[GPL-3.0-or-later mit der Revit Linking Exception oder eine kommerzielle Lizenz](../../LICENSING.md).
