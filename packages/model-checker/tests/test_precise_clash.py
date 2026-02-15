"""Test precise geometry clash detection."""

import pytest

from model_checker.clash_detection import ClashDetector, PreciseGeometry


def test_create_precise_geometry():
    """Test creating precise geometry from data."""
    geometry_data = {
        "vertices": [
            {"x": 0.0, "y": 0.0, "z": 0.0},
            {"x": 1000.0, "y": 0.0, "z": 0.0},
            {"x": 1000.0, "y": 1000.0, "z": 0.0},
            {"x": 0.0, "y": 1000.0, "z": 0.0},
        ],
        "faces": [[0, 1, 2, 3]],
    }

    geom = PreciseGeometry(geometry_data)

    assert len(geom.vertices) == 4
    assert len(geom.faces) == 1
    assert geom.vertices[0] == (0.0, 0.0, 0.0)
    assert geom.vertices[2] == (1000.0, 1000.0, 0.0)


def test_precise_geometry_bounding_box():
    """Test getting bounding box from precise geometry."""
    geometry_data = {
        "vertices": [
            {"x": 100.0, "y": 200.0, "z": 300.0},
            {"x": 500.0, "y": 600.0, "z": 700.0},
            {"x": 150.0, "y": 250.0, "z": 350.0},
        ],
    }

    geom = PreciseGeometry(geometry_data)
    bbox = geom.get_bounding_box()

    assert bbox.min_x == 100.0
    assert bbox.min_y == 200.0
    assert bbox.min_z == 300.0
    assert bbox.max_x == 500.0
    assert bbox.max_y == 600.0
    assert bbox.max_z == 700.0


def test_precise_geometry_empty():
    """Test precise geometry with no vertices."""
    geometry_data = {}
    geom = PreciseGeometry(geometry_data)

    bbox = geom.get_bounding_box()
    assert bbox.min_x == 0
    assert bbox.max_x == 0


def test_point_in_bbox():
    """Test point-in-bounding-box check."""
    geometry_data = {
        "vertices": [
            {"x": 0.0, "y": 0.0, "z": 0.0},
            {"x": 1000.0, "y": 1000.0, "z": 1000.0},
        ],
    }

    geom = PreciseGeometry(geometry_data)
    bbox = geom.get_bounding_box()

    # Point inside
    assert geom._point_in_bbox((500.0, 500.0, 500.0), bbox) is True

    # Point outside
    assert geom._point_in_bbox((1500.0, 1500.0, 1500.0), bbox) is False

    # Point on boundary (should be False with strict < check)
    assert geom._point_in_bbox((0.0, 0.0, 0.0), bbox) is False


def test_precise_geometry_intersects():
    """Test precise geometry intersection detection."""
    # Geometry 1: cube from 0,0,0 to 1000,1000,1000
    geom1_data = {
        "vertices": [
            {"x": 0.0, "y": 0.0, "z": 0.0},
            {"x": 1000.0, "y": 0.0, "z": 0.0},
            {"x": 1000.0, "y": 1000.0, "z": 0.0},
            {"x": 0.0, "y": 1000.0, "z": 0.0},
            {"x": 0.0, "y": 0.0, "z": 1000.0},
            {"x": 1000.0, "y": 0.0, "z": 1000.0},
            {"x": 1000.0, "y": 1000.0, "z": 1000.0},
            {"x": 0.0, "y": 1000.0, "z": 1000.0},
        ],
    }

    # Geometry 2: cube from 500,500,500 to 1500,1500,1500 (overlapping)
    geom2_data = {
        "vertices": [
            {"x": 500.0, "y": 500.0, "z": 500.0},
            {"x": 1500.0, "y": 500.0, "z": 500.0},
            {"x": 1500.0, "y": 1500.0, "z": 500.0},
            {"x": 500.0, "y": 1500.0, "z": 500.0},
            {"x": 500.0, "y": 500.0, "z": 1500.0},
            {"x": 1500.0, "y": 500.0, "z": 1500.0},
            {"x": 1500.0, "y": 1500.0, "z": 1500.0},
            {"x": 500.0, "y": 1500.0, "z": 1500.0},
        ],
    }

    geom1 = PreciseGeometry(geom1_data)
    geom2 = PreciseGeometry(geom2_data)

    assert geom1.intersects_with(geom2) is True
    assert geom2.intersects_with(geom1) is True


def test_precise_geometry_no_intersection():
    """Test precise geometry with no intersection."""
    # Geometry 1: cube from 0,0,0 to 1000,1000,1000
    geom1_data = {
        "vertices": [
            {"x": 0.0, "y": 0.0, "z": 0.0},
            {"x": 1000.0, "y": 1000.0, "z": 1000.0},
        ],
    }

    # Geometry 2: cube from 2000,2000,2000 to 3000,3000,3000 (separated)
    geom2_data = {
        "vertices": [
            {"x": 2000.0, "y": 2000.0, "z": 2000.0},
            {"x": 3000.0, "y": 3000.0, "z": 3000.0},
        ],
    }

    geom1 = PreciseGeometry(geom1_data)
    geom2 = PreciseGeometry(geom2_data)

    assert geom1.intersects_with(geom2) is False
    assert geom2.intersects_with(geom1) is False


def test_check_precise_clash():
    """Test precise clash detection."""
    detector = ClashDetector()

    # Overlapping geometries
    geom1_data = {
        "vertices": [
            {"x": 0.0, "y": 0.0, "z": 0.0},
            {"x": 1000.0, "y": 1000.0, "z": 1000.0},
        ],
    }

    geom2_data = {
        "vertices": [
            {"x": 500.0, "y": 500.0, "z": 500.0},
            {"x": 1500.0, "y": 1500.0, "z": 1500.0},
        ],
    }

    geom1 = PreciseGeometry(geom1_data)
    geom2 = PreciseGeometry(geom2_data)

    clash = detector.check_precise_clash("wall_1", geom1, "beam_1", geom2)

    assert clash is not None
    assert clash.element_id_1 == "wall_1"
    assert clash.element_id_2 == "beam_1"
    assert clash.clash_type == "precise_geometry"
    assert clash.intersection_volume > 0
    assert clash.location is not None


def test_check_precise_clash_no_intersection():
    """Test precise clash with no intersection."""
    detector = ClashDetector()

    geom1_data = {
        "vertices": [
            {"x": 0.0, "y": 0.0, "z": 0.0},
            {"x": 1000.0, "y": 1000.0, "z": 1000.0},
        ],
    }

    geom2_data = {
        "vertices": [
            {"x": 2000.0, "y": 2000.0, "z": 2000.0},
            {"x": 3000.0, "y": 3000.0, "z": 3000.0},
        ],
    }

    geom1 = PreciseGeometry(geom1_data)
    geom2 = PreciseGeometry(geom2_data)

    clash = detector.check_precise_clash("elem_1", geom1, "elem_2", geom2)

    assert clash is None


def test_check_precise_multiple_elements():
    """Test precise clash detection for multiple elements."""
    detector = ClashDetector()

    elements = [
        {
            "id": "wall_1",
            "geometry": {
                "vertices": [
                    {"x": 0.0, "y": 0.0, "z": 0.0},
                    {"x": 1000.0, "y": 1000.0, "z": 3000.0},
                ],
            },
        },
        {
            "id": "beam_1",
            "geometry": {
                "vertices": [
                    {"x": 500.0, "y": 500.0, "z": 1000.0},
                    {"x": 1500.0, "y": 1500.0, "z": 2000.0},
                ],
            },
        },
        {
            "id": "column_1",
            "geometry": {
                "vertices": [
                    {"x": 5000.0, "y": 5000.0, "z": 0.0},
                    {"x": 5500.0, "y": 5500.0, "z": 3000.0},
                ],
            },
        },
    ]

    clashes = detector.check_precise_multiple_elements(elements)

    # Should find 1 clash (wall_1 and beam_1)
    assert len(clashes) == 1
    assert clashes[0].element_id_1 == "wall_1"
    assert clashes[0].element_id_2 == "beam_1"
    assert clashes[0].clash_type == "precise_geometry"


def test_precise_clash_severity():
    """Test severity calculation for precise clashes."""
    detector = ClashDetector()

    # Large intersection
    geom1_data = {
        "vertices": [
            {"x": 0.0, "y": 0.0, "z": 0.0},
            {"x": 2000.0, "y": 2000.0, "z": 2000.0},
        ],
    }

    geom2_data = {
        "vertices": [
            {"x": 1000.0, "y": 1000.0, "z": 1000.0},
            {"x": 3000.0, "y": 3000.0, "z": 3000.0},
        ],
    }

    geom1 = PreciseGeometry(geom1_data)
    geom2 = PreciseGeometry(geom2_data)

    clash = detector.check_precise_clash("e1", geom1, "e2", geom2)

    # 1000³ mm³ = 1 m³ = critical
    assert clash.severity == "critical"


def test_mixed_precise_and_bbox_clashes():
    """Test detector can handle both precise and bounding box clashes."""
    from model_checker.clash_detection import BoundingBox

    detector = ClashDetector()

    # Add bbox clash
    bbox1 = BoundingBox(0, 0, 0, 1000, 1000, 1000)
    bbox2 = BoundingBox(500, 500, 500, 1500, 1500, 1500)
    detector.check_bounding_box_clash("e1", bbox1, "e2", bbox2)

    # Add precise clash (overlapping cubes)
    geom1_data = {
        "vertices": [
            {"x": 0.0, "y": 0.0, "z": 0.0},
            {"x": 1000.0, "y": 1000.0, "z": 1000.0},
        ]
    }
    geom2_data = {
        "vertices": [
            {"x": 500.0, "y": 500.0, "z": 500.0},
            {"x": 1500.0, "y": 1500.0, "z": 1500.0},
        ]
    }
    geom1 = PreciseGeometry(geom1_data)
    geom2 = PreciseGeometry(geom2_data)
    detector.check_precise_clash("e3", geom1, "e4", geom2)

    assert detector.get_total_clashes() == 2
    assert len(detector.clashes) == 2


def test_precise_geometry_complex_shape():
    """Test precise geometry with complex shape."""
    # L-shaped geometry
    geom_data = {
        "vertices": [
            # Bottom horizontal part
            {"x": 0.0, "y": 0.0, "z": 0.0},
            {"x": 1000.0, "y": 0.0, "z": 0.0},
            {"x": 1000.0, "y": 200.0, "z": 0.0},
            {"x": 0.0, "y": 200.0, "z": 0.0},
            # Vertical part
            {"x": 0.0, "y": 200.0, "z": 0.0},
            {"x": 200.0, "y": 200.0, "z": 0.0},
            {"x": 200.0, "y": 800.0, "z": 0.0},
            {"x": 0.0, "y": 800.0, "z": 0.0},
        ],
        "faces": [[0, 1, 2, 3], [4, 5, 6, 7]],
    }

    geom = PreciseGeometry(geom_data)

    assert len(geom.vertices) == 8
    assert len(geom.faces) == 2

    bbox = geom.get_bounding_box()
    assert bbox.min_x == 0.0
    assert bbox.max_x == 1000.0
    assert bbox.min_y == 0.0
    assert bbox.max_y == 800.0
