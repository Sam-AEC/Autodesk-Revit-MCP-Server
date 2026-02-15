"""Room and space validation (Scaffold 6) + Documentation validation (Scaffold 7)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RoomIssue:
    """Room or documentation validation issue."""

    element_id: str | int
    element_type: str
    issue_type: str
    description: str
    location: dict[str, float] | None = None
    severity: str = "medium"


# SCAFFOLD 6: Room and Space Validation

class RoomValidator:
    """Validator for rooms and spaces."""

    def __init__(self) -> None:
        """Initialize room validator."""
        self.issues: list[RoomIssue] = []

    # Task 6.1: Room boundary checker
    def validate_room_boundaries(self, rooms: list[dict[str, Any]]) -> list[RoomIssue]:
        """Validate room boundaries."""
        issues = []

        for room in rooms:
            # Check if room is bound
            if not room.get("is_bound", True):
                issue = RoomIssue(
                    element_id=room["id"],
                    element_type="room",
                    issue_type="unbound",
                    description=f"Room '{room.get('name', room['id'])}' is not bound",
                    severity="high",
                )
                issues.append(issue)
                self.issues.append(issue)

            # Check for overlapping rooms
            # (simplified - would need actual boundary geometry)
            if room.get("overlaps_with"):
                issue = RoomIssue(
                    element_id=room["id"],
                    element_type="room",
                    issue_type="overlapping",
                    description=f"Room overlaps with {room['overlaps_with']}",
                    severity="critical",
                )
                issues.append(issue)
                self.issues.append(issue)

        return issues

    # Task 6.2: Area calculation validation
    def validate_room_areas(
        self,
        rooms: list[dict[str, Any]],
        min_area: float = 5.0,  # m²
        max_area: float = 500.0,  # m²
    ) -> list[RoomIssue]:
        """Validate room areas."""
        issues = []

        for room in rooms:
            area = room.get("area", 0)
            required_area = room.get("required_area")

            # Check minimum area
            if area < min_area:
                issue = RoomIssue(
                    element_id=room["id"],
                    element_type="room",
                    issue_type="area_too_small",
                    description=f"Room area {area:.1f}m² is below minimum {min_area}m²",
                )
                issues.append(issue)
                self.issues.append(issue)

            # Check maximum area
            if area > max_area:
                issue = RoomIssue(
                    element_id=room["id"],
                    element_type="room",
                    issue_type="area_too_large",
                    description=f"Room area {area:.1f}m² exceeds maximum {max_area}m²",
                )
                issues.append(issue)
                self.issues.append(issue)

            # Check against required area
            if required_area and abs(area - required_area) / required_area > 0.1:  # 10% tolerance
                issue = RoomIssue(
                    element_id=room["id"],
                    element_type="room",
                    issue_type="area_mismatch",
                    description=f"Room area {area:.1f}m² differs from required {required_area:.1f}m²",
                )
                issues.append(issue)
                self.issues.append(issue)

        return issues

    # Task 6.3: Occupancy and egress validation
    def validate_occupancy(
        self, rooms: list[dict[str, Any]], max_occupant_load_factor: float = 10.0
    ) -> list[RoomIssue]:
        """Validate occupancy loads and egress."""
        issues = []

        for room in rooms:
            area = room.get("area", 0)
            occupant_load = area / max_occupant_load_factor

            # Check exit access
            has_exit = room.get("has_exit_access", False)
            if not has_exit and occupant_load > 1:
                issue = RoomIssue(
                    element_id=room["id"],
                    element_type="room",
                    issue_type="no_exit_access",
                    description=f"Room with {occupant_load:.0f} occupants has no exit access",
                    severity="critical",
                )
                issues.append(issue)
                self.issues.append(issue)

            # Check exit width (750mm per 50 occupants)
            required_exit_width = (occupant_load / 50) * 750
            actual_exit_width = room.get("exit_width", 0)

            if actual_exit_width < required_exit_width:
                issue = RoomIssue(
                    element_id=room["id"],
                    element_type="room",
                    issue_type="insufficient_exit_width",
                    description=f"Exit width {actual_exit_width}mm insufficient for {occupant_load:.0f} occupants (need {required_exit_width:.0f}mm)",
                    severity="high",
                )
                issues.append(issue)
                self.issues.append(issue)

        return issues

    def get_issues(self) -> list[RoomIssue]:
        """Get all room issues."""
        return self.issues

    def clear_issues(self) -> None:
        """Clear all issues."""
        self.issues = []


# SCAFFOLD 7: Documentation Completeness

class DocumentationValidator:
    """Validator for documentation completeness."""

    def __init__(self) -> None:
        """Initialize documentation validator."""
        self.issues: list[RoomIssue] = []

    # Task 7.1: View completeness checker
    def validate_view_coverage(
        self, elements: list[dict[str, Any]], views: list[dict[str, Any]]
    ) -> list[RoomIssue]:
        """Validate that all elements appear in required views."""
        issues = []

        for element in elements:
            element_views = element.get("visible_in_views", [])
            required_view_types = element.get("required_view_types", ["floor_plan"])

            for view_type in required_view_types:
                has_view_type = any(
                    view["id"] in element_views and view.get("type") == view_type
                    for view in views
                )

                if not has_view_type:
                    issue = RoomIssue(
                        element_id=element["id"],
                        element_type=element.get("type", "element"),
                        issue_type="missing_from_view",
                        description=f"Element not shown in any {view_type} view",
                        severity="medium",
                    )
                    issues.append(issue)
                    self.issues.append(issue)

        return issues

    # Task 7.2: Sheet validation
    def validate_sheets(self, sheets: list[dict[str, Any]]) -> list[RoomIssue]:
        """Validate sheets for completeness."""
        issues = []

        for sheet in sheets:
            # Check for titleblock
            if not sheet.get("has_titleblock"):
                issue = RoomIssue(
                    element_id=sheet["id"],
                    element_type="sheet",
                    issue_type="missing_titleblock",
                    description=f"Sheet {sheet.get('number', sheet['id'])} has no titleblock",
                    severity="high",
                )
                issues.append(issue)
                self.issues.append(issue)

            # Check for placed views
            viewports = sheet.get("viewports", [])
            if len(viewports) == 0:
                issue = RoomIssue(
                    element_id=sheet["id"],
                    element_type="sheet",
                    issue_type="no_views",
                    description=f"Sheet {sheet.get('number', sheet['id'])} has no views placed",
                    severity="high",
                )
                issues.append(issue)
                self.issues.append(issue)

        return issues

    # Task 7.3: Revision tracking validation
    def validate_revisions(
        self, sheets: list[dict[str, Any]], revisions: list[dict[str, Any]]
    ) -> list[RoomIssue]:
        """Validate revision tracking."""
        issues = []

        revision_ids = {rev["id"] for rev in revisions}

        for sheet in sheets:
            sheet_revisions = sheet.get("revisions", [])

            for rev_id in sheet_revisions:
                if rev_id not in revision_ids:
                    issue = RoomIssue(
                        element_id=sheet["id"],
                        element_type="sheet",
                        issue_type="invalid_revision",
                        description=f"Sheet references invalid revision {rev_id}",
                        severity="medium",
                    )
                    issues.append(issue)
                    self.issues.append(issue)

            # Check for revision clouds
            has_clouds = sheet.get("has_revision_clouds", False)
            if sheet_revisions and not has_clouds:
                issue = RoomIssue(
                    element_id=sheet["id"],
                    element_type="sheet",
                    issue_type="missing_revision_clouds",
                    description="Sheet has revisions but no revision clouds",
                    severity="low",
                )
                issues.append(issue)
                self.issues.append(issue)

        return issues

    def get_issues(self) -> list[RoomIssue]:
        """Get all documentation issues."""
        return self.issues

    def clear_issues(self) -> None:
        """Clear all issues."""
        self.issues = []
