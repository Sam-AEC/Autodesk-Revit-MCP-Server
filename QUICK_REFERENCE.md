# RevitMCP - Quick Reference Card

## ✅ Setup Status
Everything is configured and ready to use!

## 🚀 How to Use (3 Steps)

### 1. Make Sure Revit is Running
- Open Revit 2024
- Open or create a project

### 2. Open/Restart Claude Desktop
- Look for "revit" in the MCP servers list
- You'll see tools like `revit_health`, `revit_create_wall`, etc.

### 3. Start Chatting!
Just describe what you want in natural language.

---

## 💬 Example Commands

### Check Status
```
"Is Revit running?"
"What project is open?"
"Show me the document information"
```

### Create Structures
```
"Create a 30ft by 25ft house with 10ft tall walls"
"Build a rectangular building that's 50 feet by 40 feet"
"Add a floor slab at level L1 for a 30x25 area"
```

### Query Model
```
"How many walls are in the project?"
"List all the levels available"
"Show me all the elements in the Walls category"
```

### Create Levels
```
"Create a new level at 20 feet elevation"
"Add a level called 'Roof' at 30 feet"
```

### Complex Requests
```
"Create a two-story house:
- First floor: 40x30 feet
- Walls: 10 feet tall
- Second level at 10 feet
- Add floors on both levels"
```

---

## 🛠️ Available Tools

| Tool | What It Does |
|------|--------------|
| `revit_health` | Check if Revit is running |
| `revit_create_wall` | Create a wall between two points |
| `revit_create_floor` | Create a floor with boundary |
| `revit_create_roof` | Create a roof structure |
| `revit_create_level` | Create a new level |
| `revit_list_levels` | List all levels in project |
| `revit_list_views` | List all views |
| `revit_list_elements` | List elements by category |
| `revit_get_document_info` | Get project information |
| `revit_save_document` | Save the current document |

---

## 📍 Important Coordinates

Revit uses **feet** by default:
- X axis: East-West (positive = East)
- Y axis: North-South (positive = North)
- Z axis: Up-Down (positive = Up)

Example: A 30ft x 25ft rectangle:
- Southwest corner: (0, 0, 0)
- Southeast corner: (30, 0, 0)
- Northeast corner: (30, 25, 0)
- Northwest corner: (0, 25, 0)

---

## ⚠️ Troubleshooting

### "Bridge Error" or "Cannot connect"
**Fix**: Make sure Revit is running with a project open
```powershell
# Test the bridge
curl http://localhost:3000/health
```

### MCP Server Not Visible in Claude
**Fix**: Restart Claude Desktop completely

### "Level not found"
**Fix**: Ask Claude to list levels first:
```
"What levels are available in this project?"
```
Then use the correct level name (e.g., "L1" not "Level 1")

---

## 📝 Tips for Best Results

### Be Specific
❌ "Create a building"
✅ "Create a 50ft by 40ft building with 15ft tall walls on level L1"

### Let Claude Plan
```
"I need a house with 4 rooms. Help me plan the layout first."
```
Claude will work with you to design before building!

### Work Iteratively
```
1. "Create the exterior walls"
2. "Now add a floor"
3. "Add interior walls to divide into 3 rooms"
```

### Ask for Verification
```
"After creating the walls, list all walls to confirm"
```

---

## 🔧 Quick Commands

### Verify Setup
```powershell
.\verify-setup.ps1
```

### Test Bridge Directly
```powershell
curl http://localhost:3000/health
```

### Reinstall MCP Server
```powershell
cd packages\mcp-server-revit
pip install -e .
```

### View Logs
```powershell
# Bridge logs
Get-Content "C:\Users\samo3\AppData\Roaming\RevitMCP\Logs\bridge*.jsonl" -Tail 20

# Claude Desktop logs
# View > Toggle Developer Tools > Console
```

---

## 📚 Full Documentation

- **Setup Guide**: [CLAUDE_DESKTOP_SETUP.md](CLAUDE_DESKTOP_SETUP.md)
- **Natural Language Guide**: [NATURAL_LANGUAGE_READY.md](NATURAL_LANGUAGE_READY.md)
- **Testing Checklist**: [TESTING_CHECKLIST.md](TESTING_CHECKLIST.md)
- **Quick Start**: [QUICKSTART.md](QUICKSTART.md)

---

## 🎯 Example Session

```
You: Hi! I want to design a house in Revit.

Claude: I'd be happy to help! Let me check if Revit is running.
[Uses revit_health]
Great! Revit 2024 is running with "Project1" open.
What size house would you like?

You: Make it 30 feet by 25 feet, single story

Claude: Perfect! I'll create:
- 4 exterior walls (30ft x 25ft)
- Floor slab
- 10ft wall height
Let me get started...
[Creates the house]
Done! Check your Revit window to see the house structure.

You: Add 3 rooms inside - a living room and 2 bedrooms

Claude: I'll divide the space. Let me plan the layout:
- Living room: 30ft x 12ft (left side)
- Bedroom 1: 15ft x 13ft (top right)
- Bedroom 2: 15ft x 13ft (bottom right)
Does this work?

You: Perfect!

Claude: [Creates interior walls]
All done! Your house now has 3 rooms.
```

---

## ⚡ Current Status

✅ **Revit Bridge**: Running (port 3000)
✅ **Claude Desktop**: Configured
✅ **MCP Server**: Installed
✅ **Python Package**: Ready

**You're all set! Start chatting with Claude!** 🎉
