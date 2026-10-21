<div align="center">

<img src="../../assets/logo.svg" alt="AEC Model Bridge logo: an isometric model cube with a bridge arch" height="120">

[English](../../README.md) | [简体中文](README.zh-CN.md) | [Español](README.es.md) | [हिन्दी](README.hi.md) | [العربية](README.ar.md) | [Português (BR)](README.pt-BR.md) | [Русский](README.ru.md) | [日本語](README.ja.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Bahasa Indonesia](README.id.md) | [Türkçe](README.tr.md) | [한국어](README.ko.md) | [Tiếng Việt](README.vi.md) | **Italiano** | [Polski](README.pl.md) | [繁體中文](README.zh-TW.md)

> Questa traduzione è stata realizzata con l'aiuto dell'IA. Il [README](../../README.md) in inglese è la fonte di riferimento; le correzioni sono benvenute tramite pull request (vedi [CONTRIBUTING.md](../../CONTRIBUTING.md)).

**Interroga la tua IA sul modello Revit che hai aperto. Per impostazione predefinita, gli strumenti di scrittura restano bloccati finché non approvi un piano.**

Server MCP open source e add-in nativo per Revit 2024 – 2027. Funziona con Claude, Codex e altri client MCP.

[![CI](https://img.shields.io/github/actions/workflow/status/Sam-AEC/aec-model-bridge/ci.yml?branch=main&style=flat-square&label=CI)](https://github.com/Sam-AEC/aec-model-bridge/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Sam-AEC/aec-model-bridge?style=flat-square&color=0F766E)](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)
[![Revit](https://img.shields.io/badge/Revit-2024--2027-0696D7?style=flat-square)](#versioni-di-revit-supportate)
[![License](https://img.shields.io/badge/license-GPL--3.0%20%2B%20commercial-2563EB?style=flat-square)](../../LICENSING.md)

[Per iniziare](#avvio-rapido) | [Flussi di lavoro di esempio](#flussi-di-lavoro-di-esempio) | [Strumenti](../tools-generated.md) | [Documentazione](#documentazione) | [Download](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)

</div>

<p align="center">
  <img src="../images/readme/revit-villa-panel.png" alt="Modello di una villa in Revit accanto al pannello AEC Model Bridge con la modalità Dev attivata." width="900">
</p>

AEC Model Bridge è il server MCP open source per Revit che permette a Claude, Codex, Cursor e ad altri assistenti IA di leggere e modificare il modello Revit che hai aperto, con ogni modifica approvata prima da te. Unisce un server MCP in Python a un add-in Revit nativo: gli strumenti di sola lettura ispezionano subito il modello, mentre le modifiche al modello richiedono, per impostazione predefinita, un piano approvato. [Vedi il flusso di approvazione](#come-funziona-lapprovazione).

<p align="center">
  <img src="../images/readme/works-with.svg" alt="Compatibile con: Claude Desktop, VS Code con GitHub Copilot, Cursor e Codex hanno una configurazione documentata. Anche altri client MCP, come Claude Code, Windsurf, Cline, Continue, Zed e Gemini CLI, dovrebbero funzionare. Applicazioni: Revit 2024-2027, Rhino, Grasshopper, Navisworks (in sviluppo). Dati: IFC, Speckle, Excel, SQLite. Protocollo: MCP su stdio con un punto di approvazione." width="900">
</p>

La configurazione è documentata per Claude Desktop, VS Code con GitHub Copilot, Cursor e Codex. È un server MCP stdio standard, quindi dovrebbero funzionare anche altri client come Claude Code, Windsurf, Cline, Continue, Zed e Gemini CLI. Consulta la [compatibilità](../compatibility.md) per sapere cosa è documentato e cosa non è stato testato.

Lo stesso server include l'ispezione IFC, l'automazione di Rhino e Grasshopper e l'integrazione con Speckle. Lo [stato delle integrazioni](#altre-integrazioni) distingue i provider disponibili da quelli ancora in sviluppo.

## Cronologia delle stelle

<a href="https://www.star-history.com/?repos=sam-aec%2Faec-model-bridge&type=date&legend=top-right">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=sam-aec/aec-model-bridge&type=date&theme=dark&legend=bottom-right" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=sam-aec/aec-model-bridge&type=date&legend=bottom-right" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=sam-aec/aec-model-bridge&type=date&legend=bottom-right" />
 </picture>
</a>

## Flussi di lavoro di esempio

Per i coordinatori BIM: controllare la qualità del modello, esaminare gli elementi interessati, approvare una correzione dei parametri, poi verificare i risultati ed esportare un report. Questi esempi usano strumenti del [catalogo attuale](../tools-generated.md).

| Flusso di lavoro | Richiesta di esempio | Strumenti usati |
| --- | --- | --- |
| Verifica del modello | "Mostra il documento attivo, elenca i suoi avvisi e trova gli elementi interessati." | `revit_get_document_info`, `revit_get_warnings`, `revit_get_elements_by_type` |
| Aggiornamento dei parametri | "Trova i muri al Level 02, mostra i loro valori di Comments e proponi un aggiornamento in blocco." | `revit_get_elements_by_type`, `revit_get_element_parameters`, `revit_batch_set_parameters` |
| Produzione degli elaborati | "Prepara un elenco di tavole (sheet) da questo CSV, poi proponi di creare le tavole e di posizionare le viste." | `revit_batch_create_sheets_from_csv`, `revit_place_viewport_on_sheet` |
| Verifica IFC | "Mostra i piani di questo file IFC, ispeziona le proprietà dei muri e segnala i problemi di validazione dello schema." | `ifc_get_spatial_structure`, `ifc_get_properties`, `ifc_validate` |

Per una prima prova in Revit, usa questo prompt:

```text
Read the active model's warnings. Group them by description and show the
affected element IDs. Then suggest which issues to investigate first.
```

Poi prova con una correzione di parametro, sostituendo livello e valore con quelli del tuo progetto:

```text
Find walls on Level 02 and show their current Comments values. Propose setting
Comments to "Coordination reviewed" for the elements I choose. After I approve
the plan in Revit, apply it and read the values back to confirm the result.
```

Per le modifiche, l'assistente crea un piano con `plan_actions`; lo esamini nel pannello di Revit prima che `execute_plan` lo applichi. La verifica IFC funziona senza Revit.

I moduli di QA/QC e di report basati su snapshot richiedono uno snapshot salvato compatibile. L'attuale passaggio dello snapshot da Revit al modulo richiede che nome del file e workspace coincidano; omettendo `snapshot_id` possono essere restituiti dati di esempio generati. Per l'ispezione in tempo reale usa direttamente gli strumenti Revit indicati sopra. [Correzioni previste e demo](../roadmap.md).

## Avvio rapido

**Installazione con un clic**

[![Install in VS Code](https://img.shields.io/badge/Install_in-VS_Code-0098FF?style=for-the-badge)](../install-buttons.md#vs-code)
[![Install in Cursor](https://img.shields.io/badge/Install_in-Cursor-111111?style=for-the-badge)](https://cursor.com/en/install-mcp?name=aec-model-bridge&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyItLWZyb20iLCJnaXQraHR0cHM6Ly9naXRodWIuY29tL1NhbS1BRUMvYWVjLW1vZGVsLWJyaWRnZSNzdWJkaXJlY3Rvcnk9cGFja2FnZXMvbWNwLXNlcnZlci1yZXZpdCIsImFlYy1tb2RlbC1icmlkZ2UiXSwiZW52Ijp7Ik1DUF9SRVZJVF9NT0RFIjoiYnJpZGdlIn19)
[![Claude Desktop bundle](https://img.shields.io/badge/Claude_Desktop-.mcpb_bundle-D97757?style=for-the-badge)](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)

I pulsanti richiedono solo [uv](https://docs.astral.sh/uv/getting-started/installation/) e nessun'altra configurazione: il server usa `~/Documents/AEC Model Bridge` come workspace, a meno che tu non ne imposti uno tuo. Per Claude Desktop, scarica il file `.mcpb` dall'ultima release e aprilo. Per lavorare con Revit in esecuzione servono comunque Revit e [l'add-in](#installare-ladd-in-di-revit); la modalità mock non richiede nulla.

**Configurazione manuale**

Per automatizzare Revit in tempo reale servono Windows, Revit 2024-2027 con licenza, Python 3.11 o successivo, [uv](https://docs.astral.sh/uv/getting-started/installation/) e l'add-in di Revit ([passaggi di installazione](#installare-ladd-in-di-revit)). Poi aggiungi questo al tuo `claude_desktop_config.json` (Codex, Cursor e VS Code usano gli stessi valori; le due variabili di directory sono facoltative e, per impostazione predefinita, puntano al workspace indicato sopra):

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

Vuoi prima dare un'occhiata agli strumenti, senza Revit? Imposta `"MCP_REVIT_MODE": "mock"`. Il server si avvia ovunque, elenca ogni strumento con il suo schema e restituisce risposte predefinite senza toccare alcun modello. Un `Dockerfile` per la stessa modalità mock si trova nella radice del repository (`docker build -t aec-model-bridge .`, poi `docker run -i --rm aec-model-bridge`).

Usi VS Code? Il [sorgente dell'estensione e i passaggi di installazione locale](../../extensions/vscode/README.md) registrano il server MCP e mostrano lo stato della connessione a Revit. Non è stata pubblicata sul Marketplace.

### Gli strumenti in sintesi

| Area | Strumenti | Cosa fanno |
| --- | --- | --- |
| Revit | 103 | Leggere il modello, creare e modificare elementi, parametri, viste, tavole, abachi, esportazioni, condivisione del lavoro (worksharing) |
| Approvazione | 6 | Pianificare, rivedere, approvare, eseguire e annullare le modifiche al modello |
| Moduli | 34 | Ispezione degli snapshot, griglie di parametri, controlli QA/QC, ricette, report, selezioni |
| Rhino e Grasshopper | 19 | Geometria, layer, materiali, operazioni booleane |
| Speckle | 17 | Progetti, modelli, versioni, invio e ricezione |
| Navisworks | 15 | Albero del modello, punti di vista, verifiche di interferenza (in sviluppo) |
| IFC | 7 | Leggere file IFC senza Revit: struttura, proprietà, validazione |
| Grafo, snapshot, esportazioni, job | 18 | Audit del grafo semantico, differenze tra snapshot, esportazione SQLite, job in background |

Nella configurazione predefinita sono elencati 219 strumenti (contati dal server attuale in modalità mock). Gli strumenti Autodesk Data compaiono quando sono configurate le credenziali APS. Il [riferimento degli strumenti](../tools-generated.md) li elenca tutti. Ogni strumento ha annotazioni MCP (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`), così i client possono distinguere le letture dalle scritture.

### Automazione avanzata di Revit

Oltre alle query sul modello e agli aggiornamenti dei parametri, gli strumenti Revit creano elementi edilizi, viste, tavole, abachi, etichette e quote, ed esportano file IFC, DWG, immagini e Navisworks. Consulta il [riferimento degli strumenti](../tools-generated.md) per operazioni e input supportati.

Per ciò che il catalogo non copre, `revit_invoke_method`, `revit_reflect_get` e `revit_reflect_set` lavorano con i membri pubblici dell'API di Revit, e `revit_execute_python` esegue IronPython all'interno di Revit. Questi strumenti avanzati hanno gli stessi permessi del processo Revit. Usali solo con client MCP e prompt di cui ti fidi.

## Come funziona

Il client MCP parla con un unico hub Python. L'hub invia ogni chiamata al provider che possiede lo strumento. I provider per le applicazioni desktop comunicano via localhost con un piccolo add-in all'interno di quell'applicazione.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../images/architecture-dark.png">
    <img src="../images/architecture-light.png" alt="Architecture of AEC Model Bridge: an MCP client such as Claude or Codex calls the Python MCP hub, which routes tool calls to the Revit, Rhino, Navisworks, IFC and Speckle providers. The Revit and Rhino providers talk to add-ins over localhost HTTP, the IFC provider reads IFC files with IfcOpenShell, and Navisworks is still in progress." width="900">
  </picture>
</p>

<sub>Sorgente del diagramma: [architecture.mmd](../diagrams/architecture.mmd). Rigenera le immagini con `python scripts/render_diagrams.py`.</sub>

I riquadri verde acqua funzionano oggi. I riquadri ambra tratteggiati sono in sviluppo. Le forme indaco sono dati e servizi esterni.

### Come funziona l'approvazione

L'hub blocca qualsiasi chiamata a uno strumento che modifica il modello, a meno che non porti con sé un piano approvato. La modalità predefinita è `required`. L'IA propone un piano, tu lo esamini nel pannello laterale di Revit e l'add-in lo esegue nel thread principale di Revit, le azioni sui parametri e di modifica del modello ciascuna in una propria transazione con nome; salvataggio, sincronizzazione e script no, quindi Ctrl+Z non le copre.

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

<sub>Sorgente del diagramma: [approval-flow.mmd](../diagrams/approval-flow.mmd). Rigenera le immagini con `python scripts/render_diagrams.py`.</sub>

Se un piano si rivela sbagliato, annullalo con Ctrl+Z in Revit. Ogni scrittura di parametro è una transazione con nome a sé, quindi un piano può richiedere più pressioni. Un annullamento in un solo passaggio per un intero piano è pianificato, non realizzato. Una seconda via è un piano di ripristino: l'assistente ne redige uno con `plan_revert` a partire dalla prova di un piano eseguito, e tu lo approvi come qualsiasi altro piano. `rollback_plan` è solo per le persone e non è né un pulsante né un comando, quindi non contarci. Nessuna di queste vie è ancora verificata in una sessione Revit reale (UNVERIFIED). Le operazioni che non si possono annullare, come la scrittura di file, non vengono annullate da nessuna di esse e non chiedono ancora una seconda conferma (pianificato). L'elenco Plans del pannello mostra solo i piani in sospeso; `aec-model-bridge-approve show <plan_id>` funziona per un piano in qualsiasi stato, mentre i pacchetti `proofs/` esistono solo per i piani eseguiti (o tentati). Il ciclo di vita è descritto nell'[ADR 0008](../0008-approval-gate-lifecycle.md).

Per le pipeline non presidiate puoi impostare `MCP_REVIT_APPROVAL_MODE=auto`. Questo disattiva il controllo da parte di una persona, quindi usalo solo in un ambiente controllato.

## Versioni di Revit supportate

| Versione di Revit | Target dell'add-in | Strumenti di build |
|---|---|---|
| 2024 | .NET Framework 4.8 | .NET 8 SDK e .NET Framework 4.8 developer pack |
| 2025 | .NET 8 for Windows | .NET 8 SDK |
| 2026 | .NET 8 for Windows | .NET 8 SDK |
| 2027 | .NET 10 for Windows | .NET 10 SDK |

Servono inoltre Windows 10 o 11, Python 3.11 o successivo e un'installazione di Revit con licenza per la versione che usi. La modalità mock esegue il server senza Revit, utile per sviluppo e test.

### Altre integrazioni

| Integrazione | Stato |
|---|---|
| Revit | Disponibile. Add-in nativo in C#. |
| IFC (IfcOpenShell) | Disponibile. Legge file IFC senza che Revit sia in esecuzione. |
| Rhino e Grasshopper | Disponibile. Si collega all'add-in di Rhino su `localhost:3004`. |
| Speckle | Disponibile. Richiede un client ID di Speckle nel tuo ambiente. |
| Navisworks Manage | In sviluppo. Il provider e i suoi strumenti sono registrati. L'add-in di Navisworks non è terminato. |
| Power BI | In sviluppo. Il provider e lo strumento esistono ma non sono registrati nell'hub. |
| Excel, Parquet e DuckDB | Pianificato. |

I nomi dei prodotti e i loghi appartengono ai rispettivi proprietari. Il banner li usa solo per mostrare con cosa funziona questo progetto.

## Installare l'add-in di Revit

**Il modo più semplice (Windows):** scarica `AECModelBridge-Setup-<version>.exe` dall'[ultima release](https://github.com/Sam-AEC/aec-model-bridge/releases/latest), fai doppio clic, scegli le tue versioni di Revit e riavvia Revit. Installa l'add-in, il server Python incluso e, se spunti la casella, le impostazioni di Claude Desktop e VS Code, con un backup delle tue impostazioni attuali. Si disinstalla da Impostazioni di Windows. I passaggi seguenti servono per compilare dai sorgenti.

Devi installare due componenti: il server MCP in Python e l'add-in di Revit. L'automazione di Revit in tempo reale le richiede entrambe.

### 1. Installare il server MCP

```powershell
git clone https://github.com/Sam-AEC/aec-model-bridge.git
cd aec-model-bridge

py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e packages/mcp-server-revit
```

### 2. Installare l'add-in di Revit

Imposta la versione in modo che corrisponda alla tua installazione di Revit. Se Windows blocca gli script scaricati, fai clic con il tasto destro su ogni file `.ps1`, apri Proprietà e seleziona Sblocca prima di eseguirli.

```powershell
$RevitVersion = Read-Host "Revit year (2024, 2025, 2026, or 2027)"

.\scripts\package.ps1 -RevitVersion $RevitVersion
.\scripts\install.ps1 -RevitVersion $RevitVersion
```

Il programma di installazione colloca i binari specifici di ogni versione in:

```text
C:\ProgramData\AECModelBridge\bin\<year>
```

Il manifest dell'add-in viene installato per utente in:

```text
%APPDATA%\Autodesk\Revit\Addins\<year>
```

Usa `-AllUsers` con `install.ps1` per installare invece il manifest in `C:\ProgramData\Autodesk\Revit\Addins\<year>`.

Per preparare i binari di tutte le versioni supportate in un colpo solo:

```powershell
.\scripts\package.ps1 -RevitVersion All
```

Ogni [release di GitHub](https://github.com/Sam-AEC/aec-model-bridge/releases/latest) include un pacchetto già pronto per ogni anno di Revit, ad esempio `aec-model-bridge-revit-2026-<version>.zip`. Decomprimilo ed esegui `.\install.ps1 -RevitVersion 2026` invece di compilare dai sorgenti. Per un installer Windows con doppio clic, `scripts/build-installer.ps1` ne genera uno con Inno Setup. La guida completa, con la risoluzione dei problemi, è in [docs/install.md](../install.md).

## Collegare Claude Desktop a Revit

Aggiungi il server alla configurazione del tuo client MCP. Per Claude Desktop è la sezione `mcpServers` di `claude_desktop_config.json`. Codex, Cursor, VS Code e altri client MCP usano gli stessi valori di `command`, `args` ed `env` nel proprio formato di configurazione.

Usa l'eseguibile Python del tuo ambiente virtuale e scegli una cartella di workspace a cui il server possa accedere:

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

Ometti `MCP_REVIT_HOST_VERSION` per puntare all'istanza di Revit aperta più recente. Impostala su un anno come `2024` o `2026` per vincolare una voce del client a quella versione di Revit. `MCP_REVIT_BRIDGE_URL` sostituisce l'endpoint nelle configurazioni avanzate.

Gli utenti di VS Code possono partire da [`.vscode/mcp.json`](../../.vscode/mcp.json). Gli utenti di Hermes Desktop possono partire da [`docs/examples/hermes-desktop.json`](../examples/hermes-desktop.json) dopo aver sostituito il percorso Python segnaposto. I client che supportano MCP Bundles possono installare il file `.mcpb` dall'[ultima release](https://github.com/Sam-AEC/aec-model-bridge/releases/latest). L'add-in di Revit resta necessario, perché il server comunica con l'applicazione desktop in esecuzione.

### Verificare la connessione

Riavvia Revit dopo aver installato l'add-in, apri un modello ed esegui:

```powershell
$registry = Get-ChildItem "$env:LOCALAPPDATA\AECModelBridge\registry\revit-*.json" | Select-Object -First 1
$switch = Get-Content $registry.FullName -Raw | ConvertFrom-Json
Invoke-RestMethod "$($switch.endpoint)/health"
```

La risposta deve riportare `healthy` e la versione di Revit in esecuzione. In Revit cerca la scheda della barra multifunzione `AEC Bridge`. Il suo pannello Workflows contiene Open Panel, Health Check, Pending Actions e Reports. Il pannello Tools contiene Config, Help e About.

## Sicurezza

- Il bridge di Revit è raggiungibile solo da localhost.
- Il server legge e scrive solo nelle cartelle indicate in `MCP_REVIT_ALLOWED_DIRECTORIES`.
- Gli strumenti che modificano il modello richiedono un piano approvato, a meno che tu non disattivi l'approvazione.
- Le chiamate agli strumenti vengono scritte in un registro di audit e i segreti vengono mascherati.

I dettagli sono in [docs/security.md](../security.md). Per segnalare una vulnerabilità, segui [SECURITY.md](../../SECURITY.md).

## FAQ

### Che cos'è un server MCP per Revit?

Il Model Context Protocol (MCP) è uno standard aperto che permette agli assistenti IA di chiamare strumenti in altri software. Un server MCP per Revit pubblica le operazioni di Revit come strumenti. L'assistente sceglie gli strumenti e l'add-in li esegue dentro Revit.

### Con quali assistenti IA funziona?

Con qualsiasi client MCP in grado di avviare un server stdio locale. Documentiamo Claude Desktop, VS Code con GitHub Copilot, Cursor e Codex, oltre ai client che leggono una configurazione `mcpServers` standard. Windsurf, Cline, Roo Code, Continue, Zed, Claude Code e Gemini CLI dovrebbero funzionare allo stesso modo, ma non sono stati testati. Vedi la [compatibilità](../compatibility.md). La chat del pannello può anche usare una chiave API Anthropic o gli strumenti da riga di comando `claude` o `codex`, se installati. Vedi l'[ADR 0012](../0012-native-agent-chat-backend.md).

### L'IA può modificare il mio modello senza chiedere?

Non nella modalità predefinita. Gli strumenti che modificano il modello sono bloccati finché un piano non viene approvato nel pannello di Revit. Gli strumenti di sola lettura funzionano senza approvazione. Se imposti `MCP_REVIT_APPROVAL_MODE=auto`, l'approvazione viene saltata.

### Invia il mio modello al cloud?

Il server e l'add-in girano sul tuo computer e il bridge è raggiungibile solo da localhost. Ciò che vede l'assistente IA dipende dal client che usi: i risultati degli strumenti vanno al provider del modello di quel client. I provider rivolti al cloud, come Speckle, funzionano solo quando li configuri e ne chiami gli strumenti.

### Funziona con i file IFC senza Revit?

Sì. Il provider IFC legge i file con IfcOpenShell. Può restituire metadati del file, struttura spaziale, proprietà degli elementi e bounding box, eseguire query per classe, GUID, nome o proprietà e validare lo schema. Non modifica i file IFC.

### Posso usarlo senza Revit installato?

Puoi eseguire il server in modalità mock per sviluppo e test. Il lavoro in tempo reale sul modello richiede Revit 2024-2027 e l'add-in.

## Release e versioni

AEC Model Bridge segue il Semantic Versioning. Le release sono etichettate `vX.Y.Z` su GitHub e un file `VERSION` nella radice contiene il numero di versione. Vedi [docs/versioning.md](../versioning.md) per il processo di rilascio e [CHANGELOG.md](../../CHANGELOG.md) per le modifiche di ogni versione.

## Sviluppo

```powershell
# Python tests
python -m pytest packages/mcp-server-revit/tests

# Build one Revit version, for example 2026
.\scripts\build-addin.ps1 -RevitVersion 2026 -Configuration Release

# Build all supported versions
.\scripts\package.ps1 -RevitVersion All
```

La CI compila il server Python e i target dell'add-in per Revit 2024-2027. Leggi [CONTRIBUTING.md](../../CONTRIBUTING.md) prima di aprire una pull request.

## Documentazione

- [Guida all'installazione](../install.md)
- [Riferimento degli strumenti](../tools-generated.md)
- [Architettura](../0001-multi-provider-architecture.md)
- [Riferimento della configurazione](../configuration-reference.md)
- [Sicurezza](../security.md)
- [Client MCP e registry](../marketplaces.md)
- [Versioning e release](../versioning.md)
- [Tutta la documentazione](../README.md)
- [Come contribuire](../../CONTRIBUTING.md) e [Codice di condotta](../../CODE_OF_CONDUCT.md)
- [Collaboratori](../../CONTRIBUTORS.md)

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

## Progetto e licenza

Mantenuto da [A. Sam Mohammad](https://github.com/Sam-AEC).
[LinkedIn](https://www.linkedin.com/in/a-sam-mohammad-92790416b) |
[Issues](https://github.com/Sam-AEC/aec-model-bridge/issues)

[GPL-3.0-or-later con la Revit Linking Exception, oppure licenza commerciale](../../LICENSING.md).
