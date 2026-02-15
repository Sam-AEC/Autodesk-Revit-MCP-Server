"""Test clash visualization report generation."""

import json
import tempfile
from pathlib import Path

import pytest

from model_checker.clash_detection import ClashResult
from model_checker.clash_report import ClashReportBuilder, ClashVisualizationReport


def test_create_clash_report():
    """Test creating a clash visualization report."""
    report = ClashVisualizationReport(project_name="Test Project")

    assert report.project_name == "Test Project"
    assert report.get_clash_count() == 0
    assert len(report.clashes) == 0


def test_add_clash_to_report():
    """Test adding a clash to the report."""
    report = ClashVisualizationReport(project_name="Test")

    clash = ClashResult(
        element_id_1="wall_1",
        element_id_2="beam_1",
        clash_type="bounding_box",
        intersection_volume=125000.0,
        location={"x": 500.0, "y": 500.0, "z": 1500.0},
        severity="high",
    )

    report.add_clash(clash)

    assert report.get_clash_count() == 1
    assert len(report.clashes) == 1


def test_clash_matrix():
    """Test clash matrix generation."""
    report = ClashVisualizationReport(project_name="Test")

    clash1 = ClashResult(
        element_id_1="wall_1",
        element_id_2="beam_1",
        clash_type="bounding_box",
        severity="high",
    )

    clash2 = ClashResult(
        element_id_1="wall_1",
        element_id_2="column_1",
        clash_type="bounding_box",
        severity="medium",
    )

    report.add_clash(clash1)
    report.add_clash(clash2)

    assert "wall_1" in report.clash_matrix
    assert "beam_1" in report.clash_matrix
    assert "column_1" in report.clash_matrix

    assert "beam_1" in report.clash_matrix["wall_1"]
    assert "column_1" in report.clash_matrix["wall_1"]
    assert "wall_1" in report.clash_matrix["beam_1"]


def test_get_clashes_by_severity():
    """Test filtering clashes by severity."""
    report = ClashVisualizationReport(project_name="Test")

    critical_clash = ClashResult(
        element_id_1="e1",
        element_id_2="e2",
        clash_type="precise",
        severity="critical",
    )

    high_clash = ClashResult(
        element_id_1="e3",
        element_id_2="e4",
        clash_type="precise",
        severity="high",
    )

    low_clash = ClashResult(
        element_id_1="e5",
        element_id_2="e6",
        clash_type="bounding_box",
        severity="low",
    )

    report.add_clash(critical_clash)
    report.add_clash(high_clash)
    report.add_clash(low_clash)

    critical = report.get_clashes_by_severity("critical")
    high = report.get_clashes_by_severity("high")
    low = report.get_clashes_by_severity("low")

    assert len(critical) == 1
    assert len(high) == 1
    assert len(low) == 1


def test_get_clash_counts():
    """Test getting clash counts by severity."""
    report = ClashVisualizationReport(project_name="Test")

    for i in range(3):
        report.add_clash(
            ClashResult(
                element_id_1=f"c{i}_1",
                element_id_2=f"c{i}_2",
                clash_type="precise",
                severity="critical",
            )
        )

    for i in range(2):
        report.add_clash(
            ClashResult(
                element_id_1=f"h{i}_1",
                element_id_2=f"h{i}_2",
                clash_type="bounding_box",
                severity="high",
            )
        )

    assert report.get_clash_count() == 5
    assert report.get_critical_count() == 3
    assert report.get_high_count() == 2


def test_get_elements_with_clashes():
    """Test getting list of elements involved in clashes."""
    report = ClashVisualizationReport(project_name="Test")

    report.add_clash(
        ClashResult(
            element_id_1="wall_1",
            element_id_2="beam_1",
            clash_type="precise",
            severity="high",
        )
    )

    report.add_clash(
        ClashResult(
            element_id_1="wall_1",
            element_id_2="column_1",
            clash_type="precise",
            severity="medium",
        )
    )

    elements = report.get_elements_with_clashes()

    assert len(elements) == 3
    assert "wall_1" in elements
    assert "beam_1" in elements
    assert "column_1" in elements


def test_get_most_problematic_elements():
    """Test getting elements with most clashes."""
    report = ClashVisualizationReport(project_name="Test")

    # wall_1 clashes with 3 elements
    for i in range(3):
        report.add_clash(
            ClashResult(
                element_id_1="wall_1",
                element_id_2=f"elem_{i}",
                clash_type="precise",
                severity="high",
            )
        )

    # beam_1 clashes with 1 element
    report.add_clash(
        ClashResult(
            element_id_1="beam_1",
            element_id_2="elem_5",
            clash_type="bounding_box",
            severity="low",
        )
    )

    problematic = report.get_most_problematic_elements(limit=3)

    assert len(problematic) <= 3
    assert problematic[0][0] == "wall_1"
    assert problematic[0][1] == 3


def test_report_to_dict():
    """Test converting report to dictionary."""
    report = ClashVisualizationReport(project_name="Sample Project")
    report.total_elements_checked = 100

    clash = ClashResult(
        element_id_1="wall_1",
        element_id_2="beam_1",
        clash_type="bounding_box",
        intersection_volume=50000.0,
        location={"x": 100.0, "y": 200.0, "z": 300.0},
        severity="medium",
    )

    report.add_clash(clash)

    data = report.to_dict()

    assert data["project_name"] == "Sample Project"
    assert data["summary"]["total_clashes"] == 1
    assert data["summary"]["elements_checked"] == 100
    assert len(data["clashes"]) == 1
    assert data["clashes"][0]["element_id_1"] == "wall_1"
    assert data["clashes"][0]["intersection_volume"] == 50000.0


def test_report_to_json():
    """Test converting report to JSON string."""
    report = ClashVisualizationReport(project_name="Test Project")

    clash = ClashResult(
        element_id_1=123,
        element_id_2=456,
        clash_type="precise",
        severity="high",
    )

    report.add_clash(clash)

    json_str = report.to_json()

    # Verify it's valid JSON
    data = json.loads(json_str)
    assert data["project_name"] == "Test Project"
    assert len(data["clashes"]) == 1


def test_save_to_file():
    """Test saving report to JSON file."""
    report = ClashVisualizationReport(project_name="Test Project")
    report.total_elements_checked = 50

    clash = ClashResult(
        element_id_1="wall_1",
        element_id_2="beam_1",
        clash_type="bounding_box",
        severity="critical",
    )

    report.add_clash(clash)

    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = Path(tmpdir) / "clash_report.json"
        report.save_to_file(str(filepath))

        assert filepath.exists()

        # Read and verify
        with open(filepath) as f:
            data = json.load(f)

        assert data["project_name"] == "Test Project"
        assert data["summary"]["total_clashes"] == 1


def test_get_clash_pairs():
    """Test getting clash pairs."""
    report = ClashVisualizationReport(project_name="Test")

    report.add_clash(
        ClashResult(
            element_id_1="wall_1",
            element_id_2="beam_1",
            clash_type="precise",
            severity="high",
        )
    )

    report.add_clash(
        ClashResult(
            element_id_1="column_1",
            element_id_2="slab_1",
            clash_type="bounding_box",
            severity="medium",
        )
    )

    pairs = report.get_clash_pairs()

    assert len(pairs) == 2
    assert ("wall_1", "beam_1") in pairs
    assert ("column_1", "slab_1") in pairs


def test_get_clash_locations():
    """Test getting clash locations."""
    report = ClashVisualizationReport(project_name="Test")

    report.add_clash(
        ClashResult(
            element_id_1="e1",
            element_id_2="e2",
            clash_type="precise",
            severity="high",
            location={"x": 100.0, "y": 200.0, "z": 300.0},
        )
    )

    report.add_clash(
        ClashResult(
            element_id_1="e3",
            element_id_2="e4",
            clash_type="bounding_box",
            severity="medium",
            location={"x": 500.0, "y": 600.0, "z": 700.0},
        )
    )

    locations = report.get_clash_locations()

    assert len(locations) == 2
    assert {"x": 100.0, "y": 200.0, "z": 300.0} in locations
    assert {"x": 500.0, "y": 600.0, "z": 700.0} in locations


def test_generate_visualization_data():
    """Test generating visualization data."""
    report = ClashVisualizationReport(project_name="Test")

    report.add_clash(
        ClashResult(
            element_id_1="wall_1",
            element_id_2="beam_1",
            clash_type="precise",
            severity="critical",
            intersection_volume=1000000.0,
            location={"x": 100.0, "y": 200.0, "z": 300.0},
        )
    )

    viz_data = report.generate_visualization_data()

    assert "nodes" in viz_data
    assert "edges" in viz_data
    assert len(viz_data["nodes"]) == 2
    assert len(viz_data["edges"]) == 1

    # Check node structure
    node_ids = [node["id"] for node in viz_data["nodes"]]
    assert "wall_1" in node_ids
    assert "beam_1" in node_ids

    # Check edge structure
    edge = viz_data["edges"][0]
    assert edge["source"] == "wall_1"
    assert edge["target"] == "beam_1"
    assert edge["severity"] == "critical"
    assert edge["volume"] == 1000000.0


def test_clash_report_builder():
    """Test using ClashReportBuilder."""
    builder = ClashReportBuilder("Office Building")

    clashes = [
        ClashResult(
            element_id_1="wall_1",
            element_id_2="beam_1",
            clash_type="precise",
            severity="high",
        ),
        ClashResult(
            element_id_1="wall_2",
            element_id_2="column_1",
            clash_type="bounding_box",
            severity="medium",
        ),
    ]

    report = builder.add_clashes(clashes).set_elements_checked(150).build()

    assert report.project_name == "Office Building"
    assert report.get_clash_count() == 2
    assert report.total_elements_checked == 150


def test_builder_method_chaining():
    """Test builder method chaining."""
    clashes = [
        ClashResult(
            element_id_1="e1",
            element_id_2="e2",
            clash_type="precise",
            severity="critical",
        )
    ]

    report = (
        ClashReportBuilder("Test")
        .add_clashes(clashes)
        .set_elements_checked(50)
        .build()
    )

    assert report.get_clash_count() == 1
    assert report.total_elements_checked == 50


def test_complete_workflow():
    """Test complete clash report workflow."""
    # Create report
    builder = ClashReportBuilder("Commercial Tower Project")

    # Add multiple clashes
    clashes = [
        ClashResult(
            element_id_1="wall_ext_1",
            element_id_2="beam_str_5",
            clash_type="precise_geometry",
            intersection_volume=500000000.0,
            location={"x": 5000.0, "y": 3000.0, "z": 12000.0},
            severity="critical",
        ),
        ClashResult(
            element_id_1="wall_ext_1",
            element_id_2="duct_mep_3",
            clash_type="bounding_box",
            intersection_volume=50000000.0,
            location={"x": 5200.0, "y": 3100.0, "z": 11500.0},
            severity="high",
        ),
        ClashResult(
            element_id_1="column_str_2",
            element_id_2="pipe_mep_7",
            clash_type="precise_geometry",
            intersection_volume=5000000.0,
            location={"x": 2000.0, "y": 2000.0, "z": 8000.0},
            severity="medium",
        ),
    ]

    report = builder.add_clashes(clashes).set_elements_checked(250).build()

    # Verify summary
    assert report.get_clash_count() == 3
    assert report.get_critical_count() == 1
    assert report.get_high_count() == 1

    # Check most problematic element
    problematic = report.get_most_problematic_elements(limit=1)
    assert problematic[0][0] == "wall_ext_1"  # Has 2 clashes
    assert problematic[0][1] == 2

    # Generate and verify JSON
    data = report.to_dict()
    assert data["summary"]["total_clashes"] == 3
    assert data["summary"]["critical_clashes"] == 1
    assert len(data["most_problematic_elements"]) > 0

    # Generate visualization data
    viz_data = report.generate_visualization_data()
    assert len(viz_data["nodes"]) == 5  # 5 unique elements
    assert len(viz_data["edges"]) == 3  # 3 clashes
