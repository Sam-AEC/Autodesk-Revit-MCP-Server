"""Rule engine for model checking."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable


class RuleSeverity(Enum):
    """Severity levels for validation issues."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class Rule:
    """A validation rule that can be executed against model elements."""

    id: str
    name: str
    description: str
    category: str
    severity: RuleSeverity
    check_function: Callable[[Any], bool]

    def execute(self, element: Any) -> bool:
        """Execute the rule's check function against an element.

        Args:
            element: The element to check

        Returns:
            True if the element passes the rule, False otherwise
        """
        return self.check_function(element)


class RuleEngine:
    """Engine for registering and executing validation rules."""

    def __init__(self) -> None:
        """Initialize the rule engine."""
        self.rules: dict[str, Rule] = {}
        self.rules_by_category: dict[str, list[Rule]] = {}

    def register_rule(self, rule: Rule) -> None:
        """Register a new validation rule.

        Args:
            rule: The rule to register
        """
        self.rules[rule.id] = rule

        if rule.category not in self.rules_by_category:
            self.rules_by_category[rule.category] = []
        self.rules_by_category[rule.category].append(rule)

    def get_rule(self, rule_id: str) -> Rule | None:
        """Get a rule by its ID.

        Args:
            rule_id: The ID of the rule to retrieve

        Returns:
            The rule if found, None otherwise
        """
        return self.rules.get(rule_id)

    def get_rules_by_category(self, category: str) -> list[Rule]:
        """Get all rules in a specific category.

        Args:
            category: The category to filter by

        Returns:
            List of rules in the category
        """
        return self.rules_by_category.get(category, [])

    def execute_rule(self, rule_id: str, element: Any) -> bool:
        """Execute a specific rule against an element.

        Args:
            rule_id: The ID of the rule to execute
            element: The element to check

        Returns:
            True if the element passes the rule, False otherwise

        Raises:
            KeyError: If the rule_id is not found
        """
        rule = self.rules.get(rule_id)
        if rule is None:
            raise KeyError(f"Rule not found: {rule_id}")
        return rule.execute(element)

    def execute_all_rules(self, element: Any) -> dict[str, bool]:
        """Execute all registered rules against an element.

        Args:
            element: The element to check

        Returns:
            Dictionary mapping rule IDs to pass/fail results
        """
        return {rule_id: rule.execute(element) for rule_id, rule in self.rules.items()}

    def execute_category_rules(self, category: str, element: Any) -> dict[str, bool]:
        """Execute all rules in a category against an element.

        Args:
            category: The category of rules to execute
            element: The element to check

        Returns:
            Dictionary mapping rule IDs to pass/fail results
        """
        rules = self.get_rules_by_category(category)
        return {rule.id: rule.execute(element) for rule in rules}
