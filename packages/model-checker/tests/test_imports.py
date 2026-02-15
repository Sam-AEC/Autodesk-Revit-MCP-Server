"""Test that all model checker modules can be imported successfully."""


def test_import_rule_engine():
    """Test importing rule_engine module."""
    from model_checker import rule_engine
    assert hasattr(rule_engine, 'RuleEngine')
    assert hasattr(rule_engine, 'Rule')
    assert hasattr(rule_engine, 'RuleSeverity')


def test_import_validator():
    """Test importing validator module."""
    from model_checker import validator
    assert hasattr(validator, 'Validator')
    assert hasattr(validator, 'ValidationReport')
    assert hasattr(validator, 'ValidationIssue')


def test_import_from_package():
    """Test importing from package root."""
    from model_checker import (
        Rule,
        RuleEngine,
        RuleSeverity,
        ValidationIssue,
        ValidationReport,
        Validator,
    )

    assert Rule is not None
    assert RuleEngine is not None
    assert RuleSeverity is not None
    assert ValidationIssue is not None
    assert ValidationReport is not None
    assert Validator is not None
