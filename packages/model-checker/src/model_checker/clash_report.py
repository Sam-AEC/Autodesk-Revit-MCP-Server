"""Clash visualization report generation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .clash_detection import ClashResult


@dataclass
class ClashVisualizationReport:
    """Report for clash detection visualization."""

    project_name: str
    timestamp: datetime = field(default_factory=datetime.now)
    clashes: list[ClashResult] = field(default_factory=list)
    total_elements_checked: int = 0
    clash_matrix: dict[str, list[str]] = field(default_factory=dict)

    def add_clash(self, clash: ClashResult) -> None:
        """Add a clash to the report.

        Args:
            clash: Clash result to add
        """
        self.clashes.append(clash)
        self._update_clash_matrix(clash)

    def _update_clash_matrix(self, clash: ClashResult) -> None:
        """Update the clash matrix with a new clash.

        Args:
            clash: Clash result to add to matrix
        """
        elem1 = str(clash.element_id_1)
        elem2 = str(clash.element_id_2)

        if elem1 not in self.clash_matrix:
            self.clash_matrix[elem1] = []
        if elem2 not in self.clash_matrix:
            self.clash_matrix[elem2] = []

        self.clash_matrix[elem1].append(elem2)
        self.clash_matrix[elem2].append(elem1)

    def get_clashes_by_severity(self, severity: str) -> list[ClashResult]:
        """Get all clashes of a specific severity.

        Args:
            severity: Severity level to filter by

        Returns:
            List of clashes with specified severity
        """
        return [clash for clash in self.clashes if clash.severity == severity]

    def get_clash_count(self) -> int:
        """Get total number of clashes.

        Returns:
            Number of clashes
        """
        return len(self.clashes)

    def get_critical_count(self) -> int:
        """Get count of critical clashes.

        Returns:
            Number of critical clashes
        """
        return len(self.get_clashes_by_severity("critical"))

    def get_high_count(self) -> int:
        """Get count of high severity clashes.

        Returns:
            Number of high severity clashes
        """
        return len(self.get_clashes_by_severity("high"))

    def get_elements_with_clashes(self) -> list[str]:
        """Get list of all elements involved in clashes.

        Returns:
            List of element IDs
        """
        return list(self.clash_matrix.keys())

    def get_most_problematic_elements(self, limit: int = 10) -> list[tuple[str, int]]:
        """Get elements with most clashes.

        Args:
            limit: Maximum number of elements to return

        Returns:
            List of (element_id, clash_count) tuples, sorted by count descending
        """
        element_counts = [(elem, len(clashes)) for elem, clashes in self.clash_matrix.items()]
        element_counts.sort(key=lambda x: x[1], reverse=True)
        return element_counts[:limit]

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary for JSON serialization.

        Returns:
            Dictionary representation of the report
        """
        return {
            "project_name": self.project_name,
            "timestamp": self.timestamp.isoformat(),
            "summary": {
                "total_clashes": self.get_clash_count(),
                "critical_clashes": self.get_critical_count(),
                "high_clashes": self.get_high_count(),
                "elements_checked": self.total_elements_checked,
                "elements_with_clashes": len(self.get_elements_with_clashes()),
            },
            "clashes": [
                {
                    "element_id_1": clash.element_id_1,
                    "element_id_2": clash.element_id_2,
                    "clash_type": clash.clash_type,
                    "severity": clash.severity,
                    "intersection_volume": clash.intersection_volume,
                    "location": clash.location,
                }
                for clash in self.clashes
            ],
            "clash_matrix": self.clash_matrix,
            "most_problematic_elements": [
                {"element_id": elem, "clash_count": count}
                for elem, count in self.get_most_problematic_elements()
            ],
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert report to JSON string.

        Args:
            indent: Number of spaces for indentation

        Returns:
            JSON string representation
        """
        return json.dumps(self.to_dict(), indent=indent)

    def save_to_file(self, filepath: str) -> None:
        """Save report to JSON file.

        Args:
            filepath: Path to save the JSON file
        """
        with open(filepath, "w") as f:
            f.write(self.to_json())

    def get_clash_pairs(self) -> list[tuple[str | int, str | int]]:
        """Get list of all clash pairs.

        Returns:
            List of (element_id_1, element_id_2) tuples
        """
        return [(clash.element_id_1, clash.element_id_2) for clash in self.clashes]

    def get_clash_locations(self) -> list[dict[str, float]]:
        """Get list of all clash locations.

        Returns:
            List of location dictionaries with x, y, z coordinates
        """
        return [clash.location for clash in self.clashes if clash.location is not None]

    def generate_visualization_data(self) -> dict[str, Any]:
        """Generate data formatted for 3D visualization.

        Returns:
            Dictionary with visualization data including nodes and edges
        """
        nodes = {}
        edges = []

        for clash in self.clashes:
            elem1 = str(clash.element_id_1)
            elem2 = str(clash.element_id_2)

            # Add nodes
            if elem1 not in nodes:
                nodes[elem1] = {
                    "id": elem1,
                    "clash_count": len(self.clash_matrix.get(elem1, [])),
                }

            if elem2 not in nodes:
                nodes[elem2] = {
                    "id": elem2,
                    "clash_count": len(self.clash_matrix.get(elem2, [])),
                }

            # Add edge
            edges.append(
                {
                    "source": elem1,
                    "target": elem2,
                    "severity": clash.severity,
                    "volume": clash.intersection_volume,
                    "location": clash.location,
                }
            )

        return {
            "nodes": list(nodes.values()),
            "edges": edges,
        }


class ClashReportBuilder:
    """Builder for creating clash visualization reports."""

    def __init__(self, project_name: str) -> None:
        """Initialize the report builder.

        Args:
            project_name: Name of the project
        """
        self.report = ClashVisualizationReport(project_name=project_name)

    def add_clashes(self, clashes: list[ClashResult]) -> ClashReportBuilder:
        """Add multiple clashes to the report.

        Args:
            clashes: List of clash results

        Returns:
            Self for method chaining
        """
        for clash in clashes:
            self.report.add_clash(clash)
        return self

    def set_elements_checked(self, count: int) -> ClashReportBuilder:
        """Set the number of elements checked.

        Args:
            count: Number of elements

        Returns:
            Self for method chaining
        """
        self.report.total_elements_checked = count
        return self

    def build(self) -> ClashVisualizationReport:
        """Build and return the report.

        Returns:
            Complete clash visualization report
        """
        return self.report
