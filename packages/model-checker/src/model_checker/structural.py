"""Structural integrity validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class StructuralIssue:
    """Structural validation issue."""

    element_id: str | int
    element_type: str
    issue_type: str
    description: str
    location: dict[str, float] | None = None
    severity: str = "high"


class StructuralValidator:
    """Validator for structural integrity."""

    def __init__(self) -> None:
        """Initialize structural validator."""
        self.issues: list[StructuralIssue] = []

    # Task 5.1: Column-beam connections
    def validate_beam_connections(
        self, beams: list[dict[str, Any]], columns: list[dict[str, Any]]
    ) -> list[StructuralIssue]:
        """Validate beam-column connections."""
        issues = []

        for beam in beams:
            start_connected = False
            end_connected = False

            start_pt = beam.get("start_point")
            end_pt = beam.get("end_point")

            if not start_pt or not end_pt:
                continue

            # Check if beam ends connect to columns
            for column in columns:
                col_location = column.get("location")
                if not col_location:
                    continue

                # Check start connection (ignore Z - beams connect horizontally)
                if self._points_near_horizontal(start_pt, col_location, tolerance=100):
                    start_connected = True

                # Check end connection (ignore Z - beams connect horizontally)
                if self._points_near_horizontal(end_pt, col_location, tolerance=100):
                    end_connected = True

            if not start_connected:
                issue = StructuralIssue(
                    element_id=beam["id"],
                    element_type="beam",
                    issue_type="unconnected_start",
                    description="Beam start is not connected to a column",
                    location=start_pt,
                    severity="critical",
                )
                issues.append(issue)
                self.issues.append(issue)

            if not end_connected:
                issue = StructuralIssue(
                    element_id=beam["id"],
                    element_type="beam",
                    issue_type="unconnected_end",
                    description="Beam end is not connected to a column",
                    location=end_pt,
                    severity="critical",
                )
                issues.append(issue)
                self.issues.append(issue)

        return issues

    # Task 5.2: Foundation validation
    def validate_foundations(
        self, columns: list[dict[str, Any]], foundations: list[dict[str, Any]]
    ) -> list[StructuralIssue]:
        """Validate that all columns have foundations."""
        issues = []

        for column in columns:
            col_location = column.get("base_point")
            if not col_location:
                continue

            has_foundation = False

            for foundation in foundations:
                found_location = foundation.get("location")
                if not found_location:
                    continue

                if self._points_near_horizontal(col_location, found_location, tolerance=200):
                    has_foundation = True
                    break

            if not has_foundation:
                issue = StructuralIssue(
                    element_id=column["id"],
                    element_type="column",
                    issue_type="missing_foundation",
                    description=f"Column {column.get('name', column['id'])} has no foundation",
                    location=col_location,
                    severity="critical",
                )
                issues.append(issue)
                self.issues.append(issue)

        return issues

    # Task 5.3: Load path validation
    def validate_load_path(
        self,
        roof_elements: list[dict[str, Any]],
        beams: list[dict[str, Any]],
        columns: list[dict[str, Any]],
        foundations: list[dict[str, Any]],
    ) -> list[StructuralIssue]:
        """Validate continuous load path from roof to foundation."""
        issues = []

        # Check roof elements have supporting beams
        for roof in roof_elements:
            roof_location = roof.get("location")
            if not roof_location:
                continue

            has_support = any(
                self._element_supports(beam, roof_location) for beam in beams
            )

            if not has_support:
                issue = StructuralIssue(
                    element_id=roof["id"],
                    element_type="roof",
                    issue_type="no_support",
                    description="Roof element has no supporting beam",
                    location=roof_location,
                    severity="critical",
                )
                issues.append(issue)
                self.issues.append(issue)

        # Check beams have supporting columns (already done in validate_beam_connections)

        # Check columns have foundations (already done in validate_foundations)

        # Check for broken load path
        unsupported_columns = []
        for column in columns:
            base = column.get("base_point")
            if not base:
                continue

            has_foundation = any(
                self._points_near_horizontal(base, f.get("location", {}), tolerance=200)
                for f in foundations
                if f.get("location")
            )

            if not has_foundation:
                unsupported_columns.append(column["id"])

        if unsupported_columns:
            issue = StructuralIssue(
                element_id="system",
                element_type="structural_system",
                issue_type="broken_load_path",
                description=f"Broken load path: {len(unsupported_columns)} columns without foundations",
                severity="critical",
            )
            issues.append(issue)
            self.issues.append(issue)

        return issues

    def _points_near(
        self, point1: dict[str, float], point2: dict[str, float], tolerance: float = 100.0
    ) -> bool:
        """Check if two points are within tolerance (3D distance)."""
        dx = point1.get("x", 0) - point2.get("x", 0)
        dy = point1.get("y", 0) - point2.get("y", 0)
        dz = point1.get("z", 0) - point2.get("z", 0)

        distance = (dx**2 + dy**2 + dz**2) ** 0.5
        return distance <= tolerance

    def _points_near_horizontal(
        self, point1: dict[str, float], point2: dict[str, float], tolerance: float = 100.0
    ) -> bool:
        """Check if two points are within tolerance (horizontal distance only, ignoring Z)."""
        dx = point1.get("x", 0) - point2.get("x", 0)
        dy = point1.get("y", 0) - point2.get("y", 0)

        distance = (dx**2 + dy**2) ** 0.5
        return distance <= tolerance

    def _element_supports(
        self, beam: dict[str, Any], point: dict[str, float], tolerance: float = 300.0
    ) -> bool:
        """Check if beam supports a point."""
        start = beam.get("start_point")
        end = beam.get("end_point")

        if not start or not end:
            return False

        # Check if point is near the beam line (simplified)
        return self._points_near(point, start, tolerance) or self._points_near(
            point, end, tolerance
        )

    def get_issues(self) -> list[StructuralIssue]:
        """Get all structural issues."""
        return self.issues

    def get_issues_by_severity(self, severity: str) -> list[StructuralIssue]:
        """Get issues by severity."""
        return [issue for issue in self.issues if issue.severity == severity]

    def get_critical_issues(self) -> list[StructuralIssue]:
        """Get critical structural issues."""
        return self.get_issues_by_severity("critical")

    def clear_issues(self) -> None:
        """Clear all issues."""
        self.issues = []

    def get_issue_count(self) -> int:
        """Get total issue count."""
        return len(self.issues)
