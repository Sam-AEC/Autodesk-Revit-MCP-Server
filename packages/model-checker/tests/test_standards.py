"""Test standards compliance checking."""

import pytest

from model_checker.standards import (
    NamingConventionValidator,
    NamingRule,
    ParameterRule,
)


def test_create_naming_rule():
    """Test creating a naming rule."""
    rule = NamingRule(
        id="test_rule",
        name="Test Rule",
        category="views",
        pattern=r"^FP-\d+$",
        description="Floor plans must be FP-NNN",
    )

    assert rule.id == "test_rule"
    assert rule.name == "Test Rule"
    assert rule.pattern == r"^FP-\d+$"
    assert rule.compiled_pattern is not None


def test_naming_rule_matches():
    """Test naming rule pattern matching."""
    rule = NamingRule(
        id="floor_plan",
        name="Floor Plan",
        category="views",
        pattern=r"^FP-L\d{2}$",
        description="Floor plan naming",
    )

    assert rule.matches("FP-L01") is True
    assert rule.matches("FP-L10") is True
    assert rule.matches("FP-ROOF") is False
    assert rule.matches("SEC-A") is False


def test_create_naming_validator():
    """Test creating naming convention validator."""
    validator = NamingConventionValidator()

    assert len(validator.rules) == 0
    assert len(validator.violations) == 0


def test_add_naming_rule():
    """Test adding a naming rule."""
    validator = NamingConventionValidator()

    rule = NamingRule(
        id="sheet_rule",
        name="Sheet Naming",
        category="sheets",
        pattern=r"^A-\d{3}$",
        description="Architectural sheets",
    )

    validator.add_rule(rule)

    assert len(validator.rules) == 1
    assert "sheet_rule" in validator.rules


def test_add_view_naming_rules():
    """Test adding standard view naming rules."""
    validator = NamingConventionValidator()
    validator.add_view_naming_rules()

    assert len(validator.rules) > 0
    assert "view_floor_plan" in validator.rules
    assert "view_section" in validator.rules
    assert "view_3d" in validator.rules


def test_add_sheet_naming_rules():
    """Test adding standard sheet naming rules."""
    validator = NamingConventionValidator()
    validator.add_sheet_naming_rules()

    assert "sheet_number" in validator.rules


def test_add_family_naming_rules():
    """Test adding standard family naming rules."""
    validator = NamingConventionValidator()
    validator.add_family_naming_rules()

    assert "family_wall" in validator.rules
    assert "family_door" in validator.rules
    assert "family_window" in validator.rules


def test_validate_name_with_specific_rule():
    """Test validating a name with a specific rule."""
    validator = NamingConventionValidator()
    validator.add_view_naming_rules()

    # Valid floor plan name
    is_valid, error = validator.validate_name("FP-L01", "view", "view_floor_plan")
    assert is_valid is True
    assert error is None

    # Invalid floor plan name
    is_valid, error = validator.validate_name("FloorPlan-01", "view", "view_floor_plan")
    assert is_valid is False
    assert error is not None


def test_validate_name_any_rule():
    """Test validating a name against any matching rule."""
    validator = NamingConventionValidator()
    validator.add_view_naming_rules()

    # Valid section name
    is_valid, error = validator.validate_name("SEC-A", "view")
    assert is_valid is True

    # Invalid name
    is_valid, error = validator.validate_name("RandomName", "view")
    assert is_valid is False


def test_validate_element():
    """Test validating an element and recording violations."""
    validator = NamingConventionValidator()
    validator.add_sheet_naming_rules()

    # Valid sheet
    is_valid = validator.validate_element(
        element_id="sheet_1", element_name="A-101", element_type="sheet", rule_id="sheet_number"
    )
    assert is_valid is True
    assert len(validator.violations) == 0

    # Invalid sheet
    is_valid = validator.validate_element(
        element_id="sheet_2",
        element_name="Arch-Sheet-1",
        element_type="sheet",
        rule_id="sheet_number",
    )
    assert is_valid is False
    assert len(validator.violations) == 1


def test_get_violations():
    """Test getting all violations."""
    validator = NamingConventionValidator()
    validator.add_view_naming_rules()

    validator.validate_element("view_1", "BadName1", "view")
    validator.validate_element("view_2", "BadName2", "view")

    violations = validator.get_violations()
    assert len(violations) == 2


def test_get_violations_by_type():
    """Test getting violations by element type."""
    validator = NamingConventionValidator()
    validator.add_view_naming_rules()
    validator.add_sheet_naming_rules()

    validator.validate_element("view_1", "BadView", "view")
    validator.validate_element("sheet_1", "BadSheet", "sheet")

    view_violations = validator.get_violations_by_type("view")
    sheet_violations = validator.get_violations_by_type("sheet")

    assert len(view_violations) == 1
    assert len(sheet_violations) == 1


def test_clear_violations():
    """Test clearing violations."""
    validator = NamingConventionValidator()
    validator.add_view_naming_rules()

    validator.validate_element("view_1", "BadName", "view")
    assert len(validator.violations) > 0

    validator.clear_violations()
    assert len(validator.violations) == 0


def test_get_violation_count():
    """Test getting violation count."""
    validator = NamingConventionValidator()
    validator.add_view_naming_rules()

    for i in range(5):
        validator.validate_element(f"view_{i}", f"BadName{i}", "view")

    assert validator.get_violation_count() == 5


def test_view_naming_patterns():
    """Test various view naming patterns."""
    validator = NamingConventionValidator()
    validator.add_view_naming_rules()

    # Floor plans
    assert validator.validate_name("FP-L01", "view", "view_floor_plan")[0] is True
    assert validator.validate_name("FP-ROOF", "view", "view_floor_plan")[0] is True
    assert validator.validate_name("FP-B1", "view", "view_floor_plan")[0] is True

    # Sections
    assert validator.validate_name("SEC-A", "view", "view_section")[0] is True
    assert validator.validate_name("SEC-1", "view", "view_section")[0] is True

    # 3D Views
    assert validator.validate_name("3D-ARCH", "view", "view_3d")[0] is True
    assert validator.validate_name("3D-STRUCT", "view", "view_3d")[0] is True


def test_sheet_naming_patterns():
    """Test sheet naming patterns."""
    validator = NamingConventionValidator()
    validator.add_sheet_naming_rules()

    # Valid sheets
    assert validator.validate_name("A-101", "sheet", "sheet_number")[0] is True
    assert validator.validate_name("M-201", "sheet", "sheet_number")[0] is True
    assert validator.validate_name("E-301", "sheet", "sheet_number")[0] is True

    # Invalid sheets
    assert validator.validate_name("A101", "sheet", "sheet_number")[0] is False
    assert validator.validate_name("Arch-101", "sheet", "sheet_number")[0] is False


def test_family_naming_patterns():
    """Test family naming patterns."""
    validator = NamingConventionValidator()
    validator.add_family_naming_rules()

    # Walls
    assert validator.validate_name("W-EXT-200", "family", "family_wall")[0] is True
    assert validator.validate_name("W-INT-100", "family", "family_wall")[0] is True

    # Doors
    assert validator.validate_name("D-SINGLE-900", "family", "family_door")[0] is True
    assert validator.validate_name("D-DOUBLE-1800", "family", "family_door")[0] is True

    # Windows
    assert validator.validate_name("WN-FIXED-1200", "family", "family_window")[0] is True
    assert validator.validate_name("WN-CASEMENT-900", "family", "family_window")[0] is True


def test_create_parameter_rule():
    """Test creating a parameter rule."""
    rule = ParameterRule(
        id="mark_required",
        name="Mark Parameter",
        parameter_name="Mark",
        required=True,
    )

    assert rule.id == "mark_required"
    assert rule.parameter_name == "Mark"
    assert rule.required is True


def test_parameter_required_validation():
    """Test required parameter validation."""
    rule = ParameterRule(
        id="mark_required",
        name="Mark Required",
        parameter_name="Mark",
        required=True,
    )

    # Missing value
    is_valid, error = rule.validate_value(None)
    assert is_valid is False
    assert "missing" in error.lower()

    # Empty string
    is_valid, error = rule.validate_value("")
    assert is_valid is False

    # Valid value
    is_valid, error = rule.validate_value("W-101")
    assert is_valid is True


def test_parameter_optional_validation():
    """Test optional parameter validation."""
    rule = ParameterRule(
        id="comment_optional",
        name="Comment Optional",
        parameter_name="Comments",
        required=False,
    )

    # Missing value is okay
    is_valid, error = rule.validate_value(None)
    assert is_valid is True


def test_parameter_type_validation():
    """Test parameter type validation."""
    rule = ParameterRule(
        id="height_number",
        name="Height Number",
        parameter_name="Height",
        value_type="float",
    )

    # Valid float
    is_valid, error = rule.validate_value(3000.0)
    assert is_valid is True

    # Invalid type (string)
    is_valid, error = rule.validate_value("3000")
    assert is_valid is False


def test_parameter_allowed_values():
    """Test parameter allowed values validation."""
    rule = ParameterRule(
        id="fire_rating",
        name="Fire Rating",
        parameter_name="Fire Rating",
        allowed_values=["1HR", "2HR", "3HR", "None"],
    )

    # Valid value
    is_valid, error = rule.validate_value("2HR")
    assert is_valid is True

    # Invalid value
    is_valid, error = rule.validate_value("4HR")
    assert is_valid is False


def test_parameter_numeric_range():
    """Test parameter numeric range validation."""
    rule = ParameterRule(
        id="wall_height",
        name="Wall Height Range",
        parameter_name="Height",
        min_value=2400.0,
        max_value=6000.0,
    )

    # Valid value
    is_valid, error = rule.validate_value(3000.0)
    assert is_valid is True

    # Too low
    is_valid, error = rule.validate_value(2000.0)
    assert is_valid is False

    # Too high
    is_valid, error = rule.validate_value(7000.0)
    assert is_valid is False


def test_parameter_pattern_validation():
    """Test parameter pattern validation."""
    rule = ParameterRule(
        id="mark_pattern",
        name="Mark Pattern",
        parameter_name="Mark",
        pattern=r"^[A-Z]-\d{3}$",
    )

    # Valid pattern
    is_valid, error = rule.validate_value("A-101")
    assert is_valid is True

    # Invalid pattern
    is_valid, error = rule.validate_value("Wall-1")
    assert is_valid is False


def test_parameter_custom_validator():
    """Test parameter custom validator function."""

    def is_even(value):
        return isinstance(value, int) and value % 2 == 0

    rule = ParameterRule(
        id="even_number",
        name="Even Number",
        parameter_name="Count",
        validator_function=is_even,
    )

    # Valid (even)
    is_valid, error = rule.validate_value(4)
    assert is_valid is True

    # Invalid (odd)
    is_valid, error = rule.validate_value(3)
    assert is_valid is False
