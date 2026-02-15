"""Test the rule engine functionality."""

import pytest

from model_checker import Rule, RuleEngine, RuleSeverity


def test_create_rule():
    """Test creating a basic rule."""
    rule = Rule(
        id="test_rule_1",
        name="Test Rule",
        description="A test rule",
        category="testing",
        severity=RuleSeverity.HIGH,
        check_function=lambda x: x > 0,
    )

    assert rule.id == "test_rule_1"
    assert rule.name == "Test Rule"
    assert rule.severity == RuleSeverity.HIGH
    assert rule.category == "testing"


def test_rule_execute():
    """Test executing a rule's check function."""
    rule = Rule(
        id="positive_check",
        name="Positive Number Check",
        description="Checks if number is positive",
        category="math",
        severity=RuleSeverity.MEDIUM,
        check_function=lambda x: x > 0,
    )

    assert rule.execute(5) is True
    assert rule.execute(-3) is False
    assert rule.execute(0) is False


def test_rule_engine_initialization():
    """Test creating a rule engine."""
    engine = RuleEngine()
    assert len(engine.rules) == 0
    assert len(engine.rules_by_category) == 0


def test_register_rule():
    """Test registering a rule with the engine."""
    engine = RuleEngine()
    rule = Rule(
        id="rule_1",
        name="Rule 1",
        description="First rule",
        category="test",
        severity=RuleSeverity.LOW,
        check_function=lambda x: True,
    )

    engine.register_rule(rule)

    assert len(engine.rules) == 1
    assert "rule_1" in engine.rules
    assert engine.rules["rule_1"] == rule


def test_register_multiple_rules():
    """Test registering multiple rules."""
    engine = RuleEngine()

    rule1 = Rule(
        id="rule_1",
        name="Rule 1",
        description="First rule",
        category="geometry",
        severity=RuleSeverity.HIGH,
        check_function=lambda x: x > 0,
    )

    rule2 = Rule(
        id="rule_2",
        name="Rule 2",
        description="Second rule",
        category="naming",
        severity=RuleSeverity.MEDIUM,
        check_function=lambda x: len(x) > 5,
    )

    engine.register_rule(rule1)
    engine.register_rule(rule2)

    assert len(engine.rules) == 2
    assert "rule_1" in engine.rules
    assert "rule_2" in engine.rules


def test_get_rule():
    """Test retrieving a rule by ID."""
    engine = RuleEngine()
    rule = Rule(
        id="test_rule",
        name="Test Rule",
        description="A test",
        category="test",
        severity=RuleSeverity.INFO,
        check_function=lambda x: x,
    )

    engine.register_rule(rule)

    retrieved = engine.get_rule("test_rule")
    assert retrieved == rule

    not_found = engine.get_rule("nonexistent")
    assert not_found is None


def test_rules_by_category():
    """Test categorizing rules."""
    engine = RuleEngine()

    geometry_rule = Rule(
        id="geo_1",
        name="Geometry Rule 1",
        description="Check geometry",
        category="geometry",
        severity=RuleSeverity.HIGH,
        check_function=lambda x: True,
    )

    naming_rule = Rule(
        id="name_1",
        name="Naming Rule 1",
        description="Check naming",
        category="naming",
        severity=RuleSeverity.MEDIUM,
        check_function=lambda x: True,
    )

    engine.register_rule(geometry_rule)
    engine.register_rule(naming_rule)

    geometry_rules = engine.get_rules_by_category("geometry")
    naming_rules = engine.get_rules_by_category("naming")

    assert len(geometry_rules) == 1
    assert geometry_rules[0] == geometry_rule
    assert len(naming_rules) == 1
    assert naming_rules[0] == naming_rule


def test_execute_rule():
    """Test executing a specific rule."""
    engine = RuleEngine()

    rule = Rule(
        id="length_check",
        name="Length Check",
        description="Check if string length > 3",
        category="validation",
        severity=RuleSeverity.LOW,
        check_function=lambda x: len(x) > 3,
    )

    engine.register_rule(rule)

    assert engine.execute_rule("length_check", "hello") is True
    assert engine.execute_rule("length_check", "hi") is False


def test_execute_nonexistent_rule():
    """Test executing a rule that doesn't exist."""
    engine = RuleEngine()

    with pytest.raises(KeyError, match="Rule not found"):
        engine.execute_rule("nonexistent", "data")


def test_execute_all_rules():
    """Test executing all registered rules."""
    engine = RuleEngine()

    rule1 = Rule(
        id="rule_1",
        name="Positive Check",
        description="Check positive",
        category="math",
        severity=RuleSeverity.HIGH,
        check_function=lambda x: x > 0,
    )

    rule2 = Rule(
        id="rule_2",
        name="Even Check",
        description="Check even",
        category="math",
        severity=RuleSeverity.MEDIUM,
        check_function=lambda x: x % 2 == 0,
    )

    engine.register_rule(rule1)
    engine.register_rule(rule2)

    results = engine.execute_all_rules(4)

    assert results["rule_1"] is True  # 4 > 0
    assert results["rule_2"] is True  # 4 is even

    results2 = engine.execute_all_rules(-3)

    assert results2["rule_1"] is False  # -3 is not positive
    assert results2["rule_2"] is False  # -3 is not even


def test_execute_category_rules():
    """Test executing all rules in a category."""
    engine = RuleEngine()

    geo_rule1 = Rule(
        id="geo_1",
        name="Area Check",
        description="Check area",
        category="geometry",
        severity=RuleSeverity.HIGH,
        check_function=lambda x: x > 0,
    )

    geo_rule2 = Rule(
        id="geo_2",
        name="Volume Check",
        description="Check volume",
        category="geometry",
        severity=RuleSeverity.HIGH,
        check_function=lambda x: x < 1000,
    )

    name_rule = Rule(
        id="name_1",
        name="Name Length",
        description="Check name",
        category="naming",
        severity=RuleSeverity.LOW,
        check_function=lambda x: True,
    )

    engine.register_rule(geo_rule1)
    engine.register_rule(geo_rule2)
    engine.register_rule(name_rule)

    results = engine.execute_category_rules("geometry", 500)

    assert len(results) == 2
    assert results["geo_1"] is True  # 500 > 0
    assert results["geo_2"] is True  # 500 < 1000
    assert "name_1" not in results  # naming rule not executed


def test_complete_workflow():
    """Test a complete rule engine workflow."""
    # Create engine
    engine = RuleEngine()

    # Define rules for wall validation
    min_height_rule = Rule(
        id="wall_min_height",
        name="Minimum Wall Height",
        description="Wall height must be at least 2400mm",
        category="walls",
        severity=RuleSeverity.CRITICAL,
        check_function=lambda wall: wall.get("height", 0) >= 2400,
    )

    max_length_rule = Rule(
        id="wall_max_length",
        name="Maximum Wall Length",
        description="Wall length should not exceed 12000mm",
        category="walls",
        severity=RuleSeverity.MEDIUM,
        check_function=lambda wall: wall.get("length", 0) <= 12000,
    )

    # Register rules
    engine.register_rule(min_height_rule)
    engine.register_rule(max_length_rule)

    # Test valid wall
    valid_wall = {"height": 3000, "length": 6000}
    results = engine.execute_category_rules("walls", valid_wall)

    assert results["wall_min_height"] is True
    assert results["wall_max_length"] is True

    # Test invalid wall (too short)
    invalid_wall = {"height": 2000, "length": 6000}
    results2 = engine.execute_category_rules("walls", invalid_wall)

    assert results2["wall_min_height"] is False
    assert results2["wall_max_length"] is True

    # Test invalid wall (too long)
    invalid_wall2 = {"height": 3000, "length": 15000}
    results3 = engine.execute_category_rules("walls", invalid_wall2)

    assert results3["wall_min_height"] is True
    assert results3["wall_max_length"] is False
