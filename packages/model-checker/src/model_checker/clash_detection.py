"""Clash detection functionality for geometric conflicts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class BoundingBox:
    """3D bounding box representation."""

    min_x: float
    min_y: float
    min_z: float
    max_x: float
    max_y: float
    max_z: float

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BoundingBox:
        """Create BoundingBox from dictionary.

        Args:
            data: Dictionary with min/max coordinates

        Returns:
            BoundingBox instance
        """
        return cls(
            min_x=data["min"]["x"],
            min_y=data["min"]["y"],
            min_z=data["min"]["z"],
            max_x=data["max"]["x"],
            max_y=data["max"]["y"],
            max_z=data["max"]["z"],
        )

    def intersects(self, other: BoundingBox) -> bool:
        """Check if this bounding box intersects with another.

        Uses Separating Axis Theorem (SAT) for axis-aligned bounding boxes.
        Boxes intersect if they overlap on all three axes.

        Args:
            other: Another bounding box to check intersection with

        Returns:
            True if boxes intersect, False otherwise
        """
        # Check for separation on each axis (use <= to exclude touching boxes)
        if self.max_x <= other.min_x or other.max_x <= self.min_x:
            return False
        if self.max_y <= other.min_y or other.max_y <= self.min_y:
            return False
        if self.max_z <= other.min_z or other.max_z <= self.min_z:
            return False

        return True

    def get_volume(self) -> float:
        """Calculate the volume of the bounding box.

        Returns:
            Volume in cubic units
        """
        return (
            (self.max_x - self.min_x)
            * (self.max_y - self.min_y)
            * (self.max_z - self.min_z)
        )

    def get_intersection_volume(self, other: BoundingBox) -> float:
        """Calculate the volume of intersection with another box.

        Args:
            other: Another bounding box

        Returns:
            Volume of intersection, or 0 if no intersection
        """
        if not self.intersects(other):
            return 0.0

        overlap_x = min(self.max_x, other.max_x) - max(self.min_x, other.min_x)
        overlap_y = min(self.max_y, other.max_y) - max(self.min_y, other.min_y)
        overlap_z = min(self.max_z, other.max_z) - max(self.min_z, other.min_z)

        return overlap_x * overlap_y * overlap_z

    def get_center(self) -> tuple[float, float, float]:
        """Get the center point of the bounding box.

        Returns:
            Tuple of (x, y, z) coordinates
        """
        return (
            (self.min_x + self.max_x) / 2,
            (self.min_y + self.max_y) / 2,
            (self.min_z + self.max_z) / 2,
        )


@dataclass
class ClashResult:
    """Result of a clash detection between two elements."""

    element_id_1: str | int
    element_id_2: str | int
    clash_type: str
    intersection_volume: float = 0.0
    location: dict[str, float] | None = None
    severity: str = "medium"

    def to_dict(self) -> dict[str, Any]:
        """Convert clash result to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "element_id_1": self.element_id_1,
            "element_id_2": self.element_id_2,
            "clash_type": self.clash_type,
            "intersection_volume": self.intersection_volume,
            "location": self.location,
            "severity": self.severity,
        }


class PreciseGeometry:
    """Represents precise geometry for detailed clash detection."""

    def __init__(self, geometry_data: dict[str, Any]) -> None:
        """Initialize precise geometry.

        Args:
            geometry_data: Dictionary containing geometry information
        """
        self.geometry_data = geometry_data
        self.vertices: list[tuple[float, float, float]] = []
        self.faces: list[list[int]] = []
        self._parse_geometry()

    def _parse_geometry(self) -> None:
        """Parse geometry data into vertices and faces."""
        if "vertices" in self.geometry_data:
            self.vertices = [
                (v["x"], v["y"], v["z"]) for v in self.geometry_data["vertices"]
            ]
        if "faces" in self.geometry_data:
            self.faces = self.geometry_data["faces"]

    def get_bounding_box(self) -> BoundingBox:
        """Get bounding box from precise geometry.

        Returns:
            BoundingBox containing all vertices
        """
        if not self.vertices:
            return BoundingBox(0, 0, 0, 0, 0, 0)

        xs = [v[0] for v in self.vertices]
        ys = [v[1] for v in self.vertices]
        zs = [v[2] for v in self.vertices]

        return BoundingBox(
            min_x=min(xs),
            min_y=min(ys),
            min_z=min(zs),
            max_x=max(xs),
            max_y=max(ys),
            max_z=max(zs),
        )

    def intersects_with(self, other: PreciseGeometry) -> bool:
        """Check if this geometry intersects with another.

        Uses simplified geometric intersection test.
        First checks bounding boxes, then performs vertex-in-bbox tests.

        Args:
            other: Another precise geometry

        Returns:
            True if geometries intersect
        """
        # Quick rejection using bounding boxes
        bbox1 = self.get_bounding_box()
        bbox2 = other.get_bounding_box()

        if not bbox1.intersects(bbox2):
            return False

        # Check if any vertex from one geometry is inside the other's bbox
        for vertex in self.vertices:
            if self._point_in_bbox(vertex, bbox2):
                return True

        for vertex in other.vertices:
            if self._point_in_bbox(vertex, bbox1):
                return True

        return False

    def _point_in_bbox(
        self, point: tuple[float, float, float], bbox: BoundingBox
    ) -> bool:
        """Check if a point is inside a bounding box.

        Args:
            point: 3D point coordinates
            bbox: Bounding box to check

        Returns:
            True if point is inside bbox
        """
        x, y, z = point
        return (
            bbox.min_x < x < bbox.max_x
            and bbox.min_y < y < bbox.max_y
            and bbox.min_z < z < bbox.max_z
        )


class ClashDetector:
    """Detector for geometric clashes between elements."""

    def __init__(self, tolerance: float = 0.0) -> None:
        """Initialize clash detector.

        Args:
            tolerance: Tolerance distance for clash detection (mm)
        """
        self.tolerance = tolerance
        self.clashes: list[ClashResult] = []

    def check_bounding_box_clash(
        self,
        element_id_1: str | int,
        bbox_1: BoundingBox,
        element_id_2: str | int,
        bbox_2: BoundingBox,
    ) -> ClashResult | None:
        """Check for clash between two bounding boxes.

        Args:
            element_id_1: ID of first element
            bbox_1: Bounding box of first element
            element_id_2: ID of second element
            bbox_2: Bounding box of second element

        Returns:
            ClashResult if clash detected, None otherwise
        """
        if bbox_1.intersects(bbox_2):
            intersection_volume = bbox_1.get_intersection_volume(bbox_2)
            center_1 = bbox_1.get_center()
            center_2 = bbox_2.get_center()

            location = {
                "x": (center_1[0] + center_2[0]) / 2,
                "y": (center_1[1] + center_2[1]) / 2,
                "z": (center_1[2] + center_2[2]) / 2,
            }

            # Determine severity based on intersection volume
            severity = self._calculate_severity(intersection_volume)

            clash = ClashResult(
                element_id_1=element_id_1,
                element_id_2=element_id_2,
                clash_type="bounding_box",
                intersection_volume=intersection_volume,
                location=location,
                severity=severity,
            )

            self.clashes.append(clash)
            return clash

        return None

    def check_multiple_elements(
        self,
        elements: list[dict[str, Any]],
    ) -> list[ClashResult]:
        """Check for clashes between multiple elements.

        Args:
            elements: List of element dicts with 'id' and 'bounding_box' keys

        Returns:
            List of detected clashes
        """
        clashes = []
        n = len(elements)

        for i in range(n):
            elem_1 = elements[i]
            bbox_1 = elem_1["bounding_box"]
            if isinstance(bbox_1, dict):
                bbox_1 = BoundingBox.from_dict(bbox_1)

            for j in range(i + 1, n):
                elem_2 = elements[j]
                bbox_2 = elem_2["bounding_box"]
                if isinstance(bbox_2, dict):
                    bbox_2 = BoundingBox.from_dict(bbox_2)

                clash = self.check_bounding_box_clash(
                    elem_1["id"],
                    bbox_1,
                    elem_2["id"],
                    bbox_2,
                )

                if clash:
                    clashes.append(clash)

        return clashes

    def _calculate_severity(self, intersection_volume: float) -> str:
        """Calculate clash severity based on intersection volume.

        Args:
            intersection_volume: Volume of intersection in cubic mm

        Returns:
            Severity level: "critical", "high", "medium", or "low"
        """
        # Convert mm³ to m³ for easier thresholds
        volume_m3 = intersection_volume / 1_000_000_000

        if volume_m3 >= 1.0:
            return "critical"
        if volume_m3 >= 0.1:
            return "high"
        if volume_m3 >= 0.01:
            return "medium"
        return "low"

    def get_clashes_by_severity(self, severity: str) -> list[ClashResult]:
        """Get all clashes of a specific severity.

        Args:
            severity: Severity level to filter by

        Returns:
            List of clashes with specified severity
        """
        return [clash for clash in self.clashes if clash.severity == severity]

    def get_critical_clashes(self) -> list[ClashResult]:
        """Get all critical clashes.

        Returns:
            List of critical clashes
        """
        return self.get_clashes_by_severity("critical")

    def get_total_clashes(self) -> int:
        """Get total number of clashes detected.

        Returns:
            Number of clashes
        """
        return len(self.clashes)

    def clear_clashes(self) -> None:
        """Clear all stored clashes."""
        self.clashes = []

    def check_precise_clash(
        self,
        element_id_1: str | int,
        geometry_1: PreciseGeometry,
        element_id_2: str | int,
        geometry_2: PreciseGeometry,
    ) -> ClashResult | None:
        """Check for precise geometric clash between two elements.

        Uses detailed geometry analysis beyond bounding box intersection.

        Args:
            element_id_1: ID of first element
            geometry_1: Precise geometry of first element
            element_id_2: ID of second element
            geometry_2: Precise geometry of second element

        Returns:
            ClashResult if clash detected, None otherwise
        """
        if geometry_1.intersects_with(geometry_2):
            # Estimate intersection volume from bounding box overlap
            bbox_1 = geometry_1.get_bounding_box()
            bbox_2 = geometry_2.get_bounding_box()
            intersection_volume = bbox_1.get_intersection_volume(bbox_2)

            center_1 = bbox_1.get_center()
            center_2 = bbox_2.get_center()

            location = {
                "x": (center_1[0] + center_2[0]) / 2,
                "y": (center_1[1] + center_2[1]) / 2,
                "z": (center_1[2] + center_2[2]) / 2,
            }

            severity = self._calculate_severity(intersection_volume)

            clash = ClashResult(
                element_id_1=element_id_1,
                element_id_2=element_id_2,
                clash_type="precise_geometry",
                intersection_volume=intersection_volume,
                location=location,
                severity=severity,
            )

            self.clashes.append(clash)
            return clash

        return None

    def check_precise_multiple_elements(
        self,
        elements: list[dict[str, Any]],
    ) -> list[ClashResult]:
        """Check for precise clashes between multiple elements.

        Args:
            elements: List of element dicts with 'id' and 'geometry' keys

        Returns:
            List of detected clashes
        """
        clashes = []
        n = len(elements)

        for i in range(n):
            elem_1 = elements[i]
            geom_1 = elem_1["geometry"]
            if isinstance(geom_1, dict):
                geom_1 = PreciseGeometry(geom_1)

            for j in range(i + 1, n):
                elem_2 = elements[j]
                geom_2 = elem_2["geometry"]
                if isinstance(geom_2, dict):
                    geom_2 = PreciseGeometry(geom_2)

                clash = self.check_precise_clash(
                    elem_1["id"],
                    geom_1,
                    elem_2["id"],
                    geom_2,
                )

                if clash:
                    clashes.append(clash)

        return clashes
