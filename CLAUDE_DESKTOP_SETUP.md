# Claude Desktop Integration Guide

Control Revit with natural language through Claude Desktop!

## What This Does

This integration allows you to use **natural language** in Claude Desktop to control Revit. Instead of writing scripts, you can just chat with Claude and say things like:

- "Create a 30ft x 25ft house with 4 walls"
- "Add a floor slab at level L1"
- "Show me all the walls in the model"
- "Create a new level at 20 feet elevation"

Claude will understand your intent and execute the appropriate Revit commands.

## Prerequisites

✅ Revit 2024 or 2025 installed
✅ RevitMCP Bridge add-in installed (already done!)
✅ Python 3.11+ installed
✅ Claude Desktop app installed

## Installation Steps

### Step 1: Install Claude Desktop

If you don't have it already:

1. Download from: https://claude.ai/download
2. Install and sign in with your Anthropic account

### Step 2: Configure Claude Desktop

1. **Find your Claude Desktop config file**:
   - Windows: `%APPDATA%\Claude\claude_desktop_config.json`
   - Full path: `C:\Users\samo3\AppData\Roaming\Claude\claude_desktop_config.json`

2. **Copy the configuration**:

Open `claude_desktop_config.json` in Notepad and paste this content:

```json
{
  "mcpServers": {
    "revit": {
      "command": "C:\\Users\\samo3\\AppData\\Local\\Programs\\Python\\Python313\\python.exe",
      "args": [
        "-m",
        "revit_mcp_server.mcp_server"
      ],
      "env": {
        "MCP_REVIT_WORKSPACE_DIR": "C:\\Users\\samo3\\Documents",
        "MCP_REVIT_ALLOWED_DIRECTORIES": "C:\\Users\\samo3\\Documents",
        "MCP_REVIT_BRIDGE_URL": "http://127.0.0.1:3000",
        "MCP_REVIT_MODE": "bridge"
      }
    }
  }
}
```

**OR** just copy the file we created:

```powershell
# Copy the config file to Claude Desktop
copy "C:\Users\samo3\OneDrive - Heijmans N.V\Documenten\GitHub\Autodesk-Revit-MCP-Server\claude_desktop_config.json" "$env:APPDATA\Claude\claude_desktop_config.json"
```

3. **Restart Claude Desktop** completely (close and reopen)

### Step 3: Verify Installation

1. Open Claude Desktop
2. Start a new conversation
3. Look for the 🔌 icon (MCP tools) - you should see "revit" server connected
4. You should see tools like:
   - `revit_health`
   - `revit_create_wall`
   - `revit_create_floor`
   - `revit_list_levels`
   - And more!

## Usage

### Before You Start

**IMPORTANT**: Make sure Revit is running with a project open before using Claude!

1. Open Revit 2024
2. Open or create a project
3. The RevitMCP Bridge should automatically start (check logs if needed)

### Example Conversations

#### Example 1: Check Revit Status

**You**: "Is Revit running? What's the current project?"

**Claude**: Will use `revit_health` and `revit_get_document_info` to check status

---

#### Example 2: Create a Simple House

**You**: "Create a simple rectangular house for me. Make it 30 feet by 25 feet with 10 foot tall walls. Put it on level L1."

**Claude**: Will:
1. Create 4 walls forming a rectangle
2. Add a floor slab
3. Report what was created

---

#### Example 3: List Elements

**You**: "Show me all the walls in the current project"

**Claude**: Will use `revit_list_elements` with category="Walls"

---

#### Example 4: Create Custom Structure

**You**: "I need a commercial building. Create a 50ft x 40ft footprint with walls that are 15 feet tall. Use level L1."

**Claude**: Will calculate the 4 wall coordinates and create them

---

#### Example 5: Multi-Step Task

**You**: "Build me a two-story house:
- First floor: 30ft x 25ft on L1
- Walls: 10 feet tall
- Create a second level at 10 feet
- Add floors on both levels"

**Claude**: Will:
1. Create walls for first floor
2. Create floor slab on L1
3. Create new level L2 at 10ft
4. Create second floor at L2

## Available Tools

### Basic Operations

- **revit_health**: Check if Revit is running
- **revit_get_document_info**: Get project information
- **revit_list_levels**: List all levels
- **revit_list_views**: List all views
- **revit_list_elements**: List elements by category

### Creation Tools

- **revit_create_wall**: Create a wall between two points
- **revit_create_floor**: Create a floor with boundary points
- **revit_create_roof**: Create a roof structure
- **revit_create_level**: Create a new level

### Document Operations

- **revit_save_document**: Save the current project

## Tips for Natural Language Control

### Be Specific

❌ "Create a wall"
✅ "Create a wall from (0,0) to (30,0) that's 10 feet tall on level L1"

### Use Clear Dimensions

✅ "30 feet by 25 feet"
✅ "10 foot tall walls"
✅ "at elevation 20 feet"

### Specify Levels

Always mention which level to use:
✅ "on level L1"
✅ "at level L2"

### Ask Claude to Plan First

**You**: "I want to create a house with 4 rooms. Can you plan out the walls I'll need?"

**Claude**: Will help you design the structure before creating it

## Troubleshooting

### "Revit Bridge Error"

**Problem**: Claude can't connect to Revit

**Solution**:
1. Make sure Revit is running
2. Make sure a project is open (not just the start screen)
3. Test the bridge: `curl http://localhost:3000/health`
4. Check bridge logs: `C:\Users\samo3\AppData\Roaming\RevitMCP\Logs\`

### MCP Server Not Showing in Claude Desktop

**Problem**: No 🔌 icon or "revit" server in Claude Desktop

**Solution**:
1. Check config file location: `%APPDATA%\Claude\claude_desktop_config.json`
2. Verify JSON is valid (no syntax errors)
3. Restart Claude Desktop completely
4. Check Claude Desktop logs in Developer Tools (View > Toggle Developer Tools)

### "Level not found" Errors

**Problem**: Claude tries to use "Level 1" but your project has "L1"

**Solution**: Tell Claude the correct level names:
**You**: "List all the levels in the project first, then create the walls"

### Python Not Found

**Problem**: Claude can't find Python

**Solution**: Update the `command` path in `claude_desktop_config.json` to your Python installation:
```bash
# Find your Python path
python -c "import sys; print(sys.executable)"
```

## Advanced Usage

### Complex Structures

**You**: "Create a building with an L-shape floor plan. The horizontal part should be 60ft x 30ft, and the vertical part should be 40ft x 25ft extending from the right side."

Claude will help you plan and create complex geometries!

### Parametric Design

**You**: "Create 10 walls spaced 5 feet apart, each 20 feet long, running north-south"

Claude can create patterns and repetitive elements!

### Integration with Other Tasks

**You**: "Create a 30x25 house, then export a PDF of the floor plan"

Claude can chain multiple operations together!

## Example Session

```
You: Hi! I want to design a small house in Revit. Can you help?

Claude: I'd be happy to help you design a house in Revit! Let me first check
if Revit is running and what project is open.

[Claude uses revit_health and revit_get_document_info]

Claude: Great! Revit is running with "Project1" open. What kind of house
would you like to create? Can you tell me:
- Approximate size (length x width)?
- Number of stories?
- Wall height?
- Any specific requirements?

You: Make it a single story house, 30ft by 25ft, with 10ft tall walls

Claude: Perfect! I'll create a single-story house for you. Let me:
1. Check what levels are available
2. Create 4 exterior walls (30ft x 25ft)
3. Add a floor slab
4. Report what was created

[Claude executes the tools]

Claude: ✓ House created successfully!

Created in your Revit project:
- 4 exterior walls forming a 30ft x 25ft rectangle
- 1 floor slab (750 sq ft)
- Wall height: 10 feet
- Level: L1

Would you like me to add any doors, windows, or interior walls?
```

## Next Steps

Once you're comfortable with basic operations:

1. **Explore More Tools**: The RevitMCP bridge has 50+ tools available
2. **Create Complex Designs**: Let Claude help you design entire buildings
3. **Automate Workflows**: Use Claude to batch-create elements
4. **Export & Document**: Use export tools to generate PDFs, DWGs, etc.

## Support

- **Issues**: https://github.com/Sam-AEC/Autodesk-Revit-MCP-Server/issues
- **Documentation**: See other guides in this repository
- **Logs**:
  - Bridge: `C:\Users\samo3\AppData\Roaming\RevitMCP\Logs\`
  - Claude Desktop: View > Toggle Developer Tools > Console

---

**Enjoy controlling Revit with natural language! 🎉**
