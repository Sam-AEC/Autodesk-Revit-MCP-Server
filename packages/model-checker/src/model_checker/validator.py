"""Validator for executing checks and generating reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .rule_engine import Rule, RuleSeverity


@dataclass
class ValidationIssue:
    """A validation issue found during model checking."""

    rule_id: str
    rule_name: str
    severity: RuleSeverity
    category: str
    element_id: str | int | None
    description: str
    location: dict[str, Any] | None = None
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert the issue to a dictionary.

        Returns:
            Dictionary representation of the issue
        """
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "severity": self.severity.value,
            "category": self.category,
            "element_id": self.element_id,
            "description": self.description,
            "location": self.location,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class ValidationReport:
    """Report containing all validation issues found."""

    project_name: str
    timestamp: datetime = field(default_factory=datetime.now)
    issues: list[ValidationIssue] = field(default_factory=list)
    total_elements_checked: int = 0
    rules_executed: int = 0

    def add_issue(self, issue: ValidationIssue) -> None:
        """Add a validation issue to the report.

        Args:
            issue: The issue to add
        """
        self.issues.append(issue)

    def get_issues_by_severity(self, severity: RuleSeverity) -> list[ValidationIssue]:
        """Get all issues of a specific severity.

        Args:
            severity: The severity level to filter by

        Returns:
            List of issues with the specified severity
        """
        return [issue for issue in self.issues if issue.severity == severity]

    def get_issues_by_category(self, category: str) -> list[ValidationIssue]:
        """Get all issues in a specific category.

        Args:
            category: The category to filter by

        Returns:
            List of issues in the specified category
        """
        return [issue for issue in self.issues if issue.category == category]

    def get_critical_count(self) -> int:
        """Get the count of critical issues.

        Returns:
            Number of critical issues
        """
        return len(self.get_issues_by_severity(RuleSeverity.CRITICAL))

    def get_high_count(self) -> int:
        """Get the count of high severity issues.

        Returns:
            Number of high severity issues
        """
        return len(self.get_issues_by_severity(RuleSeverity.HIGH))

    def get_total_issues(self) -> int:
        """Get the total count of all issues.

        Returns:
            Total number of issues
        """
        return len(self.issues)

    def to_dict(self) -> dict[str, Any]:
        """Convert the report to a dictionary.

        Returns:
            Dictionary representation of the report
        """
        return {
            "project_name": self.project_name,
            "timestamp": self.timestamp.isoformat(),
            "total_elements_checked": self.total_elements_checked,
            "rules_executed": self.rules_executed,
            "total_issues": self.get_total_issues(),
            "critical_issues": self.get_critical_count(),
            "high_issues": self.get_high_count(),
            "issues": [issue.to_dict() for issue in self.issues],
        }


class Validator:
    """Main validator class for executing checks and generating reports."""

    def __init__(self, rule_engine: Any) -> None:
        """Initialize the validator with a rule engine.

        Args:
            rule_engine: The rule engine to use for validation
        """
        self.rule_engine = rule_engine
        self.current_report: ValidationReport | None = None

    def create_report(self, project_name: str) -> ValidationReport:
        """Create a new validation report.

        Args:
            project_name: The name of the project being validated

        Returns:
            A new validation report
        """
        self.current_report = ValidationReport(project_name=project_name)
        return self.current_report

    def validate_element(
        self,
        element: Any,
        element_id: str | int,
        rules: list[Rule],
    ) -> list[ValidationIssue]:
        """Validate an element against a list of rules.

        Args:
            element: The element to validate
            element_id: The ID of the element
            rules: List of rules to execute

        Returns:
            List of validation issues found
        """
        issues = []
        for rule in rules:
            passed = rule.execute(element)
            if not passed:
                issue = ValidationIssue(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    severity=rule.severity,
                    category=rule.category,
                    element_id=element_id,
                    description=f"{rule.name}: {rule.description}",
                )
                issues.append(issue)
                if self.current_report:
                    self.current_report.add_issue(issue)
        return issues
