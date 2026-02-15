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
