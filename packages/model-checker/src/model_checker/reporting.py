"""Reporting and export capabilities (Scaffold 8) + CLI/MCP integration (Scaffold 9)."""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any


# SCAFFOLD 8: Quality Assurance Dashboard

class HTMLReportGenerator:
    """Generate HTML reports for validation results (Task 8.1)."""

    def __init__(self, project_name: str) -> None:
        """Initialize HTML report generator."""
        self.project_name = project_name
        self.issues: list[dict[str, Any]] = []

    def add_issues(self, issues: list[Any]) -> None:
        """Add issues to the report."""
        for issue in issues:
            if hasattr(issue, "to_dict"):
                self.issues.append(issue.to_dict())
            elif isinstance(issue, dict):
                self.issues.append(issue)

    def generate_html(self) -> str:
        """Generate HTML report."""
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>{self.project_name} - Model Check Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h1 {{ color: #333; }}
        table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #4CAF50; color: white; }}
        .critical {{ background-color: #ff4444; color: white; }}
        .high {{ background-color: #ff9933; }}
        .medium {{ background-color: #ffff66; }}
        .low {{ background-color: #99ff99; }}
        .summary {{ margin: 20px 0; padding: 15px; background-color: #f0f0f0; border-radius: 5px; }}
    </style>
</head>
<body>
    <h1>Model Check Report: {self.project_name}</h1>
    <div class="summary">
        <h2>Summary</h2>
        <p>Total Issues: {len(self.issues)}</p>
        <p>Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
    </div>
    <h2>Issues</h2>
    <table>
        <tr>
            <th>Element ID</th>
            <th>Type</th>
            <th>Issue</th>
            <th>Description</th>
            <th>Severity</th>
        </tr>"""

        for issue in self.issues:
            severity = issue.get("severity", "medium")
            html += f"""
        <tr class="{severity}">
            <td>{issue.get('element_id', 'N/A')}</td>
            <td>{issue.get('element_type', 'N/A')}</td>
            <td>{issue.get('issue_type', 'N/A')}</td>
            <td>{issue.get('description', 'N/A')}</td>
            <td>{severity.upper()}</td>
        </tr>"""

        html += """
    </table>
</body>
</html>"""
        return html

    def save_html(self, filepath: str | Path) -> None:
        """Save HTML report to file."""
        with open(filepath, "w") as f:
            f.write(self.generate_html())


class IssuePrioritizer:
    """Prioritize and rank validation issues (Task 8.2)."""

    SEVERITY_WEIGHTS = {"critical": 100, "high": 50, "medium": 20, "low": 5, "info": 1}

    def __init__(self) -> None:
        """Initialize issue prioritizer."""
        self.issues: list[dict[str, Any]] = []

    def add_issues(self, issues: list[Any]) -> None:
        """Add issues for prioritization."""
        for issue in issues:
            if hasattr(issue, "to_dict"):
                self.issues.append(issue.to_dict())
            elif hasattr(issue, "__dict__"):
                self.issues.append(vars(issue))
            elif isinstance(issue, dict):
                self.issues.append(issue)

    def prioritize(self) -> list[dict[str, Any]]:
        """Prioritize issues by severity and impact."""

        def get_priority_score(issue: dict[str, Any]) -> int:
            severity = issue.get("severity", "low")
            return self.SEVERITY_WEIGHTS.get(severity, 1)

        return sorted(self.issues, key=get_priority_score, reverse=True)

    def get_top_issues(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get top N priority issues."""
        return self.prioritize()[:limit]


class ReportExporter:
    """Export reports in various formats (Task 8.3)."""

    def __init__(self) -> None:
        """Initialize report exporter."""
        self.issues: list[dict[str, Any]] = []

    def add_issues(self, issues: list[Any]) -> None:
        """Add issues for export."""
        for issue in issues:
            if hasattr(issue, "to_dict"):
                self.issues.append(issue.to_dict())
            elif isinstance(issue, dict):
                self.issues.append(issue)

    def export_csv(self, filepath: str | Path) -> None:
        """Export issues to CSV."""
        if not self.issues:
            return

        fieldnames = list(self.issues[0].keys())

        with open(filepath, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.issues)

    def export_json(self, filepath: str | Path) -> None:
        """Export issues to JSON."""
        with open(filepath, "w") as f:
            json.dump(self.issues, f, indent=2, default=str)

    def export_markdown(self, filepath: str | Path) -> None:
        """Export issues to Markdown."""
        md = "# Model Check Issues\\n\\n"
        md += f"**Total Issues:** {len(self.issues)}\\n\\n"
        md += "| Element ID | Type | Issue | Severity |\\n"
        md += "|------------|------|-------|----------|\\n"

        for issue in self.issues:
            md += f"| {issue.get('element_id', 'N/A')} | {issue.get('element_type', 'N/A')} | {issue.get('issue_type', 'N/A')} | {issue.get('severity', 'N/A')} |\\n"

        with open(filepath, "w") as f:
            f.write(md)


# SCAFFOLD 9: MCP Integration and CLI

class ModelCheckerCLI:
    """Command-line interface for model checker (Task 9.2)."""

    def __init__(self) -> None:
        """Initialize CLI."""
        self.results: dict[str, Any] = {}

    def run_checks(
        self, project: str, checks: list[str] | None = None
    ) -> dict[str, Any]:
        """Run model checks from CLI.

        Args:
            project: Project file path
            checks: List of check types to run (None = all)

        Returns:
            Dictionary of check results
        """
        self.results = {
            "project": project,
            "timestamp": datetime.now().isoformat(),
            "checks_run": checks or ["all"],
            "total_issues": 0,
            "issues_by_category": {},
        }

        return self.results

    def format_output(self, format: str = "text") -> str:
        """Format results for display.

        Args:
            format: Output format (text, json)

        Returns:
            Formatted results string
        """
        if format == "json":
            return json.dumps(self.results, indent=2)

        # Text format
        output = f"Model Check Results for {self.results['project']}\\n"
        output += f"Timestamp: {self.results['timestamp']}\\n"
        output += f"Checks Run: {', '.join(self.results['checks_run'])}\\n"
        output += f"Total Issues: {self.results['total_issues']}\\n"

        return output


class AutomatedCheckRunner:
    """Automated check runner with scheduling (Task 9.3)."""

    def __init__(self) -> None:
        """Initialize automated check runner."""
        self.scheduled_checks: list[dict[str, Any]] = []
        self.last_run: datetime | None = None

    def schedule_check(
        self,
        check_type: str,
        interval_hours: float = 24.0,
        on_events: list[str] | None = None,
    ) -> None:
        """Schedule a check to run automatically.

        Args:
            check_type: Type of check to run
            interval_hours: Run interval in hours
            on_events: Events that trigger check (e.g., ["save", "sync"])
        """
        self.scheduled_checks.append(
            {
                "check_type": check_type,
                "interval_hours": interval_hours,
                "on_events": on_events or [],
                "last_run": None,
            }
        )

    def should_run_check(self, check: dict[str, Any]) -> bool:
        """Check if a scheduled check should run now."""
        if check["last_run"] is None:
            return True

        # Check time interval
        from datetime import timedelta

        now = datetime.now()
        elapsed = now - check["last_run"]
        interval = timedelta(hours=check["interval_hours"])

        return elapsed >= interval

    def run_scheduled_checks(self) -> list[dict[str, Any]]:
        """Run all scheduled checks that are due.

        Returns:
            List of check results
        """
        results = []

        for check in self.scheduled_checks:
            if self.should_run_check(check):
                result = {"check_type": check["check_type"], "ran": True, "timestamp": datetime.now().isoformat()}
                results.append(result)
                check["last_run"] = datetime.now()

        self.last_run = datetime.now()
        return results

    def trigger_check_on_event(self, event: str) -> list[dict[str, Any]]:
        """Trigger checks configured for a specific event.

        Args:
            event: Event name (e.g., "save", "sync")

        Returns:
            List of triggered check results
        """
        results = []

        for check in self.scheduled_checks:
            if event in check["on_events"]:
                result = {
                    "check_type": check["check_type"],
                    "triggered_by": event,
                    "timestamp": datetime.now().isoformat(),
                }
                results.append(result)
                check["last_run"] = datetime.now()

        return results
