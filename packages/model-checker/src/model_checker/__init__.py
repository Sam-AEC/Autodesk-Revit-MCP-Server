"""
Model Checker for Revit - Better than Solibri

Comprehensive BIM model checking and quality assurance system.
"""

__version__ = "0.1.0"

from .rule_engine import Rule, RuleEngine, RuleSeverity
from .validator import ValidationIssue, ValidationReport, Validator

__all__ = [
    "Rule",
    "RuleEngine",
    "RuleSeverity",
    "ValidationIssue",
    "ValidationReport",
    "Validator",
]
