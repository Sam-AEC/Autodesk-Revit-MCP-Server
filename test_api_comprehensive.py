"""
Comprehensive API Test Suite for RevitMCP Server
Tests all major API categories and validates responses
"""

import requests
import json

BRIDGE_URL = "http://127.0.0.1:3000"

class APITester:
    def __init__(self):
        self.results = {
            'passed': [],
            'failed': [],
            'skipped': []
        }
        self.wall_ids = []
        self.level_name = None

    def call_tool(self, tool, payload):
        """Call a Revit Bridge tool"""
        data = {
            'tool': tool,
            'payload': payload,
            'request_id': f'{tool}-{hash(str(payload))}'
        }
        try:
            response = requests.post(
                f'{BRIDGE_URL}/execute',
                json=data,
                timeout=30
            )
            return response.json()
        except Exception as e:
            return {'Status': 'error', 'Message': str(e)}

    def test(self, name, tool, payload, validator=None):
        """Run a single test"""
        print(f"\n{'='*70}")
        print(f"TEST: {name}")
        print(f"Tool: {tool}")
        print(f"{'='*70}")

        result = self.call_tool(tool, payload)
        status = result.get('Status', result.get('status', ''))

        if status.lower() == 'ok':
            print("[OK] Test passed")
            if validator:
                try:
                    validator(result)
                    print("[OK] Validation passed")
                except AssertionError as e:
                    print(f"[WARN] Validation failed: {e}")
                    self.results['failed'].append((name, str(e)))
                    return False
            self.results['passed'].append(name)
            return True
        else:
            error_msg = result.get('Message', result.get('message', 'Unknown error'))
            print(f"[FAILED] {error_msg}")
            self.results['failed'].append((name, error_msg))
            return False

    def run_all_tests(self):
        """Execute comprehensive test suite"""
        print("="*70)
        print("REVITMCP COMPREHENSIVE API TEST SUITE")
        print("="*70)

        # Phase 1: Connectivity
        print("\n\nPHASE 1: CONNECTIVITY & STATUS")
        print("-"*70)

        self.test(
            "Health Check",
            "revit.health",
            {},
            lambda r: self.assert_key_exists(r['Result'], 'status')
        )

        self.test(
            "Get Document Info",
            "revit.get_document_info",
            {},
            lambda r: self.assert_key_exists(r['Result'], 'title')
        )

        # Get levels for later use
        levels_result = self.call_tool('revit.list_levels', {})
        if levels_result.get('Status') == 'ok':
            levels = levels_result['Result']['levels']
            self.level_name = levels[0]['name'] if levels else 'L1'
            print(f"[INFO] Using level: {self.level_name}")

        # Phase 2: Geometry Creation
        print("\n\nPHASE 2: GEOMETRY CREATION")
        print("-"*70)

        # Test wall creation and capture IDs
        wall_test = self.test(
            "Create Wall",
            "revit.create_wall",
            {
                'start_point': {'x': 0, 'y': 0, 'z': 0},
                'end_point': {'x': 10, 'y': 0, 'z': 0},
                'height': 10,
                'level': self.level_name
            },
            lambda r: self.assert_key_exists(r['Result'], 'wall_id')
        )

        if wall_test:
            wall_id = self.call_tool('revit.create_wall', {
                'start_point': {'x': 0, 'y': 0, 'z': 0},
                'end_point': {'x': 10, 'y': 0, 'z': 0},
                'height': 10,
                'level': self.level_name
            })['Result'].get('wall_id')
            self.wall_ids.append(wall_id)

        self.test(
            "Create Floor",
            "revit.create_floor",
            {
                'boundary_points': [
                    {'x': 0, 'y': 0, 'z': 0},
                    {'x': 10, 'y': 0, 'z': 0},
                    {'x': 10, 'y': 10, 'z': 0},
                    {'x': 0, 'y': 10, 'z': 0}
                ],
                'level': self.level_name
            },
            lambda r: self.assert_key_exists(r['Result'], 'floor_id')
        )

        # Phase 3: Element Queries
        print("\n\nPHASE 3: ELEMENT QUERIES")
        print("-"*70)

        self.test(
            "List Walls",
            "revit.list_elements_by_category",
            {'category': 'Walls'},
            lambda r: self.assert_key_exists(r['Result'], 'count')
        )

        self.test(
            "List Floors",
            "revit.list_elements_by_category",
            {'category': 'Floors'},
            lambda r: self.assert_key_exists(r['Result'], 'count')
        )

        self.test(
            "List Levels",
            "revit.list_levels",
            {},
            lambda r: self.assert_key_exists(r['Result'], 'levels')
        )

        self.test(
            "List Views",
            "revit.list_views",
            {},
            lambda r: self.assert_key_exists(r['Result'], 'views')
        )

        # Phase 4: Parameters
        print("\n\nPHASE 4: PARAMETERS")
        print("-"*70)

        if self.wall_ids:
            self.test(
                "Get Element Parameters",
                "revit.get_element_parameters",
                {'element_id': self.wall_ids[0]},
                lambda r: self.assert_key_exists(r['Result'], 'parameters')
            )

        # Phase 5: Views
        print("\n\nPHASE 5: VIEW CREATION")
        print("-"*70)

        self.test(
            "Create 3D View",
            "revit.create_3d_view",
            {'name': 'Test 3D View'},
            lambda r: self.assert_key_exists(r['Result'], 'view_id')
        )

        # Phase 6: Universal Bridge (Reflection API)
        print("\n\nPHASE 6: UNIVERSAL BRIDGE (REFLECTION API)")
        print("-"*70)

        self.test(
            "Invoke XYZ Constructor",
            "revit.invoke_method",
            {
                'class_name': 'XYZ',
                'method_name': 'new',
                'arguments': [0.0, 0.0, 0.0],
                'use_transaction': False
            },
            lambda r: self.assert_key_exists(r, 'type')
        )

        # Summary
        self.print_summary()

    def assert_key_exists(self, data, key):
        """Validation helper"""
        assert key in data, f"Key '{key}' not found in response"

    def print_summary(self):
        """Print test results summary"""
        print("\n\n" + "="*70)
        print("TEST SUMMARY")
        print("="*70)

        total = len(self.results['passed']) + len(self.results['failed'])
        passed = len(self.results['passed'])
        failed = len(self.results['failed'])

        print(f"\nTotal Tests: {total}")
        print(f"Passed: {passed} ({100*passed//total if total else 0}%)")
        print(f"Failed: {failed}")

        if self.results['passed']:
            print(f"\n[OK] Passed Tests ({len(self.results['passed'])}):")
            for test in self.results['passed']:
                print(f"  - {test}")

        if self.results['failed']:
            print(f"\n[FAILED] Failed Tests ({len(self.results['failed'])}):")
            for test, error in self.results['failed']:
                print(f"  - {test}: {error}")

        print("\n" + "="*70)

        if failed == 0:
            print("ALL TESTS PASSED! API is fully functional.")
        else:
            print(f"API has {failed} issue(s) that need attention.")

        print("="*70)


if __name__ == "__main__":
    tester = APITester()

    try:
        tester.run_all_tests()
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user.")
        tester.print_summary()
    except Exception as e:
        print(f"\n\nFATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        tester.print_summary()
