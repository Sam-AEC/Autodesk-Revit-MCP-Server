# Testing RevitMCP with Claude Desktop

## Current Status
✅ Revit Bridge: Running
✅ MCP Server: Installed and working
✅ Claude Config: Set up correctly

## Step-by-Step Testing

### 1. Restart Claude Desktop
**IMPORTANT**: You must restart Claude Desktop for it to pick up the new MCP server.

1. Close Claude Desktop **completely** (right-click tray icon > Exit)
2. Wait 5 seconds
3. Reopen Claude Desktop

### 2. Verify Connection
In Claude Desktop, you should see:
- A connection indicator for "revit" server
- Available tools in the MCP section

If you see "Windows-MCP failed", that's OK - that's a different server. Focus on the "revit" server.

### 3. Test Commands

Copy and paste these into Claude Desktop one at a time:

#### Test 1: Health Check
```
Check if Revit is running and tell me what project is open.
```

**Expected**: Claude will use `revit_health` and `revit_get_document_info` tools and tell you:
- Revit is running
- Version 2024
- Project name: "Project1"

---

#### Test 2: List Levels
```
What levels are available in the current Revit project?
```

**Expected**: Claude will list levels like L1, L2, Level 2, etc.

---

#### Test 3: Create a Simple Wall
```
Create a wall in Revit from point (0,0) to point (20,0) that's 10 feet tall on level L1.
```

**Expected**: Claude will use `revit_create_wall` and confirm wall creation with the wall ID.

---

#### Test 4: Create a House
```
Create a simple rectangular house for me:
- 30 feet wide by 25 feet deep
- 10 feet tall walls
- Place it on level L1
- Include a floor slab
```

**Expected**: Claude will:
1. Create 4 walls
2. Create a floor
3. Confirm what was created

Check your Revit window - you should see the geometry!

---

#### Test 5: Query the Model
```
How many walls are currently in the Revit project?
```

**Expected**: Claude will use `revit_list_elements` and tell you the count.

---

## Troubleshooting

### Issue: "revit" server not visible
**Solution**:
1. Check config file exists: `%APPDATA%\Claude\claude_desktop_config.json`
2. Restart Claude Desktop completely
3. Check Developer Console (View > Toggle Developer Tools) for errors

### Issue: "Bridge unreachable" error
**Solution**:
1. Make sure Revit is running with a project open
2. Test bridge: Open PowerShell and run `curl http://localhost:3000/health`
3. Check bridge logs: `C:\Users\samo3\AppData\Roaming\RevitMCP\Logs\`

### Issue: Claude says "I don't have access to that tool"
**Solution**:
1. The MCP server might not have started
2. Check Claude Desktop Developer Console for startup errors
3. Try running manually:
   ```powershell
   cd "C:\Users\samo3\OneDrive - Heijmans N.V\Documenten\GitHub\Autodesk-Revit-MCP-Server"
   python -m revit_mcp_server.mcp_server
   ```
   Look for any errors

### Issue: Tools execute but nothing appears in Revit
**Solution**:
1. Make sure you're using the correct level name (L1, not "Level 1")
2. Check Revit is showing the correct view
3. Try zooming to fit (type ZF in Revit)

---

## What Claude Can Do

### Create Elements
- Walls (any configuration)
- Floors (rectangular or custom)
- Roofs
- Levels

### Query Information
- List walls, floors, etc.
- Get document info
- Check Revit status
- List levels

### Understand Natural Language
Claude understands:
- "Create a 30 by 25 foot building"
- "Make a house with 4 rooms"
- "Add a floor on level L1"
- "Show me all the walls"
- "Create a two-story structure"

---

## Example Conversation

```
You: Hi Claude! I'm working on a Revit project.

Claude: Hello! I can help you with your Revit project. Let me check
if Revit is running.

[Uses revit_health tool]

Claude: Great! Revit 2024 is running with "Project1" open. What would
you like to create or modify?

You: Create a simple single-family house, about 30 feet by 25 feet.

Claude: I'll create a house for you. Let me:
1. Check available levels
2. Create 4 exterior walls (30ft x 25ft)
3. Add a floor slab

[Uses revit_list_levels, revit_create_wall (x4), revit_create_floor]

Claude: Done! I've created:
- 4 exterior walls forming a 30ft x 25ft rectangle
- Floor slab (750 sq ft)
- Wall height: 10 feet
- Located on level L1

Check your Revit window to see the house. Would you like me to
add interior walls to create rooms?

You: Yes! Divide it into a living room and 2 bedrooms.

Claude: I'll create interior walls to divide your house into 3 rooms...
```

---

## Configuration Location

Your Claude Desktop config is at:
```
C:\Users\samo3\AppData\Roaming\Claude\claude_desktop_config.json
```

To edit:
```powershell
notepad "%APPDATA%\Claude\claude_desktop_config.json"
```

Current configuration:
```json
{
  "mcpServers": {
    "revit": {
      "command": "C:\\Users\\samo3\\AppData\\Local\\Programs\\Python\\Python313\\python.exe",
      "args": ["-m", "revit_mcp_server.mcp_server"],
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

---

## Verification Checklist

Before testing with Claude:

- [ ] Revit 2024 is running
- [ ] A project is open in Revit (not just start screen)
- [ ] Bridge health check passes: `curl http://localhost:3000/health`
- [ ] Claude Desktop has been restarted
- [ ] "revit" server appears in MCP tools

Once all checked, start testing with Claude!

---

## Quick Commands

### Verify Bridge
```powershell
curl http://localhost:3000/health
```

### Verify MCP Server
```powershell
python -m revit_mcp_server.mcp_server
# Press Ctrl+C to stop
```

### View Logs
```powershell
# Bridge logs
Get-Content "C:\Users\samo3\AppData\Roaming\RevitMCP\Logs\bridge*.jsonl" -Tail 20
```

### Re-run Setup
```powershell
.\setup-claude-desktop.ps1
```

---

**Ready to test! Restart Claude Desktop and start chatting!** 🚀
