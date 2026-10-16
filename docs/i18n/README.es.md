<div align="center">

<img src="../../assets/logo.svg" alt="AEC Model Bridge logo: an isometric model cube with a bridge arch" height="120">

[English](../../README.md) | [简体中文](README.zh-CN.md) | **Español** | [हिन्दी](README.hi.md) | [العربية](README.ar.md) | [Português (BR)](README.pt-BR.md) | [Русский](README.ru.md) | [日本語](README.ja.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Bahasa Indonesia](README.id.md) | [Türkçe](README.tr.md) | [한국어](README.ko.md) | [Tiếng Việt](README.vi.md) | [Italiano](README.it.md) | [Polski](README.pl.md) | [繁體中文](README.zh-TW.md)

> Esta traducción se ha realizado con ayuda de IA. El [README](../../README.md) en inglés es la fuente de referencia; las correcciones son bienvenidas mediante pull request (consulta [CONTRIBUTING.md](../../CONTRIBUTING.md)).

**Pregunta a tu IA sobre el modelo de Revit que tienes abierto. De forma predeterminada, las herramientas de escritura quedan bloqueadas hasta que apruebes un plan.**

Servidor MCP de código abierto y complemento nativo para Revit 2024 – 2027. Funciona con Claude, Codex y otros clientes MCP.

[![CI](https://img.shields.io/github/actions/workflow/status/Sam-AEC/aec-model-bridge/ci.yml?branch=main&style=flat-square&label=CI)](https://github.com/Sam-AEC/aec-model-bridge/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Sam-AEC/aec-model-bridge?style=flat-square&color=0F766E)](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)
[![Revit](https://img.shields.io/badge/Revit-2024--2027-0696D7?style=flat-square)](#versiones-de-revit-compatibles)
[![License](https://img.shields.io/badge/license-GPL--3.0%20%2B%20commercial-2563EB?style=flat-square)](../../LICENSING.md)

[Primeros pasos](#inicio-rápido) | [Flujos de trabajo de ejemplo](#flujos-de-trabajo-de-ejemplo) | [Herramientas](../tools-generated.md) | [Documentación](#documentación) | [Descargar](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)

</div>

<p align="center">
  <img src="../images/readme/revit-villa-panel.png" alt="Modelo de una villa en Revit junto al panel de AEC Model Bridge con el modo Dev activado." width="900">
</p>

AEC Model Bridge es el servidor MCP de código abierto para Revit que permite a Claude,
Codex, Cursor y otros asistentes de IA leer y editar el modelo de Revit que tienes abierto,
con cada cambio aprobado antes por ti. Combina un servidor MCP en Python con un complemento
nativo de Revit: las herramientas de solo lectura inspeccionan el modelo al instante y, por
defecto, los cambios en el modelo exigen un plan aprobado. [Consulta el flujo de aprobación](#cómo-funciona-la-aprobación).

<p align="center">
  <img src="../images/readme/works-with.svg" alt="Compatible con: Claude Desktop, VS Code con GitHub Copilot, Cursor y Codex tienen configuración documentada. Otros clientes MCP, como Claude Code, Windsurf, Cline, Continue, Zed y Gemini CLI, también deberían funcionar. Aplicaciones: Revit 2024 a 2027, Rhino, Grasshopper, Navisworks (en desarrollo). Datos: IFC, Speckle, Excel, SQLite. Protocolo: MCP sobre stdio con una puerta de aprobación." width="900">
</p>

La configuración está documentada para Claude Desktop, VS Code con GitHub Copilot, Cursor y
Codex. Es un servidor MCP estándar por stdio, así que otros clientes, como Claude Code,
Windsurf, Cline, Continue, Zed y Gemini CLI, también deberían funcionar. Consulta la
[compatibilidad](../compatibility.md) para ver qué está documentado y qué no se ha probado.

El mismo servidor incluye inspección de IFC, automatización de Rhino y Grasshopper
e integración con Speckle. El [estado de las integraciones](#otras-integraciones) distingue
los proveedores disponibles de los que están en desarrollo.

## Flujos de trabajo de ejemplo

Para coordinadores BIM: inspeccionar la calidad del modelo, revisar los elementos afectados,
aprobar una corrección de parámetros, comprobar los resultados y exportar un informe.
Estos ejemplos usan herramientas del [catálogo actual](../tools-generated.md).

| Flujo de trabajo | Solicitud de ejemplo | Herramientas utilizadas |
| --- | --- | --- |
| Revisión del modelo | "Muestra el documento activo, lista sus advertencias y encuentra los elementos afectados." | `revit_get_document_info`, `revit_get_warnings`, `revit_get_elements_by_type` |
| Actualización de parámetros | "Busca los muros del Level 02, muestra los valores de Comments y propón una actualización por lotes." | `revit_get_elements_by_type`, `revit_get_element_parameters`, `revit_batch_set_parameters` |
| Producción de planos | "Prepara una lista de hojas a partir de este CSV y propón crear las hojas y colocar las vistas." | `revit_batch_create_sheets_from_csv`, `revit_place_viewport_on_sheet` |
| Revisión de IFC | "Muestra las plantas de este archivo IFC, inspecciona las propiedades de los muros e informa de los problemas de validación del esquema." | `ifc_get_spatial_structure`, `ifc_get_properties`, `ifc_validate` |

Para empezar en Revit, prueba esto:

```text
Read the active model's warnings. Group them by description and show the
affected element IDs. Then suggest which issues to investigate first.
```

Después prueba una corrección de parámetros, sustituyendo el nivel y el valor por los de tu proyecto:

```text
Find walls on Level 02 and show their current Comments values. Propose setting
Comments to "Coordination reviewed" for the elements I choose. After I approve
the plan in Revit, apply it and read the values back to confirm the result.
```

Para las ediciones, el asistente crea un plan con `plan_actions`; tú lo revisas en
el panel de Revit antes de que `execute_plan` lo aplique. La revisión de IFC funciona sin Revit.

Los módulos de QA/QC y de informes basados en instantáneas (snapshots) requieren una instantánea guardada compatible.
El traspaso actual de la instantánea de Revit al módulo exige que coincidan el nombre de archivo y el espacio de trabajo;
si omites `snapshot_id`, se pueden devolver datos de ejemplo generados. Usa las
herramientas directas de Revit indicadas arriba para la inspección en vivo. [Correcciones previstas y demo](../roadmap.md).

## Inicio rápido

**Instalación con un clic**

[![Install in VS Code](https://img.shields.io/badge/Install_in-VS_Code-0098FF?style=for-the-badge)](../install-buttons.md#vs-code)
[![Install in Cursor](https://img.shields.io/badge/Install_in-Cursor-111111?style=for-the-badge)](https://cursor.com/en/install-mcp?name=aec-model-bridge&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyItLWZyb20iLCJnaXQraHR0cHM6Ly9naXRodWIuY29tL1NhbS1BRUMvYWVjLW1vZGVsLWJyaWRnZSNzdWJkaXJlY3Rvcnk9cGFja2FnZXMvbWNwLXNlcnZlci1yZXZpdCIsImFlYy1tb2RlbC1icmlkZ2UiXSwiZW52Ijp7Ik1DUF9SRVZJVF9NT0RFIjoiYnJpZGdlIn19)
[![Claude Desktop bundle](https://img.shields.io/badge/Claude_Desktop-.mcpb_bundle-D97757?style=for-the-badge)](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)

Los botones solo necesitan [uv](https://docs.astral.sh/uv/getting-started/installation/)
y ninguna otra configuración: el servidor usa `~/Documents/AEC Model Bridge` como
espacio de trabajo salvo que definas el tuyo. Para Claude Desktop, descarga el archivo `.mcpb`
de la última versión y ábrelo. El trabajo en vivo con Revit sigue requiriendo Revit y
[el complemento](#instalar-el-complemento-de-revit); el modo mock no necesita nada.

**Configuración manual**

Para la automatización de Revit en vivo necesitas Windows, Revit 2024 a 2027 con licencia,
Python 3.11 o superior, [uv](https://docs.astral.sh/uv/getting-started/installation/) y el complemento de Revit
([pasos de instalación](#instalar-el-complemento-de-revit)). Después añade esto a tu
`claude_desktop_config.json` (Codex, Cursor y VS Code usan los mismos valores;
las dos variables de directorio son opcionales y por defecto apuntan al espacio de trabajo indicado arriba):

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

¿Quieres ver primero las herramientas, sin Revit? Define `"MCP_REVIT_MODE": "mock"`.
El servidor arranca en cualquier equipo, lista todas las herramientas con su esquema y devuelve
respuestas predefinidas sin tocar ningún modelo. En la raíz del repositorio hay un `Dockerfile` para el mismo
modo mock (`docker build -t aec-model-bridge .` y después
`docker run -i --rm aec-model-bridge`).

¿Usas VS Code? El [código de la extensión y los pasos de instalación local](../../extensions/vscode/README.md)
registran el servidor MCP y muestran el estado de la conexión con Revit. Aún no se ha
publicado en el Marketplace.

### Herramientas de un vistazo

| Área | Herramientas | Qué hacen |
| --- | --- | --- |
| Revit | 110 | Leer el modelo, crear y editar elementos, parámetros, vistas, hojas, tablas de planificación, exportaciones, trabajo compartido |
| Aprobación | 5 | Planificar, revisar, aprobar, ejecutar y revertir cambios en el modelo |
| Módulos | 83 | Inspección de instantáneas, cuadrículas de parámetros, comprobaciones de QA/QC, recetas, informes, selecciones |
| Rhino y Grasshopper | 19 | Geometría, capas, materiales, operaciones booleanas |
| Speckle | 17 | Proyectos, modelos, versiones, envío y recepción |
| Navisworks | 15 | Árbol del modelo, puntos de vista, pruebas de interferencias (en desarrollo) |
| IFC | 7 | Leer archivos IFC sin Revit: estructura, propiedades, validación |
| Grafo, instantáneas, exportaciones, tareas | 21 | Auditorías del grafo semántico, diferencias entre instantáneas, exportación a SQLite, tareas en segundo plano |

En la configuración predeterminada aparecen 277 herramientas (contadas desde el servidor actual en modo
mock). Las herramientas de Autodesk Data aparecen cuando se configuran credenciales de APS. La
[referencia de herramientas](../tools-generated.md) las enumera todas. Cada herramienta incluye
anotaciones MCP (`readOnlyHint`, `destructiveHint`, `idempotentHint`,
`openWorldHint`), de modo que los clientes distinguen las lecturas de las escrituras.

### Automatización avanzada de Revit

Además de las consultas al modelo y las actualizaciones de parámetros, las herramientas de Revit crean elementos de construcción,
vistas, hojas, tablas de planificación, etiquetas y cotas, y exportan archivos IFC, DWG,
imágenes y Navisworks. Consulta la [referencia de herramientas](../tools-generated.md)
para ver las operaciones y entradas admitidas.

Para lo que el catálogo de herramientas no cubre, `revit_invoke_method`, `revit_reflect_get`
y `revit_reflect_set` trabajan con miembros públicos de la API de Revit, y `revit_execute_python`
ejecuta IronPython dentro de Revit. Estas herramientas avanzadas tienen los mismos permisos que
el proceso de Revit. Úsalas solo con clientes MCP y prompts de confianza.

## Cómo funciona

El cliente MCP habla con un único hub de Python. El hub envía cada llamada al
proveedor que posee la herramienta. Los proveedores de aplicaciones de escritorio hablan con un pequeño complemento
dentro de esa aplicación a través de localhost.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../images/architecture-dark.png">
    <img src="../images/architecture-light.png" alt="Architecture of AEC Model Bridge: an MCP client such as Claude or Codex calls the Python MCP hub, which routes tool calls to the Revit, Rhino, Navisworks, IFC and Speckle providers. The Revit and Rhino providers talk to add-ins over localhost HTTP, the IFC provider reads IFC files with IfcOpenShell, and Navisworks is still in progress." width="900">
  </picture>
</p>

<sub>Origen del diagrama: [architecture.mmd](../diagrams/architecture.mmd). Regenera las imágenes con `python scripts/render_diagrams.py`.</sub>

Los recuadros verde azulado funcionan hoy. Los recuadros ámbar con línea discontinua están en desarrollo. Las
formas índigo son datos y servicios externos.

### Cómo funciona la aprobación

El hub bloquea cualquier llamada a una herramienta que modifique el modelo salvo que lleve un
plan aprobado. El modo predeterminado es `required`. La IA propone un plan, tú
lo revisas en el panel lateral de Revit y el complemento lo ejecuta en el hilo principal de Revit
y las acciones de parámetros y de edición del modelo van cada una en su propia transacción con nombre; guardar, sincronizar y los scripts no, así que Ctrl+Z no los cubre.

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

<sub>Origen del diagrama: [approval-flow.mmd](../diagrams/approval-flow.mmd). Regenera las imágenes con `python scripts/render_diagrams.py`.</sub>

Si un plan resulta ser erróneo, deshazlo con Ctrl+Z en Revit. Cada escritura de parámetro
es su propia transacción con nombre, así que un plan puede requerir varias pulsaciones.
Un deshacer en un solo paso para un plan completo está planificado, no construido.
Una segunda vía es un plan de reversión: el asistente lo redacta con `plan_revert` a partir de la prueba de un plan ejecutado, y tú lo apruebas como cualquier otro plan. `rollback_plan` es solo para personas y no es un botón ni un comando, así que no cuentes con él. Ninguna de estas vías está verificada todavía en una sesión real de Revit (UNVERIFIED). Las operaciones que no se pueden revertir, como la escritura de archivos, no se deshacen por ninguna de ellas y todavía no piden una segunda confirmación (planificado). La lista Plans del panel muestra solo los planes pendientes; `aec-model-bridge-approve show <plan_id>` funciona con un plan en cualquier estado, mientras que los paquetes de `proofs/` solo existen para los planes que se ejecutaron (o se intentaron). El ciclo de vida está descrito en
[ADR 0008](../0008-approval-gate-lifecycle.md).

Para pipelines desatendidos puedes definir `MCP_REVIT_APPROVAL_MODE=auto`. Eso desactiva
la revisión humana, así que úsalo solo en un entorno controlado.

## Versiones de Revit compatibles

| Versión de Revit | Destino del complemento | Herramientas de compilación |
|---|---|---|
| 2024 | .NET Framework 4.8 | .NET 8 SDK y .NET Framework 4.8 developer pack |
| 2025 | .NET 8 for Windows | .NET 8 SDK |
| 2026 | .NET 8 for Windows | .NET 8 SDK |
| 2027 | .NET 10 for Windows | .NET 10 SDK |

También necesitas Windows 10 u 11, Python 3.11 o posterior y una instalación de Revit con licencia
para la versión que uses. El modo mock ejecuta el servidor sin Revit,
lo que resulta útil para desarrollo y pruebas.

### Otras integraciones

| Integración | Estado |
|---|---|
| Revit | Disponible. Complemento nativo en C#. |
| IFC (IfcOpenShell) | Disponible. Lee archivos IFC sin necesidad de tener Revit en ejecución. |
| Rhino y Grasshopper | Disponible. Se conecta al complemento de Rhino en `localhost:3004`. |
| Speckle | Disponible. Requiere un ID de cliente de Speckle en tu entorno. |
| Navisworks Manage | En desarrollo. El proveedor y sus herramientas están registrados. El complemento de Navisworks no está terminado. |
| Power BI | En desarrollo. El proveedor y la herramienta existen, pero no están registrados en el hub. |
| Excel, Parquet y DuckDB | Planificado. |

Los nombres de producto y los logotipos pertenecen a sus respectivos propietarios. El banner los usa solo para mostrar con qué trabaja este proyecto.

## Instalar el complemento de Revit

**La forma más sencilla (Windows):** descarga `AECModelBridge-Setup-<version>.exe` de la [última versión](https://github.com/Sam-AEC/aec-model-bridge/releases/latest), haz doble clic, elige tus versiones de Revit y reinicia Revit. Instala el complemento, el servidor de Python incluido y, si marcas la casilla, la configuración de Claude Desktop y VS Code, con una copia de seguridad de tu configuración actual. Se desinstala desde la Configuración de Windows. Los pasos siguientes son para compilar desde el código fuente.

Instalas dos partes: el servidor MCP de Python y el complemento de Revit. La automatización
de Revit en vivo necesita ambas.

### 1. Instalar el servidor MCP

```powershell
git clone https://github.com/Sam-AEC/aec-model-bridge.git
cd aec-model-bridge

py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e packages/mcp-server-revit
```

### 2. Instalar el complemento de Revit

Ajusta la versión para que coincida con tu instalación de Revit. Si Windows bloquea los
scripts descargados, haz clic con el botón derecho en cada archivo `.ps1`, abre Propiedades y selecciona
Desbloquear antes de ejecutarlos.

```powershell
$RevitVersion = Read-Host "Revit year (2024, 2025, 2026, or 2027)"

.\scripts\package.ps1 -RevitVersion $RevitVersion
.\scripts\install.ps1 -RevitVersion $RevitVersion
```

El instalador coloca los binarios específicos de cada versión en:

```text
C:\ProgramData\AECModelBridge\bin\<year>
```

El manifiesto del complemento se instala por usuario en:

```text
%APPDATA%\Autodesk\Revit\Addins\<year>
```

Usa `-AllUsers` con `install.ps1` para instalar el manifiesto en
`C:\ProgramData\Autodesk\Revit\Addins\<year>`.

Para preparar los binarios de todas las versiones compatibles de una sola vez:

```powershell
.\scripts\package.ps1 -RevitVersion All
```

Cada [versión de GitHub](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)
incluye un paquete ya preparado por cada año de Revit, por ejemplo
`aec-model-bridge-revit-2026-<version>.zip`. Descomprímelo y ejecuta
`.\install.ps1 -RevitVersion 2026` en lugar de compilar desde el código fuente. Para un instalador
de Windows de doble clic, `scripts/build-installer.ps1` genera uno con Inno Setup.
La guía completa, con la resolución de problemas, está en [docs/install.md](../install.md).

## Conectar Claude Desktop con Revit

Añade el servidor a la configuración de tu cliente MCP. En Claude Desktop, es
la sección `mcpServers` de `claude_desktop_config.json`. Codex, Cursor, VS
Code y otros clientes MCP usan los mismos valores de `command`, `args` y `env` en
su propio formato de configuración.

Usa el ejecutable de Python de tu entorno virtual y elige una carpeta de espacio de trabajo
a la que el servidor pueda acceder:

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

Omite `MCP_REVIT_HOST_VERSION` para apuntar a la instancia de Revit abierta más reciente.
Defínelo con un año como `2024` o `2026` para fijar una entrada de cliente a esa
versión de Revit. `MCP_REVIT_BRIDGE_URL` sustituye el endpoint en configuraciones avanzadas.

Los usuarios de VS Code pueden partir de [`.vscode/mcp.json`](../../.vscode/mcp.json). Los usuarios de Hermes
Desktop pueden partir de [`docs/examples/hermes-desktop.json`](../examples/hermes-desktop.json) tras sustituir la
ruta de Python de ejemplo. Los clientes compatibles con MCP Bundles pueden instalar el
archivo `.mcpb` de la
[última versión](https://github.com/Sam-AEC/aec-model-bridge/releases/latest).
El complemento de Revit sigue siendo necesario, porque el servidor se comunica con la
aplicación de escritorio en ejecución.

### Comprobar la conexión

Reinicia Revit después de instalar el complemento, abre un modelo y ejecuta:

```powershell
$registry = Get-ChildItem "$env:LOCALAPPDATA\AECModelBridge\registry\revit-*.json" | Select-Object -First 1
$switch = Get-Content $registry.FullName -Raw | ConvertFrom-Json
Invoke-RestMethod "$($switch.endpoint)/health"
```

La respuesta debe indicar `healthy` y la versión de Revit en ejecución. En Revit,
busca la pestaña de la cinta `AEC Bridge`. Su panel Workflows incluye Open Panel,
Health Check, Pending Actions y Reports. Su panel Tools incluye Config, Help
y About.

## Seguridad

- El puente de Revit escucha solo en localhost.
- El servidor lee y escribe únicamente dentro de las carpetas de `MCP_REVIT_ALLOWED_DIRECTORIES`.
- Las herramientas que modifican el modelo necesitan un plan aprobado, salvo que desactives la aprobación.
- Las llamadas a herramientas se registran en un registro de auditoría y los secretos se enmascaran.

Los detalles están en [docs/security.md](../security.md). Para notificar una
vulnerabilidad, sigue [SECURITY.md](../../SECURITY.md).

## Preguntas frecuentes

### ¿Qué es un servidor MCP para Revit?

El Model Context Protocol (MCP) es un estándar abierto que permite a los asistentes de IA
llamar a herramientas de otro software. Un servidor MCP para Revit publica operaciones de Revit
como herramientas. El asistente elige las herramientas y el complemento las ejecuta
dentro de Revit.

### ¿Con qué asistentes de IA funciona?

Con cualquier cliente MCP capaz de iniciar un servidor stdio local. Documentamos Claude
Desktop, VS Code con GitHub Copilot, Cursor y Codex, y los clientes que leen una configuración estándar de
`mcpServers`. Windsurf, Cline, Roo Code, Continue, Zed, Claude Code y Gemini CLI deberían funcionar
de la misma manera, pero no se han probado. Consulta la [compatibilidad](../compatibility.md). El chat del panel también puede usar una clave de API de Anthropic
o las herramientas de línea de comandos `claude` o `codex`, si están instaladas. Consulta
[ADR 0012](../0012-native-agent-chat-backend.md).

### ¿Puede la IA cambiar mi modelo sin preguntar?

No en el modo predeterminado. Las herramientas que modifican el modelo quedan bloqueadas hasta que se aprueba un plan
en el panel de Revit. Las herramientas de solo lectura se ejecutan sin aprobación. Si
defines `MCP_REVIT_APPROVAL_MODE=auto`, se omite la aprobación.

### ¿Envía mi modelo a la nube?

El servidor y el complemento se ejecutan en tu equipo, y el puente escucha en
localhost. Lo que ve el asistente de IA depende del cliente que uses: los resultados
de las herramientas van al proveedor del modelo de ese cliente. Los proveedores conectados a la nube, como
Speckle, solo se ejecutan cuando los configuras y llamas a sus herramientas.

### ¿Funciona con archivos IFC sin Revit?

Sí. El proveedor de IFC lee los archivos con IfcOpenShell. Puede devolver los metadatos
del archivo, la estructura espacial, las propiedades de los elementos y los cuadros delimitadores, ejecutar
consultas por clase, GUID, nombre o propiedad, y validar el esquema. No
edita archivos IFC.

### ¿Puedo usarlo sin tener Revit instalado?

Puedes ejecutar el servidor en modo mock para desarrollo y pruebas. El trabajo en vivo con el modelo
necesita Revit 2024 a 2027 y el complemento.

## Versiones y publicaciones

AEC Model Bridge sigue el versionado semántico. Las versiones se etiquetan como `vX.Y.Z` en
GitHub y un archivo `VERSION` en la raíz contiene el número de versión. Consulta
[docs/versioning.md](../versioning.md) para el proceso de publicación y
[CHANGELOG.md](../../CHANGELOG.md) para los cambios de cada versión.

## Desarrollo

```powershell
# Python tests
python -m pytest packages/mcp-server-revit/tests

# Build one Revit version, for example 2026
.\scripts\build-addin.ps1 -RevitVersion 2026 -Configuration Release

# Build all supported versions
.\scripts\package.ps1 -RevitVersion All
```

La CI compila el servidor de Python y los destinos del complemento para Revit 2024 a 2027.
Consulta [CONTRIBUTING.md](../../CONTRIBUTING.md) antes de abrir un pull request.

## Documentación

- [Guía de instalación](../install.md)
- [Referencia de herramientas](../tools-generated.md)
- [Arquitectura](../0001-multi-provider-architecture.md)
- [Referencia de configuración](../configuration-reference.md)
- [Seguridad](../security.md)
- [Clientes MCP y registro](../marketplaces.md)
- [Versionado y publicaciones](../versioning.md)
- [Toda la documentación](../README.md)
- [Guía de contribución](../../CONTRIBUTING.md) y [Código de conducta](../../CODE_OF_CONDUCT.md)
- [Colaboradores](../../CONTRIBUTORS.md)

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

## Proyecto y licencia

Mantenido por [A. Sam Mohammad](https://github.com/Sam-AEC).
[LinkedIn](https://www.linkedin.com/in/a-sam-mohammad-92790416b) |
[Issues](https://github.com/Sam-AEC/aec-model-bridge/issues)

[GPL-3.0-or-later con la Revit Linking Exception, o una licencia comercial](../../LICENSING.md).
