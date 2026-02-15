"""Test reporting and CLI features (Scaffolds 8 & 9)."""

import tempfile
from pathlib import Path

from model_checker.reporting import (
    AutomatedCheckRunner,
    HTMLReportGenerator,
    IssuePrioritizer,
    ModelCheckerCLI,
    ReportExporter,
)


# SCAFFOLD 8 TESTS: Reporting

def test_html_report_generator():
    """Test HTML report generation."""
    generator = HTMLReportGenerator("Test Project")

    issues = [
        {
            "element_id": "wall_1",
            "element_type": "wall",
            "issue_type": "undersized",
            "description": "Wall too thin",
            "severity": "critical",
        }
    ]

    generator.add_issues(issues)
    html = generator.generate_html()

    assert "Test Project" in html
    assert "wall_1" in html
    assert "critical" in html


def test_html_report_save():
    """Test saving HTML report to file."""
    generator = HTMLReportGenerator("Save Test")
    generator.add_issues([{"element_id": "test", "severity": "low"}])

    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = Path(tmpdir) / "report.html"
        generator.save_html(filepath)

        assert filepath.exists()
        content = filepath.read_text()
        assert "Save Test" in content


def test_issue_prioritizer():
    """Test issue prioritization."""
    prioritizer = IssuePrioritizer()

    issues = [
        {"severity": "low", "description": "Low issue"},
        {"severity": "critical", "description": "Critical issue"},
        {"severity": "medium", "description": "Medium issue"},
        {"severity": "high", "description": "High issue"},
    ]

    prioritizer.add_issues(issues)
    prioritized = prioritizer.prioritize()

    assert prioritized[0]["severity"] == "critical"
    assert prioritized[-1]["severity"] == "low"


def test_issue_prioritizer_top_issues():
    """Test getting top priority issues."""
    prioritizer = IssuePrioritizer()

    issues = [{"severity": f"issue_{i}"} for i in range(20)]
    prioritizer.add_issues(issues)

    top10 = prioritizer.get_top_issues(limit=10)
    assert len(top10) == 10


def test_report_exporter_csv():
    """Test exporting to CSV."""
    exporter = ReportExporter()

    issues = [
        {"element_id": "1", "type": "wall", "severity": "high"},
        {"element_id": "2", "type": "beam", "severity": "medium"},
    ]

    exporter.add_issues(issues)

    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = Path(tmpdir) / "issues.csv"
        exporter.export_csv(filepath)

        assert filepath.exists()
        content = filepath.read_text()
        assert "element_id" in content
        assert "wall" in content


def test_report_exporter_json():
    """Test exporting to JSON."""
    exporter = ReportExporter()

    issues = [{"element_id": "wall_1", "severity": "critical"}]
    exporter.add_issues(issues)

    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = Path(tmpdir) / "issues.json"
        exporter.export_json(filepath)

        assert filepath.exists()
        import json

        with open(filepath) as f:
            data = json.load(f)
        assert len(data) == 1


def test_report_exporter_markdown():
    """Test exporting to Markdown."""
    exporter = ReportExporter()

    issues = [{"element_id": "beam_1", "element_type": "beam", "severity": "high"}]
    exporter.add_issues(issues)

    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = Path(tmpdir) / "issues.md"
        exporter.export_markdown(filepath)

        assert filepath.exists()
        content = filepath.read_text()
        assert "beam_1" in content
        assert "| " in content  # Markdown table


# SCAFFOLD 9 TESTS: CLI and Automation

def test_cli_run_checks():
    """Test CLI check running."""
    cli = ModelCheckerCLI()

    results = cli.run_checks("test_project.rvt", checks=["clash", "naming"])

    assert results["project"] == "test_project.rvt"
    assert "clash" in results["checks_run"]
    assert "timestamp" in results


def test_cli_format_text():
    """Test CLI text formatting."""
    cli = ModelCheckerCLI()
    cli.run_checks("test.rvt")

    output = cli.format_output(format="text")

    assert "test.rvt" in output
    assert "Total Issues" in output


def test_cli_format_json():
    """Test CLI JSON formatting."""
    cli = ModelCheckerCLI()
    cli.run_checks("test.rvt")

    output = cli.format_output(format="json")

    import json

    data = json.loads(output)
    assert data["project"] == "test.rvt"


def test_automated_check_runner():
    """Test automated check scheduling."""
    runner = AutomatedCheckRunner()

    runner.schedule_check("clash_detection", interval_hours=24.0)
    runner.schedule_check("naming_validation", on_events=["save"])

    assert len(runner.scheduled_checks) == 2


def test_scheduled_check_running():
    """Test running scheduled checks."""
    runner = AutomatedCheckRunner()

    runner.schedule_check("test_check", interval_hours=0.001)  # Very short interval

    results = runner.run_scheduled_checks()

    assert len(results) == 1
    assert results[0]["check_type"] == "test_check"


def test_event_triggered_checks():
    """Test event-triggered checks."""
    runner = AutomatedCheckRunner()

    runner.schedule_check("on_save_check", on_events=["save"])
    runner.schedule_check("on_sync_check", on_events=["sync"])

    results = runner.trigger_check_on_event("save")

    assert len(results) == 1
    assert results[0]["triggered_by"] == "save"


def test_complete_reporting_workflow():
    """Test complete reporting workflow."""
    # Generate issues
    issues = [
        {"element_id": "wall_1", "severity": "critical", "description": "Critical wall issue"},
        {"element_id": "beam_1", "severity": "high", "description": "High beam issue"},
        {"element_id": "door_1", "severity": "medium", "description": "Medium door issue"},
    ]

    # Prioritize
    prioritizer = IssuePrioritizer()
    prioritizer.add_issues(issues)
    top_issues = prioritizer.get_top_issues(limit=2)

    assert len(top_issues) == 2
    assert top_issues[0]["severity"] == "critical"

    # Generate HTML report
    html_gen = HTMLReportGenerator("Complete Workflow Test")
    html_gen.add_issues(issues)
    html = html_gen.generate_html()

    assert "wall_1" in html
    assert "Critical wall issue" in html

    # Export to multiple formats
    exporter = ReportExporter()
    exporter.add_issues(issues)

    with tempfile.TemporaryDirectory() as tmpdir:
        exporter.export_csv(Path(tmpdir) / "issues.csv")
        exporter.export_json(Path(tmpdir) / "issues.json")
        exporter.export_markdown(Path(tmpdir) / "issues.md")

        assert (Path(tmpdir) / "issues.csv").exists()
        assert (Path(tmpdir) / "issues.json").exists()
        assert (Path(tmpdir) / "issues.md").exists()
