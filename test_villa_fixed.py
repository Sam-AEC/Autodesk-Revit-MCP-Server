#!/usr/bin/env python3
"""
Villa Building Test Script
Tests all MCP tools by building a complete villa in Revit
"""

import requests
import json
import time
from typing import Dict, Any, List

BRIDGE_URL = "http://localhost:3000"
TEST_RESULTS = []


class VillaBuilder:
    def __init__(self, bridge_url: str = BRIDGE_URL):
        self.bridge_url = bridge_url
        self.test_count = 0
        self.pass_count = 0
        self.fail_count = 0

    def call_tool(self, tool: str, payload: Dict[str, Any] = None) -> Dict[str, Any]:
        """Call a Revit tool via the bridge"""
        self.test_count += 1
        test_num = self.test_count

        try:
            print(f"\n{'='*60}")
            print(f"Test #{test_num}: {tool}")
            print(f"{'='*60}")

            if payload:
                print(f"Payload: {json.dumps(payload, indent=2)}")

            response = requests.post(
                f"{self.bridge_url}/execute",
                json={"tool": tool, "payload": payload or {}},
                timeout=30
            )

            result = response.json()

            if response.status_code == 200:
                print(f"PASS PASS - Status: {response.status_code}")
                print(f"Response: {json.dumps(result, indent=2)[:500]}")
                self.pass_count += 1
                TEST_RESULTS.append({"test": test_num, "tool": tool, "status": "PASS", "result": result})
                return result
            else:
                print(f"FAIL FAIL - Status: {response.status_code}")
                print(f"Error: {result}")
                self.fail_count += 1
                TEST_RESULTS.append({"test": test_num, "tool": tool, "status": "FAIL", "error": result})
                return None

        except Exception as e:
            print(f"FAIL EXCEPTION - {str(e)}")
            self.fail_count += 1
            TEST_RESULTS.append({"test": test_num, "tool": tool, "status": "EXCEPTION", "error": str(e)})
            return None

    def print_summary(self):
        """Print test summary"""
        print(f"\n\n{'='*60}")
        print("TEST SUMMARY")
        print(f"{'='*60}")
        print(f"Total Tests: {self.test_count}")
        print(f"PASS Passed: {self.pass_count}")
        print(f"FAIL Failed: {self.fail_count}")
        print(f"Success Rate: {(self.pass_count / self.test_count * 100):.1f}%")
        print(f"{'='*60}\n")


def main():
    print("""
==============================================================
          REVIT MCP - VILLA BUILDING TEST SUITE

  Testing all available tools by building a complete
  10m x 12m villa with rooms, doors, and windows
==============================================================
    """)

    builder = VillaBuilder()

    # Phase 1: Server Health Check
    print("\n🏥 PHASE 1: Server Health Check")
    print("-" * 60)
    builder.call_tool("revit.health")

    # Phase 2: Document Setup
    print("\n📄 PHASE 2: Document Setup")
    print("-" * 60)
    builder.call_tool("revit.get_document_info")

    # Phase 3: Level Management
    print("\n📐 PHASE 3: Level Management")
    print("-" * 60)
    levels_result = builder.call_tool("revit.list_levels")

    builder.call_tool("revit.create_level", {
        "name": "First Floor",
        "elevation": 3500
    })

    builder.call_tool("revit.create_level", {
        "name": "Roof",
        "elevation": 7000
    })

    builder.call_tool("revit.list_levels")

    # Phase 4: External Walls (10m x 12m rectangle)
    print("\n🧱 PHASE 4: Create External Walls")
    print("-" * 60)

    # South wall (10m width along X)
    builder.call_tool("revit.create_wall", {
        "start": [0, 0, 0],
        "end": [10000, 0, 0],
        "height": 2800,
        "level_name": "Level 1"
    })

    # East wall (12m length along Y)
    builder.call_tool("revit.create_wall", {
        "start": [10000, 0, 0],
        "end": [10000, 12000, 0],
        "height": 2800,
        "level_name": "Level 1"
    })

    # North wall
    builder.call_tool("revit.create_wall", {
        "start": [10000, 12000, 0],
        "end": [0, 12000, 0],
        "height": 2800,
        "level_name": "Level 1"
    })

    # West wall
    builder.call_tool("revit.create_wall", {
        "start": [0, 12000, 0],
        "end": [0, 0, 0],
        "height": 2800,
        "level_name": "Level 1"
    })

    # Phase 5: Internal Walls
    print("\n🏠 PHASE 5: Create Internal Walls")
    print("-" * 60)

    # Hallway wall (divides living area from bedrooms)
    builder.call_tool("revit.create_wall", {
        "start": [3000, 0, 0],
        "end": [3000, 12000, 0],
        "height": 2800,
        "level_name": "Level 1"
    })

    # Bedroom divider
    builder.call_tool("revit.create_wall", {
        "start": [3000, 6000, 0],
        "end": [10000, 6000, 0],
        "height": 2800,
        "level_name": "Level 1"
    })

    # Bathroom wall
    builder.call_tool("revit.create_wall", {
        "start": [7000, 0, 0],
        "end": [7000, 6000, 0],
        "height": 2800,
        "level_name": "Level 1"
    })

    # Phase 6: Query Elements
    print("\n🔍 PHASE 6: Query Created Elements")
    print("-" * 60)
    builder.call_tool("revit.list_elements_by_category", {"category": "Walls"})

    # Phase 7: Floors
    print("\n🏗️ PHASE 7: Create Floor Slabs")
    print("-" * 60)
    builder.call_tool("revit.create_floor", {
        "boundary": [
            [0, 0, 0],
            [10000, 0, 0],
            [10000, 12000, 0],
            [0, 12000, 0]
        ],
        "level_name": "Level 1"
    })

    # Phase 8: Families
    print("\n👪 PHASE 8: List Available Families")
    print("-" * 60)
    families_result = builder.call_tool("revit.list_families", {"category": "Doors"})
    builder.call_tool("revit.list_families", {"category": "Windows"})

    # Phase 9: Place Doors
    print("\n🚪 PHASE 9: Place Doors")
    print("-" * 60)

    # Front door
    builder.call_tool("revit.place_door", {
        "location": [5000, 0, 0],
        "level_name": "Level 1"
    })

    # Phase 10: Place Windows
    print("\n🪟 PHASE 10: Place Windows")
    print("-" * 60)
    builder.call_tool("revit.place_window", {
        "location": [1500, 0, 1000],
        "level_name": "Level 1"
    })

    builder.call_tool("revit.place_window", {
        "location": [8500, 0, 1000],
        "level_name": "Level 1"
    })

    # Phase 11: Rooms
    print("\n🏡 PHASE 11: Create Rooms")
    print("-" * 60)
    builder.call_tool("revit.create_room", {
        "location": [1500, 6000, 0],
        "level_name": "Level 1",
        "name": "Living Room",
        "number": "101"
    })

    builder.call_tool("revit.create_room", {
        "location": [6500, 3000, 0],
        "level_name": "Level 1",
        "name": "Bedroom 1",
        "number": "102"
    })

    builder.call_tool("revit.create_room", {
        "location": [6500, 9000, 0],
        "level_name": "Level 1",
        "name": "Bedroom 2",
        "number": "103"
    })

    builder.call_tool("revit.create_room", {
        "location": [8500, 3000, 0],
        "level_name": "Level 1",
        "name": "Bathroom",
        "number": "104"
    })

    # Phase 12: Save
    print("\n💾 PHASE 12: Save Document")
    print("-" * 60)
    builder.call_tool("revit.save_document")

    # Final Summary
    builder.print_summary()

    # Save results to file
    with open("villa_test_results.json", "w") as f:
        json.dump(TEST_RESULTS, f, indent=2)
    print("📊 Detailed results saved to: villa_test_results.json\n")


if __name__ == "__main__":
    main()
