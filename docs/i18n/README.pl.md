<div align="center">

<img src="../../assets/logo.svg" alt="Logo AEC Model Bridge: izometryczna kostka modelu z łukiem mostu" height="120">

[English](../../README.md) | [简体中文](README.zh-CN.md) | [Español](README.es.md) | [हिन्दी](README.hi.md) | [العربية](README.ar.md) | [Português (BR)](README.pt-BR.md) | [Русский](README.ru.md) | [日本語](README.ja.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Bahasa Indonesia](README.id.md) | [Türkçe](README.tr.md) | [한국어](README.ko.md) | [Tiếng Việt](README.vi.md) | [Italiano](README.it.md) | **Polski** | [繁體中文](README.zh-TW.md)

> To tłumaczenie powstało z pomocą AI. Wiążące jest angielskie [README](../../README.md); poprawki są mile widziane w formie pull requestów (zob. [CONTRIBUTING.md](../../CONTRIBUTING.md)).

**Zapytaj swoje AI o otwarty model Revit. Domyślnie narzędzia zapisu są zablokowane, dopóki nie zatwierdzisz planu.**

Otwartoźródłowy serwer MCP i natywny dodatek do Revit 2024 – 2027. Działa z Claude, Codex i innymi klientami MCP.

[![CI](https://img.shields.io/github/actions/workflow/status/Sam-AEC/aec-model-bridge/ci.yml?branch=main&style=flat-square&label=CI)](https://github.com/Sam-AEC/aec-model-bridge/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Sam-AEC/aec-model-bridge?style=flat-square&color=0F766E)](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)
[![Revit](https://img.shields.io/badge/Revit-2024--2027-0696D7?style=flat-square)](#obsługiwane-wersje-revit)
[![License](https://img.shields.io/badge/license-GPL--3.0%20%2B%20commercial-2563EB?style=flat-square)](../../LICENSING.md)

[Pierwsze kroki](#szybki-start) | [Przykładowe procesy pracy](#przykładowe-procesy-pracy) | [Narzędzia](../tools-generated.md) | [Dokumentacja](#dokumentacja) | [Pobierz](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)

</div>

<p align="center">
  <img src="../images/readme/revit-villa-panel.png" alt="Model willi w Revit obok panelu AEC Model Bridge z włączonym trybem Dev." width="900">
</p>

AEC Model Bridge to otwartoźródłowy serwer MCP dla Revit, który pozwala Claude, Codex, Cursorowi i innym asystentom AI odczytywać i edytować otwarty model Revit, przy czym każdą zmianę najpierw zatwierdzasz Ty. Łączy serwer MCP w Pythonie z natywnym dodatkiem do Revit: narzędzia tylko do odczytu od razu sprawdzają model, a zmiany w modelu domyślnie wymagają zatwierdzonego planu. [Zobacz, jak działa zatwierdzanie](#jak-działa-zatwierdzanie).

<p align="center">
  <img src="../images/readme/works-with.svg" alt="Działa z: Claude Desktop, VS Code z GitHub Copilot, Cursor i Codex mają udokumentowaną konfigurację. Inni klienci MCP, np. Claude Code, Windsurf, Cline, Continue, Zed i Gemini CLI, też powinni działać. Aplikacje: Revit 2024–2027, Rhino, Grasshopper, Navisworks (w trakcie prac). Dane: IFC, Speckle, Excel, SQLite. Protokół: MCP przez stdio z bramką zatwierdzania." width="900">
</p>

Konfiguracja jest udokumentowana dla Claude Desktop, VS Code z GitHub Copilot, Cursor i Codex. To standardowy serwer MCP działający przez stdio, więc inni klienci, np. Claude Code, Windsurf, Cline, Continue, Zed i Gemini CLI, też powinni działać. W [zgodności](../compatibility.md) opisano, co jest udokumentowane, a co nie było testowane.

Ten sam serwer obejmuje też kontrolę plików IFC, automatyzację Rhino i Grasshoppera oraz integrację ze Speckle. [Stan integracji](#inne-integracje) rozróżnia dostawców już dostępnych od tych, nad którymi trwają prace.

## Przykładowe procesy pracy

Dla koordynatorów BIM: sprawdź jakość modelu, przejrzyj elementy, których dotyczą, zatwierdź poprawkę parametrów, a potem zweryfikuj wyniki i wyeksportuj raport. Przykłady korzystają z narzędzi z [aktualnego katalogu](../tools-generated.md).

| Proces | Przykładowe polecenie | Użyte narzędzia |
| --- | --- | --- |
| Przegląd modelu | "Pokaż aktywny dokument, wypisz jego ostrzeżenia i znajdź elementy, których dotyczą." | `revit_get_document_info`, `revit_get_warnings`, `revit_get_elements_by_type` |
| Aktualizacja parametrów | "Znajdź ściany na Level 02, pokaż ich wartości Comments i zaproponuj aktualizację zbiorczą." | `revit_get_elements_by_type`, `revit_get_element_parameters`, `revit_batch_set_parameters` |
| Przygotowanie rysunków | "Przygotuj listę arkuszy z tego pliku CSV, a potem zaproponuj utworzenie arkuszy i rozmieszczenie widoków." | `revit_batch_create_sheets_from_csv`, `revit_place_viewport_on_sheet` |
| Przegląd IFC | "Pokaż kondygnacje tego pliku IFC, sprawdź właściwości ścian i zgłoś problemy z walidacją schematu." | `ifc_get_spatial_structure`, `ifc_get_properties`, `ifc_validate` |

Na pierwszą próbę w Revit wpisz:

```text
Read the active model's warnings. Group them by description and show the
affected element IDs. Then suggest which issues to investigate first.
```

Potem wypróbuj poprawkę parametru, podmieniając poziom i wartość na właściwe dla Twojego projektu:

```text
Find walls on Level 02 and show their current Comments values. Propose setting
Comments to "Coordination reviewed" for the elements I choose. After I approve
the plan in Revit, apply it and read the values back to confirm the result.
```

Przy edycji asystent tworzy plan za pomocą `plan_actions`; przeglądasz go w panelu Revit, zanim `execute_plan` go zastosuje. Przegląd IFC działa bez Revit.

Moduły QA/QC i raportów oparte na migawkach (snapshot) wymagają zgodnej, zapisanej migawki. Obecne przekazanie migawki z Revit do modułu wymaga zgodności nazwy pliku i obszaru roboczego; pominięcie `snapshot_id` może zwrócić wygenerowane dane przykładowe. Do inspekcji na żywo używaj bezpośrednich narzędzi Revit wymienionych wyżej. [Planowane poprawki i demo](../roadmap.md).

## Szybki start

**Instalacja jednym kliknięciem**

[![Install in VS Code](https://img.shields.io/badge/Install_in-VS_Code-0098FF?style=for-the-badge)](../install-buttons.md#vs-code)
[![Install in Cursor](https://img.shields.io/badge/Install_in-Cursor-111111?style=for-the-badge)](https://cursor.com/en/install-mcp?name=aec-model-bridge&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyItLWZyb20iLCJnaXQraHR0cHM6Ly9naXRodWIuY29tL1NhbS1BRUMvYWVjLW1vZGVsLWJyaWRnZSNzdWJkaXJlY3Rvcnk9cGFja2FnZXMvbWNwLXNlcnZlci1yZXZpdCIsImFlYy1tb2RlbC1icmlkZ2UiXSwiZW52Ijp7Ik1DUF9SRVZJVF9NT0RFIjoiYnJpZGdlIn19)
[![Claude Desktop bundle](https://img.shields.io/badge/Claude_Desktop-.mcpb_bundle-D97757?style=for-the-badge)](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)

Przyciski wymagają tylko [uv](https://docs.astral.sh/uv/getting-started/installation/) i żadnej innej konfiguracji: serwer używa `~/Documents/AEC Model Bridge` jako obszaru roboczego, chyba że ustawisz własny. W przypadku Claude Desktop pobierz plik `.mcpb` z najnowszego wydania i otwórz go. Praca na żywo w Revit nadal wymaga Revit i [dodatku](#instalacja-dodatku-do-revit); tryb mock nie wymaga niczego.

**Konfiguracja ręczna**

Do automatyzacji Revit na żywo potrzebujesz Windows, licencjonowanego Revit 2024–2027, Pythona 3.11 lub nowszego, [uv](https://docs.astral.sh/uv/getting-started/installation/) oraz dodatku do Revit ([kroki instalacji](#instalacja-dodatku-do-revit)). Następnie dodaj poniższe do `claude_desktop_config.json` (Codex, Cursor i VS Code używają tych samych wartości; obie zmienne katalogów są opcjonalne i domyślnie wskazują obszar roboczy podany wyżej):

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

Chcesz najpierw obejrzeć narzędzia, bez Revit? Ustaw `"MCP_REVIT_MODE": "mock"`. Serwer uruchomi się wszędzie, wypisze każde narzędzie wraz ze schematem i zwróci gotowe odpowiedzi, nie dotykając żadnego modelu. `Dockerfile` dla tego samego trybu mock znajduje się w katalogu głównym repozytorium (`docker build -t aec-model-bridge .`, a potem `docker run -i --rm aec-model-bridge`).

Używasz VS Code? [Kod źródłowy rozszerzenia i kroki lokalnej instalacji](../../extensions/vscode/README.md) rejestrują serwer MCP i pokazują stan połączenia z Revit. Rozszerzenie nie zostało opublikowane w Marketplace.

### Narzędzia w skrócie

| Obszar | Narzędzia | Co robią |
| --- | --- | --- |
| Revit | 110 | Odczyt modelu, tworzenie i edycja elementów, parametrów, widoków, arkuszy, zestawień, eksporty, współpraca (worksharing) |
| Zatwierdzanie | 5 | Planowanie, przegląd, zatwierdzanie, wykonywanie i wycofywanie zmian modelu |
| Moduły | 83 | Inspekcja migawek, siatki parametrów, kontrole QA/QC, receptury, raporty, zaznaczenia |
| Rhino i Grasshopper | 19 | Geometria, warstwy, materiały, operacje boolowskie |
| Speckle | 17 | Projekty, modele, wersje, wysyłanie i odbieranie |
| Navisworks | 15 | Drzewo modelu, punkty widzenia, testy kolizji (w trakcie prac) |
| IFC | 7 | Odczyt plików IFC bez Revit: struktura, właściwości, walidacja |
| Graf, migawki, eksporty, zadania | 21 | Audyty grafu semantycznego, różnice migawek, eksport do SQLite, zadania w tle |

W konfiguracji domyślnej widocznych jest 277 narzędzi (policzone na aktualnym serwerze w trybie mock). Narzędzia Autodesk Data pojawiają się po skonfigurowaniu poświadczeń APS. [Opis narzędzi](../tools-generated.md) zawiera listę wszystkich. Każde narzędzie ma adnotacje MCP (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`), dzięki czemu klienci odróżniają odczyty od zapisów.

### Zaawansowana automatyzacja Revit

Oprócz zapytań do modelu i aktualizacji parametrów narzędzia Revit tworzą elementy budynku, widoki, arkusze, zestawienia, etykiety i wymiary oraz eksportują pliki IFC, DWG, obrazy i pliki Navisworks. Obsługiwane operacje i dane wejściowe opisuje [opis narzędzi](../tools-generated.md).

W sytuacjach, których katalog narzędzi nie obejmuje, `revit_invoke_method`, `revit_reflect_get` i `revit_reflect_set` działają na publicznych składowych API Revit, a `revit_execute_python` uruchamia IronPython wewnątrz Revit. Te zaawansowane narzędzia mają takie same uprawnienia jak proces Revit. Używaj ich tylko z klientami MCP i promptami, którym ufasz.

## Jak to działa

Klient MCP komunikuje się z jednym hubem w Pythonie. Hub przekazuje każde wywołanie do dostawcy, który posiada dane narzędzie. Dostawcy dla aplikacji desktopowych komunikują się przez localhost z niewielkim dodatkiem wewnątrz tej aplikacji.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../images/architecture-dark.png">
    <img src="../images/architecture-light.png" alt="Architektura AEC Model Bridge: klient MCP, np. Claude lub Codex, wywołuje hub MCP w Pythonie, który kieruje wywołania narzędzi do dostawców Revit, Rhino, Navisworks, IFC i Speckle. Dostawcy Revit i Rhino komunikują się z dodatkami przez HTTP na localhost, dostawca IFC odczytuje pliki IFC za pomocą IfcOpenShell, a Navisworks jest nadal w trakcie prac." width="900">
  </picture>
</p>

<sub>Źródło diagramu: [architecture.mmd](../diagrams/architecture.mmd). Obrazy wygenerujesz ponownie poleceniem `python scripts/render_diagrams.py`.</sub>

Turkusowe ramki działają już dziś. Bursztynowe ramki z linią przerywaną są w trakcie prac. Granatowe kształty to dane i usługi zewnętrzne.

### Jak działa zatwierdzanie

Hub zatrzymuje każde wywołanie narzędzia zmieniającego model, jeśli nie towarzyszy mu zatwierdzony plan. Tryb domyślny to `required`. AI proponuje plan, Ty przeglądasz go w panelu bocznym Revit, a dodatek wykonuje go w głównym wątku Revit, akcje parametrów i edycji modelu każda w osobnej nazwanej transakcji; zapis, synchronizacja i skrypty nie, więc Ctrl+Z ich nie obejmuje.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/Sam-AEC/aec-model-bridge/main/docs/images/readme/readme-workflow-dark.png">
    <img src="https://raw.githubusercontent.com/Sam-AEC/aec-model-bridge/main/docs/images/readme/readme-workflow-light.png" alt="Sprawdź, zaproponuj, zatwierdź, zweryfikuj. Cztery kroki: sprawdzenie znajduje puste pole Mark, propozycja przygotowuje zmianę, zatwierdzenie to decyzja człowieka, weryfikacja odczytuje wartość ponownie. Wartości są przykładowe." width="900">
  </picture>
</p>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../images/approval-flow-dark.png">
    <img src="../images/approval-flow-light.png" alt="Przepływ zatwierdzania: asystent AI tworzy plan przez plan_actions, panel boczny pokazuje proponowane zmiany (liczby, zakres, przed i po), a człowiek zatwierdza w panelu lub poleceniem CLI aec-model-bridge-approve, nigdy przez MCP. Hub sprawdza, czy plan zgadza się z zatwierdzonym narzędziem i argumentami, tylko jeden raz. Revit wykonuje każdą akcję w osobnej transakcji, więc Ctrl+Z cofa jedną akcję na naciśnięcie. Jeśli odrzucisz plan lub nigdy go nie zatwierdzisz, wywołanie jest blokowane, a model pozostaje nietknięty." width="900">
  </picture>
</p>

<sub>Źródło diagramu: [approval-flow.mmd](../diagrams/approval-flow.mmd). Obrazy wygenerujesz ponownie poleceniem `python scripts/render_diagrams.py`.</sub>

Jeśli plan okaże się błędny, cofnij go skrótem Ctrl+Z w Revit. Każdy zapis parametru to osobna nazwana transakcja, więc jeden plan może wymagać kilku naciśnięć. Cofnięcie całego planu jednym krokiem jest planowane, ale jeszcze nie zbudowane. Drugą drogą jest plan cofnięcia: asystent sporządza go za pomocą `plan_revert` na podstawie dowodu wykonanego planu, a zatwierdzasz go jak każdy inny plan. `rollback_plan` jest tylko dla ludzi i nie jest ani przyciskiem, ani poleceniem, więc nie licz na niego. Żadna z tych dróg nie została jeszcze zweryfikowana w prawdziwej sesji Revit (UNVERIFIED). Operacje, których nie da się cofnąć, np. zapis plików, nie są cofane żadną z nich i nie wymagają jeszcze drugiego potwierdzenia (planowane). Lista Plans w panelu pokazuje tylko plany oczekujące; `aec-model-bridge-approve show <plan_id>` działa dla planu w dowolnym stanie, natomiast pakiety `proofs/` istnieją tylko dla planów, które wykonano (lub próbowano wykonać). Cykl życia opisuje [ADR 0008](../0008-approval-gate-lifecycle.md).

W potokach działających bez nadzoru możesz ustawić `MCP_REVIT_APPROVAL_MODE=auto`. To wyłącza kontrolę człowieka, więc używaj tego tylko w kontrolowanym środowisku.

## Obsługiwane wersje Revit

| Wersja Revit | Docelowa platforma dodatku | Narzędzia do kompilacji |
|---|---|---|
| 2024 | .NET Framework 4.8 | .NET 8 SDK i .NET Framework 4.8 developer pack |
| 2025 | .NET 8 for Windows | .NET 8 SDK |
| 2026 | .NET 8 for Windows | .NET 8 SDK |
| 2027 | .NET 10 for Windows | .NET 10 SDK |

Potrzebujesz także Windows 10 lub 11, Pythona 3.11 lub nowszego oraz licencjonowanej instalacji Revit w używanej wersji. Tryb mock uruchamia serwer bez Revit, co przydaje się przy rozwoju i testach.

### Inne integracje

| Integracja | Stan |
|---|---|
| Revit | Dostępne. Natywny dodatek w C#. |
| IFC (IfcOpenShell) | Dostępne. Odczytuje pliki IFC bez uruchomionego Revit. |
| Rhino i Grasshopper | Dostępne. Łączy się z dodatkiem Rhino pod `localhost:3004`. |
| Speckle | Dostępne. Wymaga identyfikatora klienta Speckle w środowisku. |
| Navisworks Manage | W trakcie prac. Dostawca i jego narzędzia są zarejestrowane. Dodatek do Navisworks nie jest ukończony. |
| Power BI | W trakcie prac. Dostawca i narzędzie istnieją, ale nie są zarejestrowane w hubie. |
| Excel, Parquet i DuckDB | Planowane. |

Nazwy produktów i logotypy należą do ich właścicieli. Baner używa ich wyłącznie po to, by pokazać, z czym współpracuje ten projekt.

## Instalacja dodatku do Revit

**Najprościej (Windows):** pobierz `AECModelBridge-Setup-<version>.exe` z [najnowszego wydania](https://github.com/Sam-AEC/aec-model-bridge/releases/latest), kliknij go dwukrotnie, wybierz swoje wersje Revit i uruchom Revit ponownie. Zainstaluje dodatek, dołączony serwer Pythona i, po zaznaczeniu pola, ustawienia Claude Desktop oraz VS Code, z kopią zapasową bieżących ustawień. Odinstalujesz go w Ustawieniach Windows. Poniższe kroki dotyczą kompilacji ze źródeł.

Instalujesz dwie części: serwer MCP w Pythonie i dodatek do Revit. Automatyzacja Revit na żywo wymaga obu.

### 1. Instalacja serwera MCP

```powershell
git clone https://github.com/Sam-AEC/aec-model-bridge.git
cd aec-model-bridge

py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e packages/mcp-server-revit
```

### 2. Instalacja dodatku do Revit

Ustaw wersję zgodną z zainstalowanym Revit. Jeśli Windows blokuje pobrane skrypty, kliknij każdy plik `.ps1` prawym przyciskiem myszy, otwórz Właściwości i przed uruchomieniem wybierz Odblokuj.

```powershell
$RevitVersion = Read-Host "Revit year (2024, 2025, 2026, or 2027)"

.\scripts\package.ps1 -RevitVersion $RevitVersion
.\scripts\install.ps1 -RevitVersion $RevitVersion
```

Instalator umieszcza pliki binarne dla poszczególnych wersji w:

```text
C:\ProgramData\AECModelBridge\bin\<year>
```

Manifest dodatku jest instalowany dla użytkownika w:

```text
%APPDATA%\Autodesk\Revit\Addins\<year>
```

Użyj `-AllUsers` z `install.ps1`, aby zainstalować manifest w `C:\ProgramData\Autodesk\Revit\Addins\<year>`.

Aby przygotować pliki binarne dla wszystkich obsługiwanych wersji naraz:

```powershell
.\scripts\package.ps1 -RevitVersion All
```

Każde [wydanie na GitHubie](https://github.com/Sam-AEC/aec-model-bridge/releases/latest) zawiera gotowy pakiet dla każdego roku Revit, na przykład `aec-model-bridge-revit-2026-<version>.zip`. Rozpakuj go i uruchom `.\install.ps1 -RevitVersion 2026` zamiast kompilować ze źródeł. Skrypt `scripts/build-installer.ps1` buduje za pomocą Inno Setup instalator Windows uruchamiany dwukrotnym kliknięciem. Pełny przewodnik z rozwiązywaniem problemów znajdziesz w [docs/install.md](../install.md).

## Łączenie Claude Desktop z Revit

Dodaj serwer do konfiguracji klienta MCP. W Claude Desktop jest to sekcja `mcpServers` w `claude_desktop_config.json`. Codex, Cursor, VS Code i inni klienci MCP używają tych samych wartości `command`, `args` i `env` we własnym formacie konfiguracji.

Użyj pliku wykonywalnego Pythona z wirtualnego środowiska i wybierz folder obszaru roboczego, do którego serwer ma dostęp:

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

Pomiń `MCP_REVIT_HOST_VERSION`, aby wskazać najnowszą otwartą instancję Revit. Ustaw rok, np. `2024` lub `2026`, aby przypiąć wpis klienta do tej wersji Revit. `MCP_REVIT_BRIDGE_URL` zastępuje punkt końcowy w zaawansowanych konfiguracjach.

Użytkownicy VS Code mogą zacząć od [`.vscode/mcp.json`](../../.vscode/mcp.json). Użytkownicy Hermes Desktop mogą zacząć od [`docs/examples/hermes-desktop.json`](../examples/hermes-desktop.json) po zastąpieniu zastępczej ścieżki Pythona. Klienci obsługujący MCP Bundles mogą zainstalować plik `.mcpb` z [najnowszego wydania](https://github.com/Sam-AEC/aec-model-bridge/releases/latest). Dodatek do Revit jest nadal wymagany, ponieważ serwer komunikuje się z uruchomioną aplikacją desktopową.

### Sprawdzanie połączenia

Po zainstalowaniu dodatku uruchom Revit ponownie, otwórz model i wykonaj:

```powershell
$registry = Get-ChildItem "$env:LOCALAPPDATA\AECModelBridge\registry\revit-*.json" | Select-Object -First 1
$switch = Get-Content $registry.FullName -Raw | ConvertFrom-Json
Invoke-RestMethod "$($switch.endpoint)/health"
```

Odpowiedź powinna zawierać `healthy` oraz wersję uruchomionego Revit. W Revit poszukaj karty wstążki `AEC Bridge`. Jej panel Workflows zawiera Open Panel, Health Check, Pending Actions i Reports. Panel Tools zawiera Config, Help i About.

## Bezpieczeństwo

- Most Revit nasłuchuje wyłącznie na localhost.
- Serwer odczytuje i zapisuje tylko w folderach wymienionych w `MCP_REVIT_ALLOWED_DIRECTORIES`.
- Narzędzia zmieniające model wymagają zatwierdzonego planu, chyba że wyłączysz zatwierdzanie.
- Wywołania narzędzi trafiają do dziennika audytu, a sekrety są maskowane.

Szczegóły są w [docs/security.md](../security.md). Aby zgłosić lukę w zabezpieczeniach, postępuj zgodnie z [SECURITY.md](../../SECURITY.md).

## FAQ

### Czym jest serwer MCP dla Revit?

Model Context Protocol (MCP) to otwarty standard, który pozwala asystentom AI wywoływać narzędzia w innym oprogramowaniu. Serwer MCP dla Revit udostępnia operacje Revit jako narzędzia. Asystent wybiera narzędzia, a dodatek wykonuje je wewnątrz Revit.

### Z którymi asystentami AI to działa?

Z każdym klientem MCP, który potrafi uruchomić lokalny serwer stdio. Dokumentujemy Claude Desktop, VS Code z GitHub Copilot, Cursor i Codex oraz klientów czytających standardową konfigurację `mcpServers`. Windsurf, Cline, Roo Code, Continue, Zed, Claude Code i Gemini CLI powinni działać tak samo, ale nie byli testowani. Zob. [zgodność](../compatibility.md). Czat w panelu może też korzystać z klucza API Anthropic albo z narzędzi wiersza poleceń `claude` lub `codex`, jeśli są zainstalowane. Zob. [ADR 0012](../0012-native-agent-chat-backend.md).

### Czy AI może zmienić mój model bez pytania?

W trybie domyślnym nie. Narzędzia zmieniające model są blokowane, dopóki plan nie zostanie zatwierdzony w panelu Revit. Narzędzia tylko do odczytu działają bez zatwierdzenia. Jeśli ustawisz `MCP_REVIT_APPROVAL_MODE=auto`, zatwierdzanie jest pomijane.

### Czy wysyła mój model do chmury?

Serwer i dodatek działają na Twoim komputerze, a most nasłuchuje na localhost. To, co widzi asystent AI, zależy od używanego klienta: wyniki narzędzi trafiają do dostawcy modelu tego klienta. Dostawcy działający w chmurze, tacy jak Speckle, uruchamiają się tylko wtedy, gdy ich skonfigurujesz i wywołasz ich narzędzia.

### Czy działa z plikami IFC bez Revit?

Tak. Dostawca IFC odczytuje pliki za pomocą IfcOpenShell. Zwraca metadane pliku, strukturę przestrzenną, właściwości elementów i bryły ograniczające, wykonuje zapytania według klasy, GUID, nazwy lub właściwości oraz waliduje schemat. Nie edytuje plików IFC.

### Czy mogę używać tego bez zainstalowanego Revit?

Serwer możesz uruchomić w trybie mock na potrzeby rozwoju i testów. Praca na żywo na modelu wymaga Revit 2024–2027 i dodatku.

## Wydania i wersje

AEC Model Bridge stosuje wersjonowanie semantyczne (Semantic Versioning). Wydania są oznaczane na GitHubie jako `vX.Y.Z`, a numer wersji znajduje się w pliku `VERSION` w katalogu głównym. Proces wydawniczy opisuje [docs/versioning.md](../versioning.md), a zmiany w każdej wersji – [CHANGELOG.md](../../CHANGELOG.md).

## Rozwój

```powershell
# Python tests
python -m pytest packages/mcp-server-revit/tests

# Build one Revit version, for example 2026
.\scripts\build-addin.ps1 -RevitVersion 2026 -Configuration Release

# Build all supported versions
.\scripts\package.ps1 -RevitVersion All
```

CI kompiluje serwer w Pythonie oraz cele dodatku dla Revit 2024–2027. Przed otwarciem pull requesta zapoznaj się z [CONTRIBUTING.md](../../CONTRIBUTING.md).

## Dokumentacja

- [Przewodnik instalacji](../install.md)
- [Opis narzędzi](../tools-generated.md)
- [Architektura](../0001-multi-provider-architecture.md)
- [Opis konfiguracji](../configuration-reference.md)
- [Bezpieczeństwo](../security.md)
- [Klienci MCP i rejestr](../marketplaces.md)
- [Wersjonowanie i wydania](../versioning.md)
- [Cała dokumentacja](../README.md)
- [Jak współtworzyć](../../CONTRIBUTING.md) i [Kodeks postępowania](../../CODE_OF_CONDUCT.md)
- [Współtwórcy](../../CONTRIBUTORS.md)

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

## Projekt i licencja

Utrzymuje [A. Sam Mohammad](https://github.com/Sam-AEC).
[LinkedIn](https://www.linkedin.com/in/a-sam-mohammad-92790416b) |
[Issues](https://github.com/Sam-AEC/aec-model-bridge/issues)

[GPL-3.0-or-later z wyjątkiem Revit Linking Exception lub licencja komercyjna](../../LICENSING.md).
