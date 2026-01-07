"""
Test MCP server handshake - simulates what Claude Desktop does
"""
import json
import subprocess
import sys
import time

print("="*70)
print("MCP Server Handshake Test")
print("="*70)
print()

# Configuration from claude_desktop_config.json
config = {
    "command": r"C:\Users\samo3\AppData\Local\Programs\Python\Python313\python.exe",
    "args": ["-m", "revit_mcp_server.mcp_server"],
    "env": {
        "MCP_REVIT_WORKSPACE_DIR": r"C:\Users\samo3\Documents",
        "MCP_REVIT_ALLOWED_DIRECTORIES": r"C:\Users\samo3\Documents",
        "MCP_REVIT_BRIDGE_URL": "http://127.0.0.1:3000",
        "MCP_REVIT_MODE": "bridge"
    }
}

print("1. Starting MCP server...")
print(f"   Command: {config['command']}")
print(f"   Args: {' '.join(config['args'])}")
print()

# Start the server
import os
env = os.environ.copy()
env.update(config["env"])

# Change to repo directory
repo_dir = r"C:\Users\samo3\OneDrive - Heijmans N.V\Documenten\GitHub\Autodesk-Revit-MCP-Server"
os.chdir(repo_dir)

try:
    process = subprocess.Popen(
        [config["command"]] + config["args"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
        bufsize=1
    )

    print("2. Server started (PID: {})".format(process.pid))
    print()

    # Send MCP initialize request
    initialize_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "test-client",
                "version": "1.0.0"
            }
        }
    }

    print("3. Sending initialize request...")
    print(json.dumps(initialize_request, indent=2))
    print()

    # Send request
    process.stdin.write(json.dumps(initialize_request) + "\n")
    process.stdin.flush()

    print("4. Waiting for response...")

    # Wait for response (with timeout)
    import select
    timeout = 5
    start = time.time()

    response_lines = []
    while time.time() - start < timeout:
        # Check if there's output available
        try:
            line = process.stdout.readline()
            if line:
                response_lines.append(line.strip())
                print(f"   Received: {line.strip()}")

                # Try to parse as JSON
                try:
                    response = json.loads(line)
                    print()
                    print("5. SUCCESS! Server responded:")
                    print(json.dumps(response, indent=2))
                    break
                except json.JSONDecodeError:
                    # Not JSON yet, keep reading
                    continue
        except:
            break
    else:
        print()
        print("5. TIMEOUT - No valid response received")

        # Check stderr
        stderr = process.stderr.read()
        if stderr:
            print()
            print("STDERR output:")
            print(stderr)

    # Clean up
    process.terminate()
    process.wait(timeout=2)

    print()
    print("="*70)

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

print()
print("Test complete!")
