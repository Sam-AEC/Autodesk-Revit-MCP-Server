"""Standards compliance checking for BIM models."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class NamingRule:
    """A naming convention rule."""

    id: str
    name: str
    category: str
    pattern: str
    description: str
    compiled_pattern: re.Pattern | None = None

    def __post_init__(self) -> None:
        """Compile the regex pattern after initialization."""
        if self.compiled_pattern is None:
            self.compiled_pattern = re.compile(self.pattern)

    def matches(self, name: str) -> bool:
        """Check if a name matches this naming rule.

        Args:
            name: The name to check

        Returns:
            True if name matches the pattern, False otherwise
        """
        if self.compiled_pattern is None:
            return False
        return bool(self.compiled_pattern.match(name))


class NamingConventionValidator:
    """Validator for checking naming conventions."""

    def __init__(self) -> None:
        """Initialize the naming convention validator."""
        self.rules: dict[str, NamingRule] = {}
        self.violations: list[dict[str, Any]] = []

    def add_rule(self, rule: NamingRule) -> None:
        """Add a naming rule.

        Args:
            rule: The naming rule to add
        """
        self.rules[rule.id] = rule

    def add_view_naming_rules(self) -> None:
        """Add standard view naming rules."""
        # Floor plans: FP-L01, FP-L02, FP-ROOF
        self.add_rule(
            NamingRule(
                id="view_floor_plan",
                name="Floor Plan Naming",
                category="views",
                pattern=r"^FP-[A-Z0-9]+$",
                description="Floor plans must be named FP-XXXX",
            )
        )

        # Sections: SEC-A, SEC-B, SEC-1
        self.add_rule(
            NamingRule(
                id="view_section",
                name="Section Naming",
                category="views",
                pattern=r"^SEC-[A-Z0-9]+$",
                description="Sections must be named SEC-X",
            )
        )

        # 3D Views: 3D-ARCH, 3D-STRUCT, 3D-MEP
        self.add_rule(
            NamingRule(
                id="view_3d",
                name="3D View Naming",
                category="views",
                pattern=r"^3D-[A-Z]+$",
                description="3D views must be named 3D-XXXX",
            )
        )

    def add_sheet_naming_rules(self) -> None:
        """Add standard sheet naming rules."""
        # Sheets: A-101, M-201, E-301
        self.add_rule(
            NamingRule(
                id="sheet_number",
                name="Sheet Number Format",
                category="sheets",
                pattern=r"^[A-Z]-\d{3}$",
                description="Sheet numbers must be X-NNN format",
            )
        )

    def add_family_naming_rules(self) -> None:
        """Add standard family naming rules."""
        # Walls: W-EXT-200, W-INT-100
        self.add_rule(
            NamingRule(
                id="family_wall",
                name="Wall Family Naming",
                category="families",
                pattern=r"^W-[A-Z]+-\d+$",
                description="Wall families must be named W-TYPE-WIDTH",
            )
        )

        # Doors: D-SINGLE-900, D-DOUBLE-1800
        self.add_rule(
            NamingRule(
                id="family_door",
                name="Door Family Naming",
                category="families",
                pattern=r"^D-[A-Z]+-\d+$",
                description="Door families must be named D-TYPE-WIDTH",
            )
        )

        # Windows: W-FIXED-1200, W-CASEMENT-900
        self.add_rule(
            NamingRule(
                id="family_window",
                name="Window Family Naming",
                category="families",
                pattern=r"^WN-[A-Z]+-\d+$",
                description="Window families must be named WN-TYPE-WIDTH",
            )
        )

    def validate_name(
        self, name: str, element_type: str, rule_id: str | None = None
    ) -> tuple[bool, str | None]:
        """Validate a name against rules.

        Args:
            name: The name to validate
            element_type: Type of element (e.g., 'view', 'sheet', 'family')
            rule_id: Specific rule ID to check (optional)

        Returns:
            Tuple of (is_valid, error_message)
        """
        if rule_id:
            rule = self.rules.get(rule_id)
            if rule and rule.matches(name):
                return True, None
            if rule:
                return False, rule.description
            return False, f"Rule {rule_id} not found"

        # Check all rules for this element type
        for rule in self.rules.values():
            if element_type in rule.id and rule.matches(name):
                return True, None

        # No matching rule found
        return False, f"No naming rule matched for {element_type}"

    def validate_element(
        self,
        element_id: str | int,
        element_name: str,
        element_type: str,
        rule_id: str | None = None,
    ) -> bool:
        """Validate an element's name and record violations.

        Args:
            element_id: ID of the element
            element_name: Name of the element
            element_type: Type of element
            rule_id: Specific rule to check (optional)

        Returns:
            True if valid, False if violation found
        """
        is_valid, error_message = self.validate_name(element_name, element_type, rule_id)

        if not is_valid:
            self.violations.append(
                {
                    "element_id": element_id,
                    "element_name": element_name,
                    "element_type": element_type,
                    "rule_id": rule_id,
                    "error": error_message,
                }
            )

        return is_valid

    def get_violations(self) -> list[dict[str, Any]]:
        """Get all naming convention violations.

        Returns:
            List of violation dictionaries
        """
        return self.violations

    def get_violations_by_type(self, element_type: str) -> list[dict[str, Any]]:
        """Get violations for a specific element type.

        Args:
            element_type: Type of element to filter by

        Returns:
            List of violations for that type
        """
        return [v for v in self.violations if v["element_type"] == element_type]

    def clear_violations(self) -> None:
        """Clear all recorded violations."""
        self.violations = []

    def get_violation_count(self) -> int:
        """Get total number of violations.

        Returns:
            Count of violations
        """
        return len(self.violations)


@dataclass
class ParameterRule:
    """Rule for parameter validation."""

    id: str
    name: str
    parameter_name: str
    required: bool = True
    value_type: str | None = None
    allowed_values: list[Any] | None = None
    min_value: float | None = None
    max_value: float | None = None
    pattern: str | None = None
    validator_function: Callable[[Any], bool] | None = None

    def validate_value(self, value: Any) -> tuple[bool, str | None]:
        """Validate a parameter value.

        Args:
            value: The value to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check if required and missing
        if self.required and (value is None or value == ""):
            return False, f"Required parameter '{self.parameter_name}' is missing"

        # If not required and missing, that's okay
        if value is None or value == "":
            return True, None

        # Type validation
        if self.value_type:
            expected_type = self._get_python_type(self.value_type)
            if expected_type and not isinstance(value, expected_type):
                return (
                    False,
                    f"Parameter '{self.parameter_name}' must be {self.value_type}",
                )

        # Allowed values validation
        if self.allowed_values and value not in self.allowed_values:
            return (
                False,
                f"Parameter '{self.parameter_name}' must be one of {self.allowed_values}",
            )

        # Numeric range validation
        if self.min_value is not None and isinstance(value, (int, float)):
            if value < self.min_value:
                return (
                    False,
                    f"Parameter '{self.parameter_name}' must be >= {self.min_value}",
                )

        if self.max_value is not None and isinstance(value, (int, float)):
            if value > self.max_value:
                return (
                    False,
                    f"Parameter '{self.parameter_name}' must be <= {self.max_value}",
                )

        # Pattern validation for strings
        if self.pattern and isinstance(value, str):
            if not re.match(self.pattern, value):
                return (
                    False,
                    f"Parameter '{self.parameter_name}' does not match pattern {self.pattern}",
                )

        # Custom validator function
        if self.validator_function:
            if not self.validator_function(value):
                return (
                    False,
                    f"Parameter '{self.parameter_name}' failed custom validation",
                )

        return True, None

    def _get_python_type(self, type_name: str) -> type | None:
        """Convert type name string to Python type.

        Args:
            type_name: String name of type

        Returns:
            Python type object or None
        """
        type_map = {
            "string": str,
            "int": int,
            "float": float,
            "bool": bool,
            "number": (int, float),
        }
        return type_map.get(type_name.lower())


@dataclass
class LevelValidationIssue:
    """Issue found during level validation."""

    level_id: str | int
    level_name: str
    issue_type: str
    description: str
    elevation: float | None = None


class LevelGridValidator:
    """Validator for levels and grids."""

    def __init__(self) -> None:
        """Initialize the level/grid validator."""
        self.issues: list[LevelValidationIssue] = []

    def validate_level_naming(
        self, levels: list[dict[str, Any]], pattern: str = r"^L\d{2}$"
    ) -> list[LevelValidationIssue]:
        """Validate level naming conventions.

        Args:
            levels: List of level dictionaries with 'id', 'name', 'elevation'
            pattern: Regex pattern for level names (default: L01, L02, etc.)

        Returns:
            List of validation issues
        """
        issues = []
        compiled_pattern = re.compile(pattern)

        for level in levels:
            if not compiled_pattern.match(level["name"]):
                issue = LevelValidationIssue(
                    level_id=level["id"],
                    level_name=level["name"],
                    issue_type="naming",
                    description=f"Level name '{level['name']}' does not match pattern {pattern}",
                    elevation=level.get("elevation"),
                )
                issues.append(issue)
                self.issues.append(issue)

        return issues

    def validate_level_spacing(
        self,
        levels: list[dict[str, Any]],
        min_spacing: float = 3000.0,
        max_spacing: float = 5000.0,
    ) -> list[LevelValidationIssue]:
        """Validate spacing between levels.

        Args:
            levels: List of level dictionaries with 'id', 'name', 'elevation'
            min_spacing: Minimum allowed spacing in mm
            max_spacing: Maximum allowed spacing in mm

        Returns:
            List of validation issues
        """
        issues = []

        # Sort levels by elevation
        sorted_levels = sorted(levels, key=lambda x: x["elevation"])

        for i in range(len(sorted_levels) - 1):
            level1 = sorted_levels[i]
            level2 = sorted_levels[i + 1]

            spacing = level2["elevation"] - level1["elevation"]

            if spacing < min_spacing:
                issue = LevelValidationIssue(
                    level_id=level2["id"],
                    level_name=level2["name"],
                    issue_type="spacing_too_small",
                    description=f"Level spacing {spacing:.0f}mm is below minimum {min_spacing:.0f}mm",
                    elevation=level2["elevation"],
                )
                issues.append(issue)
                self.issues.append(issue)

            if spacing > max_spacing:
                issue = LevelValidationIssue(
                    level_id=level2["id"],
                    level_name=level2["name"],
                    issue_type="spacing_too_large",
                    description=f"Level spacing {spacing:.0f}mm exceeds maximum {max_spacing:.0f}mm",
                    elevation=level2["elevation"],
                )
                issues.append(issue)
                self.issues.append(issue)

        return issues

    def validate_grid_naming(
        self, grids: list[dict[str, Any]]
    ) -> list[LevelValidationIssue]:
        """Validate grid naming conventions.

        Grids should be named with letters (A, B, C) or numbers (1, 2, 3).

        Args:
            grids: List of grid dictionaries with 'id', 'name'

        Returns:
            List of validation issues
        """
        issues = []

        # Valid patterns: single letter A-Z or number 1-99
        letter_pattern = re.compile(r"^[A-Z]$")
        number_pattern = re.compile(r"^\d{1,2}$")

        for grid in grids:
            name = grid["name"]
            if not letter_pattern.match(name) and not number_pattern.match(name):
                issue = LevelValidationIssue(
                    level_id=grid["id"],
                    level_name=name,
                    issue_type="grid_naming",
                    description=f"Grid name '{name}' should be single letter or 1-2 digit number",
                )
                issues.append(issue)
                self.issues.append(issue)

        return issues

    def validate_grid_spacing(
        self,
        grids: list[dict[str, Any]],
        min_spacing: float = 3000.0,
        max_spacing: float = 12000.0,
    ) -> list[LevelValidationIssue]:
        """Validate spacing between parallel grids.

        Args:
            grids: List of grid dictionaries with 'id', 'name', 'position'
            min_spacing: Minimum allowed spacing in mm
            max_spacing: Maximum allowed spacing in mm

        Returns:
            List of validation issues
        """
        issues = []

        # Group grids by orientation (horizontal vs vertical)
        horizontal = [g for g in grids if g.get("orientation") == "horizontal"]
        vertical = [g for g in grids if g.get("orientation") == "vertical"]

        # Check horizontal grid spacing
        issues.extend(
            self._check_grid_group_spacing(horizontal, min_spacing, max_spacing, "horizontal")
        )

        # Check vertical grid spacing
        issues.extend(
            self._check_grid_group_spacing(vertical, min_spacing, max_spacing, "vertical")
        )

        return issues

    def _check_grid_group_spacing(
        self,
        grids: list[dict[str, Any]],
        min_spacing: float,
        max_spacing: float,
        orientation: str,
    ) -> list[LevelValidationIssue]:
        """Check spacing for a group of parallel grids.

        Args:
            grids: List of parallel grids
            min_spacing: Minimum spacing
            max_spacing: Maximum spacing
            orientation: Grid orientation

        Returns:
            List of issues
        """
        issues = []

        if len(grids) < 2:
            return issues

        # Sort by position
        sorted_grids = sorted(grids, key=lambda x: x["position"])

        for i in range(len(sorted_grids) - 1):
            grid1 = sorted_grids[i]
            grid2 = sorted_grids[i + 1]

            spacing = abs(grid2["position"] - grid1["position"])

            if spacing < min_spacing:
                issue = LevelValidationIssue(
                    level_id=grid2["id"],
                    level_name=grid2["name"],
                    issue_type="grid_spacing_too_small",
                    description=f"{orientation.capitalize()} grid spacing {spacing:.0f}mm is below minimum {min_spacing:.0f}mm",
                )
                issues.append(issue)
                self.issues.append(issue)

            if spacing > max_spacing:
                issue = LevelValidationIssue(
                    level_id=grid2["id"],
                    level_name=grid2["name"],
                    issue_type="grid_spacing_too_large",
                    description=f"{orientation.capitalize()} grid spacing {spacing:.0f}mm exceeds maximum {max_spacing:.0f}mm",
                )
                issues.append(issue)
                self.issues.append(issue)

        return issues

    def get_issues(self) -> list[LevelValidationIssue]:
        """Get all validation issues.

        Returns:
            List of all issues
        """
        return self.issues

    def get_issues_by_type(self, issue_type: str) -> list[LevelValidationIssue]:
        """Get issues of a specific type.

        Args:
            issue_type: Type of issue to filter by

        Returns:
            List of issues of that type
        """
        return [issue for issue in self.issues if issue.issue_type == issue_type]

    def clear_issues(self) -> None:
        """Clear all recorded issues."""
        self.issues = []

    def get_issue_count(self) -> int:
        """Get total number of issues.

        Returns:
            Count of issues
        """
        return len(self.issues)
