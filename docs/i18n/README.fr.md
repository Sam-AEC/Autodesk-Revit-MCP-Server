<div align="center">

<img src="../../assets/logo.svg" alt="AEC Model Bridge logo: an isometric model cube with a bridge arch" height="120">

[English](../../README.md) | [简体中文](README.zh-CN.md) | [Español](README.es.md) | [हिन्दी](README.hi.md) | [العربية](README.ar.md) | [Português (BR)](README.pt-BR.md) | [Русский](README.ru.md) | [日本語](README.ja.md) | [Deutsch](README.de.md) | **Français** | [Bahasa Indonesia](README.id.md) | [Türkçe](README.tr.md) | [한국어](README.ko.md) | [Tiếng Việt](README.vi.md) | [Italiano](README.it.md) | [Polski](README.pl.md) | [繁體中文](README.zh-TW.md)

> Cette traduction a été réalisée avec l'aide de l'IA. Le [README](../../README.md) en anglais fait foi ; les corrections sont les bienvenues via une pull request (voir [CONTRIBUTING.md](../../CONTRIBUTING.md)).

**Interrogez votre IA sur le modèle Revit que vous avez ouvert. Par défaut, les outils d'écriture sont bloqués tant que vous n'avez pas approuvé un plan.**

Serveur MCP open source et add-in natif pour Revit 2024 – 2027. Fonctionne avec Claude, Codex et d'autres clients MCP.

[![CI](https://img.shields.io/github/actions/workflow/status/Sam-AEC/aec-model-bridge/ci.yml?branch=main&style=flat-square&label=CI)](https://github.com/Sam-AEC/aec-model-bridge/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Sam-AEC/aec-model-bridge?style=flat-square&color=0F766E)](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)
[![Revit](https://img.shields.io/badge/Revit-2024--2027-0696D7?style=flat-square)](#versions-de-revit-prises-en-charge)
[![License](https://img.shields.io/badge/license-GPL--3.0%20%2B%20commercial-2563EB?style=flat-square)](../../LICENSING.md)

[Démarrage](#démarrage-rapide) | [Exemples de flux de travail](#exemples-de-flux-de-travail) | [Outils](../tools-generated.md) | [Documentation](#documentation) | [Télécharger](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)

</div>

<p align="center">
  <img src="../images/readme/revit-villa-panel.png" alt="Modèle de villa dans Revit à côté du panneau AEC Model Bridge avec le mode Dev activé." width="900">
</p>

AEC Model Bridge est le serveur MCP open source pour Revit qui permet à Claude, Codex, Cursor et à d'autres assistants IA de lire et de modifier le modèle Revit que vous avez ouvert, chaque modification étant d'abord approuvée par vous. Il associe un serveur MCP en Python à un add-in Revit natif : les outils en lecture seule inspectent le modèle immédiatement, et les modifications du modèle exigent par défaut un plan approuvé. [Voir le processus d'approbation](#fonctionnement-de-lapprobation).

<p align="center">
  <img src="../images/readme/works-with.svg" alt="Compatible avec : Claude Desktop, VS Code avec GitHub Copilot, Cursor et Codex disposent d'une configuration documentée. D'autres clients MCP, comme Claude Code, Windsurf, Cline, Continue, Zed et Gemini CLI, devraient aussi fonctionner. Applications : Revit 2024 à 2027, Rhino, Grasshopper, Navisworks (en cours). Données : IFC, Speckle, Excel, SQLite. Protocole : MCP sur stdio avec une porte d'approbation." width="900">
</p>

La configuration est documentée pour Claude Desktop, VS Code avec GitHub Copilot, Cursor et Codex. Il s'agit d'un serveur MCP stdio standard : d'autres clients, comme Claude Code, Windsurf, Cline, Continue, Zed et Gemini CLI, devraient donc fonctionner aussi. Consultez la [compatibilité](../compatibility.md) pour savoir ce qui est documenté et ce qui n'a pas été testé.

Le même serveur inclut l'inspection IFC, l'automatisation de Rhino et Grasshopper, et l'intégration Speckle. L'[état des intégrations](#autres-intégrations) distingue les fournisseurs disponibles de ceux qui sont en cours de développement.

## Exemples de flux de travail

Pour les coordinateurs BIM : contrôler la qualité du modèle, examiner les éléments concernés, approuver une correction de paramètres, puis vérifier les résultats et exporter un rapport. Ces exemples utilisent des outils du [catalogue actuel](../tools-generated.md).

| Flux de travail | Exemple de demande | Outils utilisés |
| --- | --- | --- |
| Contrôle du modèle | "Affiche le document actif, liste ses avertissements et trouve les éléments concernés." | `revit_get_document_info`, `revit_get_warnings`, `revit_get_elements_by_type` |
| Mise à jour de paramètres | "Trouve les murs du Level 02, affiche leurs valeurs Comments et propose une mise à jour par lot." | `revit_get_elements_by_type`, `revit_get_element_parameters`, `revit_batch_set_parameters` |
| Production de plans | "Prépare une liste de feuilles à partir de ce CSV, puis propose de créer les feuilles et de placer les vues." | `revit_batch_create_sheets_from_csv`, `revit_place_viewport_on_sheet` |
| Contrôle IFC | "Affiche les niveaux de ce fichier IFC, inspecte les propriétés des murs et signale les problèmes de validation du schéma." | `ifc_get_spatial_structure`, `ifc_get_properties`, `ifc_validate` |

Pour un premier essai dans Revit, testez ceci :

```text
Read the active model's warnings. Group them by description and show the
affected element IDs. Then suggest which issues to investigate first.
```

Testez ensuite une correction de paramètre, en remplaçant le niveau et la valeur par ceux de votre projet :

```text
Find walls on Level 02 and show their current Comments values. Propose setting
Comments to "Coordination reviewed" for the elements I choose. After I approve
the plan in Revit, apply it and read the values back to confirm the result.
```

Pour les modifications, l'assistant crée un plan avec `plan_actions` ; vous l'examinez dans le panneau Revit avant que `execute_plan` ne l'applique. Le contrôle IFC fonctionne sans Revit.

Les modules de QA/QC et de rapports basés sur des snapshots nécessitent un snapshot enregistré compatible. Le transfert actuel du snapshot de Revit vers le module exige que le nom de fichier et l'espace de travail concordent ; si vous omettez `snapshot_id`, des données d'exemple générées peuvent être renvoyées. Pour l'inspection en direct, utilisez les outils Revit directs ci-dessus. [Correctifs prévus et démo](../roadmap.md).

## Démarrage rapide

**Installation en un clic**

[![Install in VS Code](https://img.shields.io/badge/Install_in-VS_Code-0098FF?style=for-the-badge)](../install-buttons.md#vs-code)
[![Install in Cursor](https://img.shields.io/badge/Install_in-Cursor-111111?style=for-the-badge)](https://cursor.com/en/install-mcp?name=aec-model-bridge&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyItLWZyb20iLCJnaXQraHR0cHM6Ly9naXRodWIuY29tL1NhbS1BRUMvYWVjLW1vZGVsLWJyaWRnZSNzdWJkaXJlY3Rvcnk9cGFja2FnZXMvbWNwLXNlcnZlci1yZXZpdCIsImFlYy1tb2RlbC1icmlkZ2UiXSwiZW52Ijp7Ik1DUF9SRVZJVF9NT0RFIjoiYnJpZGdlIn19)
[![Claude Desktop bundle](https://img.shields.io/badge/Claude_Desktop-.mcpb_bundle-D97757?style=for-the-badge)](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)

Les boutons n'ont besoin que de [uv](https://docs.astral.sh/uv/getting-started/installation/), sans autre configuration : le serveur utilise `~/Documents/AEC Model Bridge` comme espace de travail, sauf si vous en définissez un autre. Pour Claude Desktop, téléchargez le fichier `.mcpb` de la dernière version et ouvrez-le. Le travail en direct dans Revit nécessite toujours Revit et [l'add-in](#installer-ladd-in-revit) ; le mode mock n'a besoin de rien.

**Installation manuelle**

Pour l'automatisation de Revit en direct, il vous faut Windows, Revit 2024 à 2027 sous licence, Python 3.11 ou plus récent, [uv](https://docs.astral.sh/uv/getting-started/installation/) et l'add-in Revit ([étapes d'installation](#installer-ladd-in-revit)). Ajoutez ensuite ceci à votre `claude_desktop_config.json` (Codex, Cursor et VS Code utilisent les mêmes valeurs ; les deux variables de répertoire sont facultatives et pointent par défaut vers l'espace de travail ci-dessus) :

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

Vous voulez d'abord voir les outils, sans Revit ? Définissez `"MCP_REVIT_MODE": "mock"`. Le serveur démarre alors n'importe où, liste chaque outil avec son schéma et renvoie des réponses prédéfinies sans toucher à un modèle. Un `Dockerfile` pour ce même mode mock se trouve à la racine du dépôt (`docker build -t aec-model-bridge .`, puis `docker run -i --rm aec-model-bridge`).

Vous utilisez VS Code ? Les [sources de l'extension et les étapes d'installation locale](../../extensions/vscode/README.md) enregistrent le serveur MCP et affichent l'état de la connexion à Revit. Elle n'a pas été publiée sur le Marketplace.

### Les outils en bref

| Domaine | Outils | Ce qu'ils font |
| --- | --- | --- |
| Revit | 103 | Lire le modèle, créer et modifier des éléments, paramètres, vues, feuilles, nomenclatures, exports, travail collaboratif (worksharing) |
| Approbation | 6 | Planifier, examiner, approuver, exécuter et annuler les modifications du modèle |
| Modules | 34 | Inspection de snapshots, grilles de paramètres, contrôles QA/QC, recettes, rapports, sélections |
| Rhino et Grasshopper | 19 | Géométrie, calques, matériaux, opérations booléennes |
| Speckle | 17 | Projets, modèles, versions, envoi et réception |
| Navisworks | 15 | Arbre du modèle, points de vue, tests de collision (en cours) |
| IFC | 7 | Lire des fichiers IFC sans Revit : structure, propriétés, validation |
| Graphe, snapshots, exports, tâches | 18 | Audits du graphe sémantique, différences entre snapshots, export SQLite, tâches en arrière-plan |

219 outils sont listés dans la configuration par défaut (comptés sur le serveur actuel en mode mock). Les outils Autodesk Data apparaissent lorsque les identifiants APS sont configurés. La [référence des outils](../tools-generated.md) les liste tous. Chaque outil porte des annotations MCP (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`), pour que les clients distinguent les lectures des écritures.

### Automatisation avancée de Revit

En plus des requêtes sur le modèle et des mises à jour de paramètres, les outils Revit créent des éléments de construction, des vues, des feuilles, des nomenclatures, des étiquettes et des cotes, et exportent des fichiers IFC, DWG, des images et des fichiers Navisworks. Consultez la [référence des outils](../tools-generated.md) pour les opérations et les entrées prises en charge.

Pour ce que le catalogue d'outils ne couvre pas, `revit_invoke_method`, `revit_reflect_get` et `revit_reflect_set` travaillent avec les membres publics de l'API Revit, et `revit_execute_python` exécute IronPython dans Revit. Ces outils avancés ont les mêmes permissions que le processus Revit. Ne les utilisez qu'avec des clients MCP et des prompts de confiance.

## Fonctionnement

Le client MCP parle à un seul hub Python. Le hub envoie chaque appel au fournisseur qui détient l'outil. Les fournisseurs pour applications de bureau communiquent via localhost avec un petit add-in installé dans cette application.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../images/architecture-dark.png">
    <img src="../images/architecture-light.png" alt="Architecture of AEC Model Bridge: an MCP client such as Claude or Codex calls the Python MCP hub, which routes tool calls to the Revit, Rhino, Navisworks, IFC and Speckle providers. The Revit and Rhino providers talk to add-ins over localhost HTTP, the IFC provider reads IFC files with IfcOpenShell, and Navisworks is still in progress." width="900">
  </picture>
</p>

<sub>Source du schéma : [architecture.mmd](../diagrams/architecture.mmd). Régénérez les images avec `python scripts/render_diagrams.py`.</sub>

Les cadres turquoise fonctionnent aujourd'hui. Les cadres ambre en pointillés sont en cours de développement. Les formes indigo représentent les données et les services externes.

### Fonctionnement de l'approbation

Le hub bloque tout appel d'outil qui modifie le modèle s'il n'est pas accompagné d'un plan approuvé. Le mode par défaut est `required`. L'IA propose un plan, vous l'examinez dans le panneau latéral de Revit, et l'add-in l'exécute dans le thread principal de Revit, les actions de paramètres et de modification du modèle dans leur propre transaction nommée ; l'enregistrement, la synchronisation et les scripts n'en ont pas, donc Ctrl+Z ne les couvre pas.

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

<sub>Source du schéma : [approval-flow.mmd](../diagrams/approval-flow.mmd). Régénérez les images avec `python scripts/render_diagrams.py`.</sub>

Si un plan se révèle erroné, annulez-le avec Ctrl+Z dans Revit. Chaque écriture de paramètre est sa propre transaction nommée, donc un plan peut demander plusieurs appuis. Une annulation en une seule étape pour un plan entier est prévue, pas encore construite. Une deuxième voie est un plan d'annulation : l'assistant en rédige un avec `plan_revert` à partir de la preuve d'un plan exécuté, et vous l'approuvez comme n'importe quel autre plan. `rollback_plan` est réservé aux personnes et n'est ni un bouton ni une commande ; ne comptez donc pas dessus. Aucune de ces voies n'est encore vérifiée dans une vraie session Revit (UNVERIFIED). Les opérations irréversibles, comme l'écriture de fichiers, ne sont annulées par aucune d'elles et ne demandent pas encore de seconde confirmation (prévu). La liste Plans du panneau n'affiche que les plans en attente ; `aec-model-bridge-approve show <plan_id>` fonctionne pour un plan dans n'importe quel état, tandis que les lots `proofs/` n'existent que pour les plans exécutés (ou tentés). Le cycle de vie est décrit dans l'[ADR 0008](../0008-approval-gate-lifecycle.md).

Pour les pipelines sans surveillance, vous pouvez définir `MCP_REVIT_APPROVAL_MODE=auto`. Cela désactive la vérification par un humain ; ne l'utilisez donc que dans un environnement maîtrisé.

## Versions de Revit prises en charge

| Version de Revit | Cible de l'add-in | Outils de compilation |
|---|---|---|
| 2024 | .NET Framework 4.8 | .NET 8 SDK et .NET Framework 4.8 developer pack |
| 2025 | .NET 8 for Windows | .NET 8 SDK |
| 2026 | .NET 8 for Windows | .NET 8 SDK |
| 2027 | .NET 10 for Windows | .NET 10 SDK |

Il vous faut aussi Windows 10 ou 11, Python 3.11 ou plus récent, et une installation de Revit sous licence pour la version utilisée. Le mode mock exécute le serveur sans Revit, ce qui est utile pour le développement et les tests.

### Autres intégrations

| Intégration | État |
|---|---|
| Revit | Disponible. Add-in C# natif. |
| IFC (IfcOpenShell) | Disponible. Lit les fichiers IFC sans que Revit soit lancé. |
| Rhino et Grasshopper | Disponible. Se connecte à l'add-in Rhino sur `localhost:3004`. |
| Speckle | Disponible. Nécessite un identifiant client Speckle dans votre environnement. |
| Navisworks Manage | En cours. Le fournisseur et ses outils sont enregistrés. L'add-in Navisworks n'est pas terminé. |
| Power BI | En cours. Le fournisseur et l'outil existent, mais ne sont pas enregistrés dans le hub. |
| Excel, Parquet et DuckDB | Prévu. |

Les noms de produits et les logos appartiennent à leurs propriétaires respectifs. La bannière ne les utilise que pour montrer avec quoi ce projet fonctionne.

## Installer l'add-in Revit

**Le plus simple (Windows) :** téléchargez `AECModelBridge-Setup-<version>.exe` depuis la [dernière version](https://github.com/Sam-AEC/aec-model-bridge/releases/latest), double-cliquez dessus, choisissez vos versions de Revit et redémarrez Revit. Il installe l'add-in, le serveur Python fourni et, si vous cochez la case, les paramètres de Claude Desktop et de VS Code, avec une sauvegarde de vos paramètres actuels. Désinstallez-le depuis les Paramètres de Windows. Les étapes ci-dessous servent à compiler depuis les sources.

Vous installez deux éléments : le serveur MCP Python et l'add-in Revit. L'automatisation de Revit en direct a besoin des deux.

### 1. Installer le serveur MCP

```powershell
git clone https://github.com/Sam-AEC/aec-model-bridge.git
cd aec-model-bridge

py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e packages/mcp-server-revit
```

### 2. Installer l'add-in Revit

Réglez la version pour qu'elle corresponde à votre installation de Revit. Si Windows bloque les scripts téléchargés, faites un clic droit sur chaque fichier `.ps1`, ouvrez Propriétés et sélectionnez Débloquer avant de les exécuter.

```powershell
$RevitVersion = Read-Host "Revit year (2024, 2025, 2026, or 2027)"

.\scripts\package.ps1 -RevitVersion $RevitVersion
.\scripts\install.ps1 -RevitVersion $RevitVersion
```

Le programme d'installation place les binaires propres à chaque version dans :

```text
C:\ProgramData\AECModelBridge\bin\<year>
```

Le manifeste de l'add-in est installé par utilisateur dans :

```text
%APPDATA%\Autodesk\Revit\Addins\<year>
```

Utilisez `-AllUsers` avec `install.ps1` pour installer plutôt le manifeste dans `C:\ProgramData\Autodesk\Revit\Addins\<year>`.

Pour préparer les binaires de toutes les versions prises en charge en une seule fois :

```powershell
.\scripts\package.ps1 -RevitVersion All
```

Chaque [version GitHub](https://github.com/Sam-AEC/aec-model-bridge/releases/latest) fournit un paquet prêt à l'emploi pour chaque année de Revit, par exemple `aec-model-bridge-revit-2026-<version>.zip`. Décompressez-le et exécutez `.\install.ps1 -RevitVersion 2026` au lieu de compiler depuis les sources. Pour un installateur Windows à double-clic, `scripts/build-installer.ps1` en génère un avec Inno Setup. Le guide complet, avec le dépannage, se trouve dans [docs/install.md](../install.md).

## Connecter Claude Desktop à Revit

Ajoutez le serveur à la configuration de votre client MCP. Pour Claude Desktop, il s'agit de la section `mcpServers` de `claude_desktop_config.json`. Codex, Cursor, VS Code et les autres clients MCP utilisent les mêmes valeurs `command`, `args` et `env` dans leur propre format de configuration.

Utilisez l'exécutable Python de votre environnement virtuel et choisissez un dossier d'espace de travail auquel le serveur peut accéder :

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

Omettez `MCP_REVIT_HOST_VERSION` pour cibler l'instance Revit ouverte la plus récente. Définissez-la sur une année comme `2024` ou `2026` pour verrouiller une entrée client sur cette version de Revit. `MCP_REVIT_BRIDGE_URL` remplace le point de terminaison pour les configurations avancées.

Les utilisateurs de VS Code peuvent partir de [`.vscode/mcp.json`](../../.vscode/mcp.json). Les utilisateurs de Hermes Desktop peuvent partir de [`docs/examples/hermes-desktop.json`](../examples/hermes-desktop.json) après avoir remplacé le chemin Python fictif. Les clients compatibles avec MCP Bundles peuvent installer le fichier `.mcpb` de la [dernière version](https://github.com/Sam-AEC/aec-model-bridge/releases/latest). L'add-in Revit reste nécessaire, car le serveur communique avec l'application de bureau en cours d'exécution.

### Vérifier la connexion

Redémarrez Revit après avoir installé l'add-in, ouvrez un modèle et exécutez :

```powershell
$registry = Get-ChildItem "$env:LOCALAPPDATA\AECModelBridge\registry\revit-*.json" | Select-Object -First 1
$switch = Get-Content $registry.FullName -Raw | ConvertFrom-Json
Invoke-RestMethod "$($switch.endpoint)/health"
```

La réponse doit indiquer `healthy` et la version de Revit en cours d'exécution. Dans Revit, repérez l'onglet de ruban `AEC Bridge`. Son panneau Workflows contient Open Panel, Health Check, Pending Actions et Reports. Son panneau Tools contient Config, Help et About.

## Sécurité

- Le pont Revit n'est accessible que via localhost.
- Le serveur lit et écrit uniquement dans les dossiers listés dans `MCP_REVIT_ALLOWED_DIRECTORIES`.
- Les outils qui modifient le modèle exigent un plan approuvé, sauf si vous désactivez l'approbation.
- Les appels d'outils sont consignés dans un journal d'audit, et les secrets sont masqués.

Les détails se trouvent dans [docs/security.md](../security.md). Pour signaler une vulnérabilité, suivez [SECURITY.md](../../SECURITY.md).

## FAQ

### Qu'est-ce qu'un serveur MCP pour Revit ?

Le Model Context Protocol (MCP) est un standard ouvert qui permet aux assistants IA d'appeler des outils dans d'autres logiciels. Un serveur MCP pour Revit publie des opérations Revit sous forme d'outils. L'assistant choisit les outils, et l'add-in les exécute dans Revit.

### Avec quels assistants IA cela fonctionne-t-il ?

Avec tout client MCP capable de lancer un serveur stdio local. Nous documentons Claude Desktop, VS Code avec GitHub Copilot, Cursor et Codex, ainsi que les clients qui lisent une configuration `mcpServers` standard. Windsurf, Cline, Roo Code, Continue, Zed, Claude Code et Gemini CLI devraient fonctionner de la même façon, mais n'ont pas été testés. Voir la [compatibilité](../compatibility.md). Le chat du panneau peut aussi utiliser une clé d'API Anthropic ou les outils en ligne de commande `claude` ou `codex`, s'ils sont installés. Voir l'[ADR 0012](../0012-native-agent-chat-backend.md).

### L'IA peut-elle modifier mon modèle sans demander ?

Pas dans le mode par défaut. Les outils qui modifient le modèle sont bloqués tant qu'un plan n'est pas approuvé dans le panneau Revit. Les outils en lecture seule s'exécutent sans approbation. Si vous définissez `MCP_REVIT_APPROVAL_MODE=auto`, l'approbation est ignorée.

### Mon modèle est-il envoyé dans le cloud ?

Le serveur et l'add-in s'exécutent sur votre machine, et le pont n'est accessible que via localhost. Ce que voit l'assistant IA dépend du client utilisé : les résultats des outils sont transmis au fournisseur de modèle de ce client. Les fournisseurs orientés cloud, comme Speckle, ne s'exécutent que lorsque vous les configurez et appelez leurs outils.

### Cela fonctionne-t-il avec des fichiers IFC sans Revit ?

Oui. Le fournisseur IFC lit les fichiers avec IfcOpenShell. Il peut renvoyer les métadonnées du fichier, la structure spatiale, les propriétés des éléments et les boîtes englobantes, exécuter des requêtes par classe, GUID, nom ou propriété, et valider le schéma. Il ne modifie pas les fichiers IFC.

### Puis-je l'utiliser sans Revit installé ?

Vous pouvez exécuter le serveur en mode mock pour le développement et les tests. Le travail en direct sur un modèle nécessite Revit 2024 à 2027 et l'add-in.

## Versions et publications

AEC Model Bridge suit le versionnage sémantique. Les versions sont étiquetées `vX.Y.Z` sur GitHub, et un fichier `VERSION` à la racine contient le numéro de version. Voir [docs/versioning.md](../versioning.md) pour le processus de publication et [CHANGELOG.md](../../CHANGELOG.md) pour les changements de chaque version.

## Développement

```powershell
# Python tests
python -m pytest packages/mcp-server-revit/tests

# Build one Revit version, for example 2026
.\scripts\build-addin.ps1 -RevitVersion 2026 -Configuration Release

# Build all supported versions
.\scripts\package.ps1 -RevitVersion All
```

La CI compile le serveur Python et les cibles de l'add-in pour Revit 2024 à 2027. Lisez [CONTRIBUTING.md](../../CONTRIBUTING.md) avant d'ouvrir une pull request.

## Documentation

- [Guide d'installation](../install.md)
- [Référence des outils](../tools-generated.md)
- [Architecture](../0001-multi-provider-architecture.md)
- [Référence de configuration](../configuration-reference.md)
- [Sécurité](../security.md)
- [Clients MCP et registre](../marketplaces.md)
- [Versionnage et publications](../versioning.md)
- [Toute la documentation](../README.md)
- [Contribuer](../../CONTRIBUTING.md) et [Code de conduite](../../CODE_OF_CONDUCT.md)
- [Contributeurs](../../CONTRIBUTORS.md)

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

## Projet et licence

Maintenu par [A. Sam Mohammad](https://github.com/Sam-AEC).
[LinkedIn](https://www.linkedin.com/in/a-sam-mohammad-92790416b) |
[Issues](https://github.com/Sam-AEC/aec-model-bridge/issues)

[GPL-3.0-or-later avec la Revit Linking Exception, ou une licence commerciale](../../LICENSING.md).
