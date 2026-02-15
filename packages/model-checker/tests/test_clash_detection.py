"""Test clash detection functionality."""

import pytest

from model_checker.clash_detection import BoundingBox, ClashDetector, ClashResult


def test_create_bounding_box():
    """Test creating a bounding box."""
    bbox = BoundingBox(
        min_x=0.0, min_y=0.0, min_z=0.0, max_x=1000.0, max_y=1000.0, max_z=3000.0
    )

    assert bbox.min_x == 0.0
    assert bbox.max_z == 3000.0


def test_bounding_box_from_dict():
    """Test creating bounding box from dictionary."""
    data = {
        "min": {"x": 100.0, "y": 200.0, "z": 0.0},
        "max": {"x": 500.0, "y": 600.0, "z": 3000.0},
    }

    bbox = BoundingBox.from_dict(data)

    assert bbox.min_x == 100.0
    assert bbox.min_y == 200.0
    assert bbox.min_z == 0.0
    assert bbox.max_x == 500.0
    assert bbox.max_y == 600.0
    assert bbox.max_z == 3000.0


def test_bounding_box_intersects():
    """Test bounding box intersection detection."""
    bbox1 = BoundingBox(
        min_x=0.0, min_y=0.0, min_z=0.0, max_x=1000.0, max_y=1000.0, max_z=3000.0
    )

    # Overlapping box
    bbox2 = BoundingBox(
        min_x=500.0, min_y=500.0, min_z=1000.0, max_x=1500.0, max_y=1500.0, max_z=4000.0
    )

    assert bbox1.intersects(bbox2) is True
    assert bbox2.intersects(bbox1) is True


def test_bounding_box_no_intersection():
    """Test bounding boxes that don't intersect."""
    bbox1 = BoundingBox(
        min_x=0.0, min_y=0.0, min_z=0.0, max_x=1000.0, max_y=1000.0, max_z=3000.0
    )

    # Separated box
    bbox2 = BoundingBox(
        min_x=2000.0, min_y=2000.0, min_z=0.0, max_x=3000.0, max_y=3000.0, max_z=3000.0
    )

    assert bbox1.intersects(bbox2) is False
    assert bbox2.intersects(bbox1) is False


def test_bounding_box_volume():
    """Test bounding box volume calculation."""
    bbox = BoundingBox(
        min_x=0.0, min_y=0.0, min_z=0.0, max_x=1000.0, max_y=2000.0, max_z=3000.0
    )

    volume = bbox.get_volume()
    assert volume == 1000.0 * 2000.0 * 3000.0


def test_intersection_volume():
    """Test intersection volume calculation."""
    bbox1 = BoundingBox(
        min_x=0.0, min_y=0.0, min_z=0.0, max_x=1000.0, max_y=1000.0, max_z=1000.0
    )

    bbox2 = BoundingBox(
        min_x=500.0, min_y=500.0, min_z=500.0, max_x=1500.0, max_y=1500.0, max_z=1500.0
    )

    # Overlap is 500x500x500
    volume = bbox1.get_intersection_volume(bbox2)
    assert volume == 500.0 * 500.0 * 500.0


def test_no_intersection_volume():
    """Test intersection volume when boxes don't intersect."""
    bbox1 = BoundingBox(
        min_x=0.0, min_y=0.0, min_z=0.0, max_x=1000.0, max_y=1000.0, max_z=1000.0
    )

    bbox2 = BoundingBox(
        min_x=2000.0, min_y=2000.0, min_z=2000.0, max_x=3000.0, max_y=3000.0, max_z=3000.0
    )

    volume = bbox1.get_intersection_volume(bbox2)
    assert volume == 0.0


def test_bounding_box_center():
    """Test getting center point of bounding box."""
    bbox = BoundingBox(
        min_x=0.0, min_y=0.0, min_z=0.0, max_x=1000.0, max_y=2000.0, max_z=3000.0
    )

    center = bbox.get_center()
    assert center == (500.0, 1000.0, 1500.0)


def test_create_clash_result():
    """Test creating a clash result."""
    clash = ClashResult(
        element_id_1="wall_1",
        element_id_2="beam_1",
        clash_type="bounding_box",
        intersection_volume=125000.0,
        location={"x": 500.0, "y": 500.0, "z": 1500.0},
        severity="high",
    )

    assert clash.element_id_1 == "wall_1"
    assert clash.element_id_2 == "beam_1"
    assert clash.clash_type == "bounding_box"
    assert clash.severity == "high"


def test_clash_result_to_dict():
    """Test converting clash result to dictionary."""
    clash = ClashResult(
        element_id_1=123,
        element_id_2=456,
        clash_type="precise",
        intersection_volume=50000.0,
        location={"x": 100.0, "y": 200.0, "z": 300.0},
        severity="medium",
    )

    data = clash.to_dict()

    assert data["element_id_1"] == 123
    assert data["element_id_2"] == 456
    assert data["clash_type"] == "precise"
    assert data["intersection_volume"] == 50000.0
    assert data["location"] == {"x": 100.0, "y": 200.0, "z": 300.0}
    assert data["severity"] == "medium"


def test_create_clash_detector():
    """Test creating a clash detector."""
    detector = ClashDetector()
    assert detector.tolerance == 0.0
    assert len(detector.clashes) == 0


def test_detect_clash():
    """Test detecting a clash between two bounding boxes."""
    detector = ClashDetector()

    bbox1 = BoundingBox(
        min_x=0.0, min_y=0.0, min_z=0.0, max_x=1000.0, max_y=1000.0, max_z=3000.0
    )

    bbox2 = BoundingBox(
        min_x=500.0, min_y=500.0, min_z=1000.0, max_x=1500.0, max_y=1500.0, max_z=4000.0
    )

    clash = detector.check_bounding_box_clash("elem_1", bbox1, "elem_2", bbox2)

    assert clash is not None
    assert clash.element_id_1 == "elem_1"
    assert clash.element_id_2 == "elem_2"
    assert clash.clash_type == "bounding_box"
    assert clash.intersection_volume > 0
    assert clash.location is not None


def test_no_clash_detected():
    """Test when no clash is detected."""
    detector = ClashDetector()

    bbox1 = BoundingBox(
        min_x=0.0, min_y=0.0, min_z=0.0, max_x=1000.0, max_y=1000.0, max_z=3000.0
    )

    bbox2 = BoundingBox(
        min_x=2000.0, min_y=2000.0, min_z=0.0, max_x=3000.0, max_y=3000.0, max_z=3000.0
    )

    clash = detector.check_bounding_box_clash("elem_1", bbox1, "elem_2", bbox2)

    assert clash is None
    assert len(detector.clashes) == 0


def test_check_multiple_elements():
    """Test checking clashes between multiple elements."""
    detector = ClashDetector()

    elements = [
        {
            "id": "wall_1",
            "bounding_box": {
                "min": {"x": 0.0, "y": 0.0, "z": 0.0},
                "max": {"x": 1000.0, "y": 1000.0, "z": 3000.0},
            },
        },
        {
            "id": "beam_1",
            "bounding_box": {
                "min": {"x": 500.0, "y": 500.0, "z": 1000.0},
                "max": {"x": 1500.0, "y": 1500.0, "z": 4000.0},
            },
        },
        {
            "id": "column_1",
            "bounding_box": {
                "min": {"x": 5000.0, "y": 5000.0, "z": 0.0},
                "max": {"x": 5500.0, "y": 5500.0, "z": 3000.0},
            },
        },
    ]

    clashes = detector.check_multiple_elements(elements)

    # Should find 1 clash (wall_1 and beam_1)
    assert len(clashes) == 1
    assert clashes[0].element_id_1 == "wall_1"
    assert clashes[0].element_id_2 == "beam_1"


def test_severity_calculation():
    """Test clash severity calculation."""
    detector = ClashDetector()

    # Critical: > 1 m³ = 1,000,000,000 mm³
    bbox1 = BoundingBox(
        min_x=0.0, min_y=0.0, min_z=0.0, max_x=2000.0, max_y=2000.0, max_z=2000.0
    )
    bbox2 = BoundingBox(
        min_x=1000.0, min_y=1000.0, min_z=1000.0, max_x=3000.0, max_y=3000.0, max_z=3000.0
    )

    clash = detector.check_bounding_box_clash("e1", bbox1, "e2", bbox2)
    assert clash.severity == "critical"


def test_get_clashes_by_severity():
    """Test filtering clashes by severity."""
    detector = ClashDetector()

    # Create clashes with different severities
    bbox_critical_1 = BoundingBox(
        min_x=0.0, min_y=0.0, min_z=0.0, max_x=2000.0, max_y=2000.0, max_z=2000.0
    )
    bbox_critical_2 = BoundingBox(
        min_x=1000.0, min_y=1000.0, min_z=1000.0, max_x=3000.0, max_y=3000.0, max_z=3000.0
    )

    bbox_low_1 = BoundingBox(
        min_x=0.0, min_y=0.0, min_z=0.0, max_x=100.0, max_y=100.0, max_z=100.0
    )
    bbox_low_2 = BoundingBox(
        min_x=50.0, min_y=50.0, min_z=50.0, max_x=150.0, max_y=150.0, max_z=150.0
    )

    detector.check_bounding_box_clash("e1", bbox_critical_1, "e2", bbox_critical_2)
    detector.check_bounding_box_clash("e3", bbox_low_1, "e4", bbox_low_2)

    critical = detector.get_clashes_by_severity("critical")
    low = detector.get_clashes_by_severity("low")

    assert len(critical) == 1
    assert len(low) == 1


def test_get_critical_clashes():
    """Test getting only critical clashes."""
    detector = ClashDetector()

    bbox1 = BoundingBox(
        min_x=0.0, min_y=0.0, min_z=0.0, max_x=2000.0, max_y=2000.0, max_z=2000.0
    )
    bbox2 = BoundingBox(
        min_x=1000.0, min_y=1000.0, min_z=1000.0, max_x=3000.0, max_y=3000.0, max_z=3000.0
    )

    detector.check_bounding_box_clash("e1", bbox1, "e2", bbox2)

    critical = detector.get_critical_clashes()
    assert len(critical) == 1
    assert critical[0].severity == "critical"


def test_get_total_clashes():
    """Test getting total clash count."""
    detector = ClashDetector()

    elements = [
        {
            "id": f"elem_{i}",
            "bounding_box": {
                "min": {"x": float(i * 500), "y": 0.0, "z": 0.0},
                "max": {"x": float(i * 500 + 1000), "y": 1000.0, "z": 3000.0},
            },
        }
        for i in range(5)
    ]

    detector.check_multiple_elements(elements)
    total = detector.get_total_clashes()

    # Elements 0-1, 1-2, 2-3, 3-4 overlap (4 clashes)
    assert total == 4


def test_clear_clashes():
    """Test clearing stored clashes."""
    detector = ClashDetector()

    bbox1 = BoundingBox(
        min_x=0.0, min_y=0.0, min_z=0.0, max_x=1000.0, max_y=1000.0, max_z=3000.0
    )
    bbox2 = BoundingBox(
        min_x=500.0, min_y=500.0, min_z=1000.0, max_x=1500.0, max_y=1500.0, max_z=4000.0
    )

    detector.check_bounding_box_clash("e1", bbox1, "e2", bbox2)
    assert len(detector.clashes) == 1

    detector.clear_clashes()
    assert len(detector.clashes) == 0
