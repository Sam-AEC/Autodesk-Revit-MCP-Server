<div align="center">

<img src="../../assets/logo.svg" alt="AEC Model Bridge logo: an isometric model cube with a bridge arch" height="120">

[English](../../README.md) | [简体中文](README.zh-CN.md) | [Español](README.es.md) | [हिन्दी](README.hi.md) | [العربية](README.ar.md) | **Português (BR)** | [Русский](README.ru.md) | [日本語](README.ja.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Bahasa Indonesia](README.id.md) | [Türkçe](README.tr.md) | [한국어](README.ko.md) | [Tiếng Việt](README.vi.md) | [Italiano](README.it.md) | [Polski](README.pl.md) | [繁體中文](README.zh-TW.md)

> Esta tradução foi feita com apoio de IA. O [README](../../README.md) em inglês é a fonte de referência; correções são bem-vindas por pull request (veja [CONTRIBUTING.md](../../CONTRIBUTING.md)).

**Pergunte à sua IA sobre o modelo do Revit que você tem aberto. Por padrão, as ferramentas de escrita ficam bloqueadas até você aprovar um plano.**

Servidor MCP de código aberto e add-in nativo para Revit 2024 – 2027. Funciona com Claude, Codex e outros clientes MCP.

[![CI](https://img.shields.io/github/actions/workflow/status/Sam-AEC/aec-model-bridge/ci.yml?branch=main&style=flat-square&label=CI)](https://github.com/Sam-AEC/aec-model-bridge/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Sam-AEC/aec-model-bridge?style=flat-square&color=0F766E)](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)
[![Revit](https://img.shields.io/badge/Revit-2024--2027-0696D7?style=flat-square)](#versões-do-revit-compatíveis)
[![License](https://img.shields.io/badge/license-GPL--3.0%20%2B%20commercial-2563EB?style=flat-square)](../../LICENSING.md)

[Primeiros passos](#início-rápido) | [Exemplos de fluxos de trabalho](#exemplos-de-fluxos-de-trabalho) | [Ferramentas](../tools-generated.md) | [Documentação](#documentação) | [Baixar](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)

</div>

<p align="center">
  <img src="../images/readme/revit-villa-panel.png" alt="Modelo de uma casa no Revit ao lado do painel AEC Model Bridge com o modo Dev ativado." width="900">
</p>

O AEC Model Bridge é o servidor MCP de código aberto para Revit que permite ao Claude, ao Codex, ao Cursor e a outros assistentes de IA ler e editar o modelo do Revit que você tem aberto, com cada alteração aprovada antes por você. Ele combina um servidor MCP em Python com um add-in nativo do Revit: as ferramentas somente leitura inspecionam o modelo na hora e, por padrão, qualquer alteração no modelo exige um plano aprovado. [Veja o fluxo de aprovação](#como-funciona-a-aprovação).

<p align="center">
  <img src="../images/readme/works-with.svg" alt="Funciona com: Claude Desktop, VS Code com GitHub Copilot, Cursor e Codex têm configuração documentada. Outros clientes MCP, como Claude Code, Windsurf, Cline, Continue, Zed e Gemini CLI, também devem funcionar. Aplicativos: Revit 2024 a 2027, Rhino, Grasshopper, Navisworks (em desenvolvimento). Dados: IFC, Speckle, Excel, SQLite. Protocolo: MCP sobre stdio com uma barreira de aprovação." width="900">
</p>

A configuração está documentada para Claude Desktop, VS Code com GitHub Copilot, Cursor e Codex. É um servidor MCP stdio padrão, então outros clientes, como Claude Code, Windsurf, Cline, Continue, Zed e Gemini CLI, também devem funcionar. Veja a [compatibilidade](../compatibility.md) para saber o que está documentado e o que não foi testado.

O mesmo servidor inclui inspeção de IFC, automação do Rhino e do Grasshopper e integração com o Speckle. O [status das integrações](#outras-integrações) separa os provedores disponíveis dos que ainda estão em desenvolvimento.

## Exemplos de fluxos de trabalho

Para coordenadores BIM: inspecionar a qualidade do modelo, revisar os elementos afetados, aprovar uma correção de parâmetros, conferir os resultados e exportar um relatório. Estes exemplos usam ferramentas do [catálogo atual](../tools-generated.md).

| Fluxo de trabalho | Pedido de exemplo | Ferramentas usadas |
| --- | --- | --- |
| Revisão do modelo | "Mostre o documento ativo, liste os avisos e encontre os elementos afetados." | `revit_get_document_info`, `revit_get_warnings`, `revit_get_elements_by_type` |
| Atualização de parâmetros | "Encontre as paredes do Level 02, mostre os valores de Comments e proponha uma atualização em lote." | `revit_get_elements_by_type`, `revit_get_element_parameters`, `revit_batch_set_parameters` |
| Produção de desenhos | "Prepare uma lista de folhas a partir deste CSV e proponha criar as folhas e posicionar as vistas." | `revit_batch_create_sheets_from_csv`, `revit_place_viewport_on_sheet` |
| Revisão de IFC | "Mostre os pavimentos deste arquivo IFC, inspecione as propriedades das paredes e informe os problemas de validação do esquema." | `ifc_get_spatial_structure`, `ifc_get_properties`, `ifc_validate` |

Para um primeiro teste no Revit, experimente:

```text
Read the active model's warnings. Group them by description and show the
affected element IDs. Then suggest which issues to investigate first.
```

Depois experimente uma correção de parâmetro, trocando o nível e o valor pelos do seu projeto:

```text
Find walls on Level 02 and show their current Comments values. Propose setting
Comments to "Coordination reviewed" for the elements I choose. After I approve
the plan in Revit, apply it and read the values back to confirm the result.
```

Para alterações no modelo, o assistente cria um plano com `plan_actions`; você o revisa no painel do Revit antes de o `execute_plan` aplicá-lo. A revisão de IFC funciona sem o Revit.

Os módulos de QA/QC e de relatórios baseados em snapshot exigem um snapshot salvo compatível. A passagem atual do snapshot do Revit para o módulo exige alinhamento entre o nome do arquivo e o workspace; se você omitir `snapshot_id`, podem ser retornados dados de exemplo gerados. Para inspeção em tempo real, use as ferramentas diretas do Revit acima. [Correções planejadas e demo](../roadmap.md).

## Início rápido

**Instalação com um clique**

[![Install in VS Code](https://img.shields.io/badge/Install_in-VS_Code-0098FF?style=for-the-badge)](../install-buttons.md#vs-code)
[![Install in Cursor](https://img.shields.io/badge/Install_in-Cursor-111111?style=for-the-badge)](https://cursor.com/en/install-mcp?name=aec-model-bridge&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyItLWZyb20iLCJnaXQraHR0cHM6Ly9naXRodWIuY29tL1NhbS1BRUMvYWVjLW1vZGVsLWJyaWRnZSNzdWJkaXJlY3Rvcnk9cGFja2FnZXMvbWNwLXNlcnZlci1yZXZpdCIsImFlYy1tb2RlbC1icmlkZ2UiXSwiZW52Ijp7Ik1DUF9SRVZJVF9NT0RFIjoiYnJpZGdlIn19)
[![Claude Desktop bundle](https://img.shields.io/badge/Claude_Desktop-.mcpb_bundle-D97757?style=for-the-badge)](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)

Os botões só precisam do [uv](https://docs.astral.sh/uv/getting-started/installation/) e de nenhuma outra configuração: o servidor usa `~/Documents/AEC Model Bridge` como workspace, a menos que você defina o seu. Para o Claude Desktop, baixe o arquivo `.mcpb` da última versão e abra-o. O trabalho com o Revit em execução ainda exige o Revit e [o add-in](#instalar-o-add-in-do-revit); o modo mock não exige nada.

**Configuração manual**

Para a automação do Revit em tempo real você precisa de Windows, Revit 2024 a 2027 licenciado, Python 3.11 ou superior, [uv](https://docs.astral.sh/uv/getting-started/installation/) e o add-in do Revit ([passos de instalação](#instalar-o-add-in-do-revit)). Depois adicione isto ao seu `claude_desktop_config.json` (Codex, Cursor e VS Code usam os mesmos valores; as duas variáveis de diretório são opcionais e, por padrão, apontam para o workspace acima):

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

Quer ver as ferramentas primeiro, sem o Revit? Defina `"MCP_REVIT_MODE": "mock"`. O servidor então inicia em qualquer lugar, lista todas as ferramentas com seus esquemas e devolve respostas prontas, sem tocar em nenhum modelo. Há um `Dockerfile` para o mesmo modo mock na raiz do repositório (`docker build -t aec-model-bridge .` e depois `docker run -i --rm aec-model-bridge`).

Usa o VS Code? O [código da extensão e os passos de instalação local](../../extensions/vscode/README.md) registram o servidor MCP e mostram o status da conexão com o Revit. Ela ainda não foi publicada no Marketplace.

### Ferramentas em resumo

| Área | Ferramentas | O que fazem |
| --- | --- | --- |
| Revit | 103 | Ler o modelo, criar e editar elementos, parâmetros, vistas, folhas, tabelas de quantitativos, exportações, trabalho compartilhado |
| Aprovação | 6 | Planejar, revisar, aprovar, executar e reverter alterações no modelo |
| Módulos | 34 | Inspeção de snapshots, grades de parâmetros, verificações de QA/QC, receitas, relatórios, seleções |
| Rhino e Grasshopper | 19 | Geometria, camadas, materiais, operações booleanas |
| Speckle | 17 | Projetos, modelos, versões, envio e recebimento |
| Navisworks | 15 | Árvore do modelo, pontos de vista, testes de interferência (em desenvolvimento) |
| IFC | 7 | Ler arquivos IFC sem o Revit: estrutura, propriedades, validação |
| Grafo, snapshots, exportações, tarefas | 18 | Auditorias do grafo semântico, diferenças entre snapshots, exportação para SQLite, tarefas em segundo plano |

219 ferramentas são listadas na configuração padrão (contadas no servidor atual em modo mock). As ferramentas do Autodesk Data aparecem quando as credenciais do APS estão configuradas. A [referência de ferramentas](../tools-generated.md) lista todas elas. Cada ferramenta traz anotações MCP (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`), para que os clientes distingam leituras de escritas.

### Automação avançada do Revit

Além de consultas ao modelo e atualizações de parâmetros, as ferramentas do Revit criam elementos de construção, vistas, folhas, tabelas, tags e cotas, e exportam arquivos IFC, DWG, imagens e Navisworks. Veja a [referência de ferramentas](../tools-generated.md) para as operações e entradas compatíveis.

Para o que o catálogo de ferramentas não cobre, `revit_invoke_method`, `revit_reflect_get` e `revit_reflect_set` trabalham com membros públicos da API do Revit, e `revit_execute_python` executa IronPython dentro do Revit. Essas ferramentas avançadas têm as mesmas permissões do processo do Revit. Use-as somente com clientes MCP e prompts em que você confia.

## Como funciona

O cliente MCP conversa com um único hub Python. O hub envia cada chamada ao provedor dono da ferramenta. Os provedores de aplicativos de desktop conversam, via localhost, com um pequeno add-in dentro desse aplicativo.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../images/architecture-dark.png">
    <img src="../images/architecture-light.png" alt="Architecture of AEC Model Bridge: an MCP client such as Claude or Codex calls the Python MCP hub, which routes tool calls to the Revit, Rhino, Navisworks, IFC and Speckle providers. The Revit and Rhino providers talk to add-ins over localhost HTTP, the IFC provider reads IFC files with IfcOpenShell, and Navisworks is still in progress." width="900">
  </picture>
</p>

<sub>Fonte do diagrama: [architecture.mmd](../diagrams/architecture.mmd). Gere as imagens novamente com `python scripts/render_diagrams.py`.</sub>

As caixas verde-azuladas já funcionam. As caixas âmbar tracejadas estão em desenvolvimento. As formas índigo são dados e serviços externos.

### Como funciona a aprovação

O hub bloqueia qualquer chamada de ferramenta que altere o modelo, a menos que ela traga um plano aprovado. O modo padrão é `required`. A IA propõe um plano, você o revisa no painel lateral do Revit e o add-in o executa na thread principal do Revit, as ações de parâmetro e de edição do modelo, cada uma em sua própria transação nomeada; salvar, sincronizar e scripts não, então o Ctrl+Z não os cobre.

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

<sub>Fonte do diagrama: [approval-flow.mmd](../diagrams/approval-flow.mmd). Gere as imagens novamente com `python scripts/render_diagrams.py`.</sub>

Se um plano se mostrar errado, desfaça com Ctrl+Z no Revit. Cada gravação de parâmetro é uma transação nomeada própria, então um plano pode exigir vários toques. Um desfazer em uma única etapa para um plano inteiro está planejado, não construído. Um segundo caminho é um plano de reversão: o assistente redige um com `plan_revert` a partir da prova de um plano executado, e você o aprova como qualquer outro plano. `rollback_plan` é apenas para pessoas e não é um botão nem um comando, então não conte com ele. Nenhum desses caminhos foi verificado ainda em uma sessão real do Revit (UNVERIFIED). Operações que não podem ser revertidas, como a gravação de arquivos, não são desfeitas por nenhum deles e ainda não pedem uma segunda confirmação (planejado). A lista Plans do painel mostra apenas planos pendentes; `aec-model-bridge-approve show <plan_id>` funciona para um plano em qualquer estado, enquanto os pacotes de `proofs/` existem apenas para planos que foram executados (ou tentados). O ciclo de vida está no [ADR 0008](../0008-approval-gate-lifecycle.md).

Para pipelines sem supervisão, você pode definir `MCP_REVIT_APPROVAL_MODE=auto`. Isso desliga a verificação feita por uma pessoa, então use apenas em um ambiente controlado.

## Versões do Revit compatíveis

| Versão do Revit | Alvo do add-in | Ferramentas de build |
|---|---|---|
| 2024 | .NET Framework 4.8 | .NET 8 SDK e .NET Framework 4.8 developer pack |
| 2025 | .NET 8 for Windows | .NET 8 SDK |
| 2026 | .NET 8 for Windows | .NET 8 SDK |
| 2027 | .NET 10 for Windows | .NET 10 SDK |

Você também precisa de Windows 10 ou 11, Python 3.11 ou superior e uma instalação licenciada do Revit na versão que usa. O modo mock executa o servidor sem o Revit, o que é útil para desenvolvimento e testes.

### Outras integrações

| Integração | Status |
|---|---|
| Revit | Disponível. Add-in nativo em C#. |
| IFC (IfcOpenShell) | Disponível. Lê arquivos IFC sem o Revit em execução. |
| Rhino e Grasshopper | Disponível. Conecta-se ao add-in do Rhino em `localhost:3004`. |
| Speckle | Disponível. Precisa de um client ID do Speckle no seu ambiente. |
| Navisworks Manage | Em desenvolvimento. O provedor e suas ferramentas estão registrados. O add-in do Navisworks não está concluído. |
| Power BI | Em desenvolvimento. O provedor e a ferramenta existem, mas não estão registrados no hub. |
| Excel, Parquet e DuckDB | Planejado. |

Os nomes de produtos e os logotipos pertencem aos seus respectivos donos. O banner os usa apenas para mostrar com o que este projeto funciona.

## Instalar o add-in do Revit

**O jeito mais fácil (Windows):** baixe `AECModelBridge-Setup-<version>.exe` da [última versão](https://github.com/Sam-AEC/aec-model-bridge/releases/latest), dê um clique duplo, escolha suas versões do Revit e reinicie o Revit. Ele instala o add-in, o servidor Python incluído e, se você marcar a opção, as configurações do Claude Desktop e do VS Code, com backup das configurações atuais. Desinstale pelas Configurações do Windows. Os passos abaixo são para compilar a partir do código-fonte.

Você instala duas partes: o servidor MCP em Python e o add-in do Revit. A automação do Revit em tempo real precisa das duas.

### 1. Instalar o servidor MCP

```powershell
git clone https://github.com/Sam-AEC/aec-model-bridge.git
cd aec-model-bridge

py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e packages/mcp-server-revit
```

### 2. Instalar o add-in do Revit

Defina a versão de acordo com a sua instalação do Revit. Se o Windows bloquear os scripts baixados, clique com o botão direito em cada arquivo `.ps1`, abra Propriedades e selecione Desbloquear antes de executá-los.

```powershell
$RevitVersion = Read-Host "Revit year (2024, 2025, 2026, or 2027)"

.\scripts\package.ps1 -RevitVersion $RevitVersion
.\scripts\install.ps1 -RevitVersion $RevitVersion
```

O instalador coloca os binários específicos de cada versão em:

```text
C:\ProgramData\AECModelBridge\bin\<year>
```

O manifesto do add-in é instalado por usuário em:

```text
%APPDATA%\Autodesk\Revit\Addins\<year>
```

Use `-AllUsers` com `install.ps1` para instalar o manifesto em `C:\ProgramData\Autodesk\Revit\Addins\<year>`.

Para preparar os binários de todas as versões compatíveis de uma só vez:

```powershell
.\scripts\package.ps1 -RevitVersion All
```

Cada [versão no GitHub](https://github.com/Sam-AEC/aec-model-bridge/releases/latest) traz um pacote pronto para cada ano do Revit, por exemplo `aec-model-bridge-revit-2026-<version>.zip`. Descompacte-o e execute `.\install.ps1 -RevitVersion 2026` em vez de compilar a partir do código-fonte. Para um instalador do Windows de clique duplo, `scripts/build-installer.ps1` gera um com o Inno Setup. O guia completo, com solução de problemas, está em [docs/install.md](../install.md).

## Conectar o Claude Desktop ao Revit

Adicione o servidor à configuração do seu cliente MCP. No Claude Desktop, é a seção `mcpServers` do `claude_desktop_config.json`. Codex, Cursor, VS Code e outros clientes MCP usam os mesmos valores de `command`, `args` e `env` no formato de configuração de cada um.

Use o executável do Python do seu ambiente virtual e escolha uma pasta de workspace que o servidor possa acessar:

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

Omita `MCP_REVIT_HOST_VERSION` para usar a instância aberta mais recente do Revit. Defina-o com um ano, como `2024` ou `2026`, para fixar uma entrada de cliente nessa versão do Revit. `MCP_REVIT_BRIDGE_URL` substitui o endpoint em configurações avançadas.

Usuários do VS Code podem começar por [`.vscode/mcp.json`](../../.vscode/mcp.json). Usuários do Hermes Desktop podem começar por [`docs/examples/hermes-desktop.json`](../examples/hermes-desktop.json), depois de trocar o caminho de exemplo do Python. Clientes com suporte a MCP Bundles podem instalar o arquivo `.mcpb` da [última versão](https://github.com/Sam-AEC/aec-model-bridge/releases/latest). O add-in do Revit continua sendo necessário, porque o servidor conversa com o aplicativo de desktop em execução.

### Verificar a conexão

Reinicie o Revit depois de instalar o add-in, abra um modelo e execute:

```powershell
$registry = Get-ChildItem "$env:LOCALAPPDATA\AECModelBridge\registry\revit-*.json" | Select-Object -First 1
$switch = Get-Content $registry.FullName -Raw | ConvertFrom-Json
Invoke-RestMethod "$($switch.endpoint)/health"
```

A resposta deve indicar `healthy` e a versão do Revit em execução. No Revit, procure a guia da faixa de opções `AEC Bridge`. O painel Workflows tem Open Panel, Health Check, Pending Actions e Reports. O painel Tools tem Config, Help e About.

## Segurança

- A ponte do Revit só é acessível por localhost.
- O servidor lê e grava somente dentro das pastas listadas em `MCP_REVIT_ALLOWED_DIRECTORIES`.
- Ferramentas que alteram o modelo exigem um plano aprovado, a menos que você desative a aprovação.
- As chamadas de ferramentas são gravadas em um log de auditoria, e os segredos são mascarados.

Os detalhes estão em [docs/security.md](../security.md). Para relatar uma vulnerabilidade, siga [SECURITY.md](../../SECURITY.md).

## Perguntas frequentes

### O que é um servidor MCP para Revit?

O Model Context Protocol (MCP) é um padrão aberto que permite a assistentes de IA chamar ferramentas de outros programas. Um servidor MCP para Revit publica operações do Revit como ferramentas. O assistente escolhe as ferramentas e o add-in as executa dentro do Revit.

### Quais assistentes de IA funcionam com ele?

Qualquer cliente MCP capaz de iniciar um servidor stdio local. Documentamos o Claude Desktop, o VS Code com GitHub Copilot, o Cursor e o Codex, além de clientes que leem uma configuração `mcpServers` padrão. Windsurf, Cline, Roo Code, Continue, Zed, Claude Code e Gemini CLI devem funcionar da mesma forma, mas não foram testados. Veja a [compatibilidade](../compatibility.md). O chat do painel também pode usar uma chave de API da Anthropic ou as ferramentas de linha de comando `claude` ou `codex`, se estiverem instaladas. Veja o [ADR 0012](../0012-native-agent-chat-backend.md).

### A IA pode alterar meu modelo sem pedir?

Não no modo padrão. As ferramentas que alteram o modelo ficam bloqueadas até que um plano seja aprovado no painel do Revit. As ferramentas somente leitura rodam sem aprovação. Se você definir `MCP_REVIT_APPROVAL_MODE=auto`, a aprovação é ignorada.

### Ele envia meu modelo para a nuvem?

O servidor e o add-in rodam na sua máquina, e a ponte só é acessível por localhost. O que o assistente de IA enxerga depende do cliente que você usa: os resultados das ferramentas vão para o provedor de modelo desse cliente. Provedores voltados à nuvem, como o Speckle, só rodam quando você os configura e chama as ferramentas deles.

### Funciona com arquivos IFC sem o Revit?

Sim. O provedor de IFC lê arquivos com o IfcOpenShell. Ele pode retornar metadados do arquivo, a estrutura espacial, propriedades de elementos e caixas delimitadoras, executar consultas por classe, GUID, nome ou propriedade e validar o esquema. Ele não edita arquivos IFC.

### Posso usar sem o Revit instalado?

Você pode executar o servidor em modo mock para desenvolvimento e testes. O trabalho em tempo real com o modelo exige o Revit 2024 a 2027 e o add-in.

## Versões e lançamentos

O AEC Model Bridge segue o Versionamento Semântico. As versões recebem a tag `vX.Y.Z` no GitHub, e um arquivo `VERSION` na raiz guarda o número da versão. Veja [docs/versioning.md](../versioning.md) para o processo de lançamento e [CHANGELOG.md](../../CHANGELOG.md) para o que mudou em cada versão.

## Desenvolvimento

```powershell
# Python tests
python -m pytest packages/mcp-server-revit/tests

# Build one Revit version, for example 2026
.\scripts\build-addin.ps1 -RevitVersion 2026 -Configuration Release

# Build all supported versions
.\scripts\package.ps1 -RevitVersion All
```

A CI compila o servidor Python e os alvos do add-in para o Revit 2024 a 2027. Leia [CONTRIBUTING.md](../../CONTRIBUTING.md) antes de abrir um pull request.

## Documentação

- [Guia de instalação](../install.md)
- [Referência de ferramentas](../tools-generated.md)
- [Arquitetura](../0001-multi-provider-architecture.md)
- [Referência de configuração](../configuration-reference.md)
- [Segurança](../security.md)
- [Clientes MCP e registro](../marketplaces.md)
- [Versionamento e lançamentos](../versioning.md)
- [Toda a documentação](../README.md)
- [Como contribuir](../../CONTRIBUTING.md) e [Código de Conduta](../../CODE_OF_CONDUCT.md)
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

## Projeto e licença

Mantido por [A. Sam Mohammad](https://github.com/Sam-AEC).
[LinkedIn](https://www.linkedin.com/in/a-sam-mohammad-92790416b) |
[Issues](https://github.com/Sam-AEC/aec-model-bridge/issues)

[GPL-3.0-or-later com a Revit Linking Exception, ou uma licença comercial](../../LICENSING.md).
