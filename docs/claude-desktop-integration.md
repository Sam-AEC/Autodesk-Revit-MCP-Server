# Claude Desktop Integration Guide

This guide shows you how to use the RevitMCP server with Claude Desktop (formerly Claude Code).

## Prerequisites

- **Claude Desktop** installed (download from https://claude.ai/download)
- **Revit 2024 or 2025** installed
- **RevitMCP Bridge** installed and running in Revit

## Architecture

```
┌─────────────────────────┐
│   Claude Desktop App    │
│   (AI Assistant)        │
└────────────┬────────────┘
             │ MCP Protocol
             │
┌────────────▼────────────┐
│  RevitMCP Server        │
│  (Python)               │
└────────────┬────────────┘
             │ HTTP localhost:3000
┌────────────▼────────────┐
│  RevitBridge Add-in     │
│  (C# in Revit)          │
└────────────┬────────────┘
             │ Revit API
┌────────────▼────────────┐
│  Autodesk Revit         │
│  (2024/2025)            │
└─────────────────────────┘
```

## Step 1: Install RevitMCP

### Option A: From Release Package

1. Download the latest release from [Releases](https://github.com/Sam-AEC/Autodesk-Revit-MCP-Server/releases)
2. Extract the ZIP file
3. Run the installer:
   ```powershell
   .\install.ps1 -RevitVersion 2024
   ```

### Option B: From Source

```powershell
git clone https://github.com/Sam-AEC/Autodesk-Revit-MCP-Server.git
cd Autodesk-Revit-MCP-Server
.\scripts\build-addin.ps1 -RevitVersion 2024
.\scripts\install.ps1 -RevitVersion 2024
```

## Step 2: Start Revit

1. Launch **Autodesk Revit 2024** (or 2025)
2. The RevitMCP Bridge will start automatically
3. Verify it's running:
   ```powershell
   curl http://localhost:3000/health
   ```

   Expected output:
   ```json
   {
     "status": "healthy",
     "version": "1.0.0",
     "uptime_seconds": 5.2,
     "revit_version": "2024",
     "active_document": "YourProject.rvt"
   }
   ```

## Step 3: Configure Claude Desktop

### Locate the Configuration File

The Claude Desktop configuration file is located at:

**Windows:**
```
%APPDATA%\Claude\claude_desktop_config.json
```

**macOS:**
```
~/Library/Application Support/Claude/claude_desktop_config.json
```

**Linux:**
```
~/.config/Claude/claude_desktop_config.json
```

### Add RevitMCP Server

Edit `claude_desktop_config.json` and add the MCP server configuration:

```json
{
  "mcpServers": {
    "revit": {
      "command": "python",
      "args": [
        "-m",
        "revit_mcp_server"
      ],
      "env": {
        "BRIDGE_URL": "http://localhost:3000"
      }
    }
  }
}
```

### Alternative: Using uvx (Recommended)

If you have `uvx` installed, you can use this simpler configuration:

```json
{
  "mcpServers": {
    "revit": {
      "command": "uvx",
      "args": [
        "revit-mcp-server"
      ],
      "env": {
        "BRIDGE_URL": "http://localhost:3000"
      }
}
    }
  }
```

## Step 4: Install Python Package

Open a terminal and install the RevitMCP server package:

```powershell
# From PyPI (when published)
pip install revit-mcp-server

# Or from source
cd path/to/Autodesk-Revit-MCP-Server
pip install -e packages/mcp-server-revit
```

## Step 5: Restart Claude Desktop

1. Close Claude Desktop completely (check system tray)
2. Reopen Claude Desktop
3. The MCP server will automatically connect

## Step 6: Test the Integration

In Claude Desktop, try these prompts:

### Check Connection
```
Can you check if Revit is running and what version it is?
```

Claude should call `revit.health` and tell you the Revit version.

### List Views
```
What views are available in my current Revit project?
```

Claude should call `revit.list_views` and show you all views.

### Create a Wall
```
Create a wall in my Revit model starting at (0,0,0) and ending at (10,0,0) with a height of 10 feet on Level 1
```

Claude should call `revit.create_wall` with the appropriate parameters.

## Available Tools (50 Total)

### Document Management (5 tools)
- `revit.health` - Check Revit status
- `revit.open_document` - Open Revit file
- `revit.save_document` - Save current document
- `revit.close_document` - Close document
- `revit.list_levels` - List all levels

### Geometry Creation (8 tools)
- `revit.create_wall` - Create walls
- `revit.create_floor` - Create floors
- `revit.create_roof` - Create roofs
- `revit.create_level` - Create levels
- `revit.create_grid` - Create grids
- `revit.create_room` - Create rooms
- `revit.list_elements_by_category` - Query elements
- `revit.delete_element` - Delete elements

### Component Placement (4 tools)
- `revit.place_family_instance` - Place family instances
- `revit.place_door` - Place doors
- `revit.place_window` - Place windows
- `revit.list_families` - List loaded families

### View Creation (3 tools)
- `revit.create_floor_plan_view` - Create floor plans
- `revit.create_3d_view` - Create 3D views
- `revit.create_section_view` - Create section views

### Parameters & Properties (10 tools)
- `revit.get_element_parameters` - Get all element parameters
- `revit.set_parameter_value` - Set parameter value
- `revit.get_parameter_value` - Get specific parameter
- `revit.list_shared_parameters` - List shared parameters
- `revit.list_project_parameters` - List project parameters
- `revit.batch_set_parameters` - Bulk parameter updates
- `revit.get_type_parameters` - Get type parameters
- `revit.set_type_parameter` - Set type parameter

### Sheets & Documentation (10 tools)
- `revit.list_sheets` - List all sheets
- `revit.create_sheet` - Create new sheet
- `revit.delete_sheet` - Delete sheet
- `revit.place_viewport_on_sheet` - Place view on sheet
- `revit.batch_create_sheets_from_csv` - Bulk sheet creation
- `revit.populate_titleblock` - Update titleblock parameters
- `revit.list_titleblocks` - List available titleblocks
- `revit.get_sheet_info` - Get detailed sheet info
- `revit.duplicate_sheet` - Duplicate existing sheet
- `revit.renumber_sheets` - Batch renumber sheets

### Advanced Exports (5 tools)
- `revit.export_dwg_by_view` - Export to DWG
- `revit.export_ifc_with_settings` - Export IFC
- `revit.export_navisworks` - Export to Navisworks
- `revit.export_image` - Export view as image
- `revit.render_3d_view` - Render 3D view

### Legacy Export Tools (5 tools)
- `revit.list_views` - List all views
- `revit.export_schedules` - Export schedules to CSV
- `revit.export_pdf_by_sheet_set` - Export PDFs

## Example Conversations

### Example 1: Create a Simple Room

**You:** Create a simple office room for me. Make it 15 feet by 12 feet with walls that are 10 feet high. Place a door and a window.

**Claude will:**
1. Call `revit.list_levels` to find Level 1
2. Call `revit.create_wall` four times to create walls
3. Call `revit.place_door` to add a door
4. Call `revit.place_window` to add a window
5. Report back with element IDs and confirmation

### Example 2: Generate Sheet Set

**You:** Create a sheet set for my project with sheets A101, A102, and A103 using the standard titleblock. Place floor plan views on each sheet.

**Claude will:**
1. Call `revit.list_titleblocks` to find available titleblocks
2. Call `revit.batch_create_sheets_from_csv` to create the sheets
3. Call `revit.list_views` to find floor plan views
4. Call `revit.place_viewport_on_sheet` for each view
5. Provide a summary of created sheets

### Example 3: Quality Assurance Report

**You:** Run a quality check on my model and tell me if there are any issues with naming standards or missing parameters.

**Claude will:**
1. Call `revit.list_elements_by_category` for key categories
2. Call `revit.get_element_parameters` to check completeness
3. Analyze naming patterns
4. Generate a report with recommendations

## Troubleshooting

### Server Not Connecting

**Symptom:** Claude says it can't connect to Revit

**Solutions:**
1. Verify Revit is running: Check Windows Task Manager
2. Check bridge health: `curl http://localhost:3000/health`
3. Check Claude Desktop logs:
   - Windows: `%APPDATA%\Claude\logs\`
   - macOS: `~/Library/Logs/Claude/`
4. Restart both Revit and Claude Desktop

### Tools Not Appearing

**Symptom:** Claude doesn't seem to know about Revit tools

**Solutions:**
1. Verify configuration file path is correct
2. Check JSON syntax in `claude_desktop_config.json`
3. Restart Claude Desktop
4. Check MCP server is installed: `pip show revit-mcp-server`

### Execution Errors

**Symptom:** Tools execute but return errors

**Solutions:**
1. Check Revit logs: `%APPDATA%\RevitMCP\Logs\bridge.jsonl`
2. Verify document is open in Revit
3. Check element IDs are valid
4. Ensure parameters exist before setting them

### Performance Issues

**Symptom:** Commands are slow or timeout

**Solutions:**
1. Large models may be slow - this is normal
2. Increase timeout in bridge configuration
3. Use batch operations instead of individual calls
4. Close unnecessary views in Revit

## Advanced Configuration

### Custom Bridge URL

If you're running the bridge on a different port:

```json
{
  "mcpServers": {
    "revit": {
      "command": "python",
      "args": ["-m", "revit_mcp_server"],
      "env": {
        "BRIDGE_URL": "http://localhost:5000"
      }
    }
  }
}
```

### Multiple Revit Instances

To connect to different Revit instances, configure multiple servers:

```json
{
  "mcpServers": {
    "revit-main": {
      "command": "python",
      "args": ["-m", "revit_mcp_server"],
      "env": {
        "BRIDGE_URL": "http://localhost:3000"
      }
    },
    "revit-secondary": {
      "command": "python",
      "args": ["-m", "revit_mcp_server"],
      "env": {
        "BRIDGE_URL": "http://localhost:3001"
      }
    }
  }
}
```

### Debug Mode

Enable detailed logging:

```json
{
  "mcpServers": {
    "revit": {
      "command": "python",
      "args": ["-m", "revit_mcp_server"],
      "env": {
        "BRIDGE_URL": "http://localhost:3000",
        "LOG_LEVEL": "DEBUG"
      }
    }
  }
}
```

## Security Considerations

### Localhost Only

By default, the bridge **only** accepts connections from localhost (`127.0.0.1`). This is secure for single-machine use with Claude Desktop.

### Network Access (Not Recommended for Claude Desktop)

If you need remote access (e.g., for Copilot Studio), see [docs/security.md](security.md) for hardening steps including:
- HTTPS reverse proxy
- OAuth2 authentication
- Rate limiting
- Audit logging

**For Claude Desktop use, localhost-only is sufficient and recommended.**

## Next Steps

1. **Explore Capabilities:** Try different prompts to see what Claude can do with Revit
2. **Read API Docs:** See [docs/api.md](api.md) for detailed tool specifications
3. **Build Workflows:** Create repeatable automation workflows
4. **Customize:** Extend the server with custom tools for your needs

## Getting Help

- **Documentation:** [GitHub Wiki](https://github.com/Sam-AEC/Autodesk-Revit-MCP-Server/wiki)
- **Issues:** [GitHub Issues](https://github.com/Sam-AEC/Autodesk-Revit-MCP-Server/issues)
- **Discussions:** [GitHub Discussions](https://github.com/Sam-AEC/Autodesk-Revit-MCP-Server/discussions)

---

**Last Updated:** 2026-01-07
