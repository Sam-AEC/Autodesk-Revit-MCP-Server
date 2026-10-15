import importlib
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..security.workspace import WorkspaceMonitor
from .base import AECProvider, ProviderTool


def _ifcopenshell() -> Any:
    """Import ifcopenshell on first use (it is slow to import)."""
    import ifcopenshell
    import ifcopenshell.util
    import ifcopenshell.util.placement

    return ifcopenshell


def _has_submodule(name: str) -> bool:
    try:
        importlib.import_module(f"ifcopenshell.{name}")
        return True
    except ImportError:
        return False


logger = logging.getLogger(__name__)

class IfcProvider(AECProvider):
    def __init__(self, workspace: WorkspaceMonitor) -> None:
        self.workspace = workspace
        self._init_capabilities()

    def get_identity(self) -> str:
        return "ifc"

    def get_capabilities(self) -> List[ProviderTool]:
        return self._capabilities

    async def check_health(self) -> Dict[str, Any]:
        ifcopenshell = _ifcopenshell()
        return {
            "status": "healthy",
            "provider": "ifc",
            "ifcopenshell_version": getattr(ifcopenshell, "__version__", "0.7.0"),
            "has_geom": _has_submodule("geom"),
            "has_validate": _has_submodule("validate")
        }

    async def execute_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if name == "ifc_health":
            return await self.check_health()

        # All other tools require an ifc_path
        ifc_path_str = arguments.get("ifc_path")
        if not ifc_path_str:
            raise ValueError("Argument 'ifc_path' is required.")

        resolved_path = self.workspace.assert_in_workspace(Path(ifc_path_str))
        if not resolved_path.exists():
            raise FileNotFoundError(f"IFC file not found: {resolved_path}")

        # Open the file
        try:
            ifc_file = _ifcopenshell().open(str(resolved_path))
        except Exception as e:
            raise ValueError(f"Failed to open IFC file: {e}") from e

        try:
            if name == "ifc_get_metadata":
                return self._get_metadata(ifc_file)
            elif name == "ifc_get_spatial_structure":
                return self._get_spatial_structure(ifc_file)
            elif name == "ifc_query_elements":
                return self._query_elements(ifc_file, arguments)
            elif name == "ifc_get_properties":
                return self._get_properties(ifc_file, arguments)
            elif name == "ifc_get_bounding_box":
                return self._get_bounding_box(ifc_file, arguments)
            elif name == "ifc_validate":
                return self._validate(ifc_file)
            else:
                raise ValueError(f"Unknown IFC tool '{name}'")
        finally:
            # clean up references if needed (ifcopenshell files don't have explicit close in older versions, but we delete to trigger garbage collection)
            del ifc_file

    def _init_capabilities(self):
        self._capabilities = [
            ProviderTool(
                name="ifc_health",
                description="Check status of IfcOpenShell and get version info",
                inputSchema={"type": "object", "properties": {}, "required": []}
            ),
            ProviderTool(
                name="ifc_get_metadata",
                description="Get file schema, header metadata, units, and georeferencing summary from an IFC file",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "ifc_path": {"type": "string", "description": "Absolute or workspace-relative path to the IFC file"}
                    },
                    "required": ["ifc_path"]
                }
            ),
            ProviderTool(
                name="ifc_get_spatial_structure",
                description="Get the spatial hierarchy (Project -> Site -> Building -> Storey -> Element Types/Counts) from an IFC file",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "ifc_path": {"type": "string", "description": "Absolute or workspace-relative path to the IFC file"}
                    },
                    "required": ["ifc_path"]
                }
            ),
            ProviderTool(
                name="ifc_query_elements",
                description="Query elements by IFC class, GUID, name, or simple property name/value criteria",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "ifc_path": {"type": "string", "description": "Absolute or workspace-relative path to the IFC file"},
                        "ifc_class": {"type": "string", "description": "IFC Class to query, e.g. 'IfcWall', 'IfcWindow' (optional)"},
                        "guid": {"type": "string", "description": "Query specific element by its GlobalId/GUID (optional)"},
                        "name_filter": {"type": "string", "description": "Sub-string filter for element name (optional)"},
                        "property_name": {"type": "string", "description": "Property name filter criteria, used with property_value (optional)"},
                        "property_value": {"description": "Property value filter criteria, used with property_name (optional)"}
                    },
                    "required": ["ifc_path"]
                }
            ),
            ProviderTool(
                name="ifc_get_properties",
                description="Get property sets, quantities, and direct attributes for a specific element in an IFC file",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "ifc_path": {"type": "string", "description": "Absolute or workspace-relative path to the IFC file"},
                        "element_id": {"type": "string", "description": "GlobalId/GUID or Express ID of the element"}
                    },
                    "required": ["ifc_path", "element_id"]
                }
            ),
            ProviderTool(
                name="ifc_get_bounding_box",
                description="Get bounding box dimensions and placement information for a specific element",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "ifc_path": {"type": "string", "description": "Absolute or workspace-relative path to the IFC file"},
                        "element_id": {"type": "string", "description": "GlobalId/GUID or Express ID of the element"}
                    },
                    "required": ["ifc_path", "element_id"]
                }
            ),
            ProviderTool(
                name="ifc_validate",
                description="Perform schema validation on the IFC file and return errors/warnings list",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "ifc_path": {"type": "string", "description": "Absolute or workspace-relative path to the IFC file"}
                    },
                    "required": ["ifc_path"]
                }
            )
        ]

    def _get_metadata(self, ifc_file) -> Dict[str, Any]:
        schema = ifc_file.schema
        
        # Header Info
        header_info = {}
        if hasattr(ifc_file, "header") and ifc_file.header:
            file_name = ifc_file.header.file_name
            if file_name:
                header_info = {
                    "name": file_name.name,
                    "timestamp": file_name.time_stamp,
                    "author": file_name.author,
                    "organization": file_name.organization,
                    "originating_system": file_name.originating_system,
                    "preprocessor_version": file_name.preprocessor_version
                }

        # Project Info
        project = ifc_file.by_type("IfcProject")
        project_name = project[0].Name if project else "N/A"
        project_guid = project[0].GlobalId if project else "N/A"

        # Unit Info
        units = []
        for ua in ifc_file.by_type("IfcUnitAssignment"):
            for unit in ua.Units:
                if unit.is_a("IfcSIUnit"):
                    units.append({
                        "type": unit.UnitType,
                        "name": f"{unit.Prefix or ''}{unit.Name}",
                    })
                elif unit.is_a("IfcConversionBasedUnit"):
                    units.append({
                        "type": unit.UnitType,
                        "name": unit.Name,
                        "conversion_factor": getattr(unit.ConversionFactor.ValueComponent, "wrappedValue", str(unit.ConversionFactor.ValueComponent)) if hasattr(unit, "ConversionFactor") else None
                    })

        # Georeferencing Info
        georeferencing = {}
        sites = ifc_file.by_type("IfcSite")
        if sites:
            site = sites[0]
            lat = getattr(site, "RefLatitude", None)
            lon = getattr(site, "RefLongitude", None)
            elev = getattr(site, "RefElevation", None)
            georeferencing = {
                "latitude": self._parse_coord_tuple(lat),
                "longitude": self._parse_coord_tuple(lon),
                "elevation": elev
            }

        try:
            map_conversions = ifc_file.by_type("IfcMapConversion")
        except RuntimeError:
            map_conversions = []

        if map_conversions:

            mc = map_conversions[0]
            georeferencing["map_conversion"] = {
                "eastings": mc.Eastings,
                "northings": mc.Northings,
                "orthogonal_height": mc.OrthogonalHeight,
                "x_axis_abscissa": getattr(mc, "XAxisAbscissa", None),
                "x_axis_ordinate": getattr(mc, "XAxisOrdinate", None),
                "scale": getattr(mc, "Scale", None)
            }

        return {
            "schema": schema,
            "project_name": project_name,
            "project_guid": project_guid,
            "header": header_info,
            "units": units,
            "georeferencing": georeferencing
        }

    def _parse_coord_tuple(self, coord) -> Optional[float]:
        if coord is None:
            return None
        # Lat/Lon are often represented as tuples: (degrees, minutes, seconds, microseconds)
        if isinstance(coord, (list, tuple)):
            try:
                deg = float(coord[0])
                m = float(coord[1]) if len(coord) > 1 else 0.0
                s = float(coord[2]) if len(coord) > 2 else 0.0
                us = float(coord[3]) if len(coord) > 3 else 0.0
                val = deg + m / 60.0 + (s + us / 1000000.0) / 3600.0
                # handle negative if degree was negative or separate sign
                return val
            except (ValueError, TypeError, IndexError):
                return str(coord)
        return float(coord) if isinstance(coord, (int, float)) else str(coord)

    def _get_spatial_structure(self, ifc_file) -> Dict[str, Any]:
        projects = ifc_file.by_type("IfcProject")
        if not projects:
            return {"message": "No IfcProject found."}
        
        project = projects[0]
        structure = self._build_spatial_node(project, ifc_file)
        return {"spatial_structure": structure}

    def _build_spatial_node(self, node, ifc_file) -> Dict[str, Any]:
        info = {
            "id": node.id(),
            "guid": node.GlobalId,
            "class": node.is_a(),
            "name": node.Name or "",
            "children": []
        }

        # Decompositions
        for rel in getattr(node, "IsDecomposedBy", []):
            if rel.is_a("IfcRelAggregates"):
                for child in rel.RelatedObjects:
                    info["children"].append(self._build_spatial_node(child, ifc_file))

        # Contained elements (e.g. for building storeys)
        contained_counts = {}
        for rel in getattr(node, "ContainsElements", []):
            if rel.is_a("IfcRelContainedInSpatialStructure"):
                for element in rel.RelatedElements:
                    cls = element.is_a()
                    contained_counts[cls] = contained_counts.get(cls, 0) + 1

        if contained_counts:
            info["contained_elements_summary"] = contained_counts

        return info

    def _query_elements(self, ifc_file, arguments: Dict[str, Any]) -> Dict[str, Any]:
        ifc_class = arguments.get("ifc_class") or "IfcProduct"
        guid = arguments.get("guid")
        name_filter = arguments.get("name_filter")
        prop_name = arguments.get("property_name")
        prop_val = arguments.get("property_value")

        # Query by guid first
        if guid:
            try:
                element = ifc_file.by_guid(guid)
                return {"elements": [self._summarize_element(element)]}
            except Exception:
                return {"elements": [], "message": f"No element found with GUID {guid}"}

        # Query by class
        try:
            elements = ifc_file.by_type(ifc_class)
        except Exception as e:
            raise ValueError(f"Invalid IFC class '{ifc_class}': {e}") from e

        filtered_elements = []
        for el in elements:
            # Name filter
            if name_filter and (not el.Name or name_filter.lower() not in el.Name.lower()):
                continue

            # Property filter
            if prop_name:
                has_prop = False
                val = self._get_element_property_value(el, prop_name)
                if val is not None:
                    if prop_val is not None:
                        # Convert to string for broad match comparison
                        if str(val).lower() == str(prop_val).lower():
                            has_prop = True
                    else:
                        has_prop = True
                if not has_prop:
                    continue

            filtered_elements.append(self._summarize_element(el))
            if len(filtered_elements) >= 200:  # Prevent oversized response limit
                return {
                    "elements": filtered_elements,
                    "truncated": True,
                    "message": "Returned first 200 matches. Refine search criteria if needed."
                }

        return {"elements": filtered_elements}

    def _summarize_element(self, element) -> Dict[str, Any]:
        return {
            "id": element.id(),
            "guid": element.GlobalId,
            "class": element.is_a(),
            "name": element.Name or ""
        }

    def _get_element_property_value(self, element, prop_name: str) -> Any:
        for rel in getattr(element, "IsDefinedBy", []):
            if rel.is_a("IfcRelDefinesByProperties"):
                prop_def = rel.RelatingPropertyDefinition
                if prop_def.is_a("IfcPropertySet"):
                    for prop in getattr(prop_def, "HasProperties", []):
                        if prop.Name.lower() == prop_name.lower():
                            return getattr(prop, "NominalValue", None).wrappedValue if hasattr(prop, "NominalValue") else None
        return None

    def _get_properties(self, ifc_file, arguments: Dict[str, Any]) -> Dict[str, Any]:
        el_id = arguments.get("element_id")
        element = self._find_element(ifc_file, el_id)
        if not element:
            raise ValueError(f"Element not found: {el_id}")

        attributes = {}
        try:
            info = element.get_info()
            for k, v in info.items():
                if v is not None and not isinstance(v, (list, tuple)) and not hasattr(v, "id") and k not in ["id", "type"]:
                    attributes[k] = v
        except Exception as e:
            logger.warning(f"Failed to get element attributes: {e}")

        property_sets = {}
        quantities = {}

        for rel in getattr(element, "IsDefinedBy", []):
            if rel.is_a("IfcRelDefinesByProperties"):
                prop_def = rel.RelatingPropertyDefinition
                if prop_def.is_a("IfcPropertySet"):
                    pset_name = prop_def.Name
                    props = {}
                    for prop in getattr(prop_def, "HasProperties", []):
                        if prop.is_a("IfcPropertySingleValue"):
                            val = prop.NominalValue.wrappedValue if prop.NominalValue else None
                            props[prop.Name] = val
                        elif prop.is_a("IfcSimpleProperty"):
                            props[prop.Name] = str(prop)
                    property_sets[pset_name] = props
                elif prop_def.is_a("IfcElementQuantity"):
                    qset_name = prop_def.Name
                    quants = {}
                    for q in getattr(prop_def, "Quantities", []):
                        val = None
                        if q.is_a("IfcQuantityLength"):
                            val = q.LengthValue
                        elif q.is_a("IfcQuantityArea"):
                            val = q.AreaValue
                        elif q.is_a("IfcQuantityVolume"):
                            val = q.VolumeValue
                        elif q.is_a("IfcQuantityCount"):
                            val = q.CountValue
                        elif q.is_a("IfcQuantityWeight"):
                            val = q.WeightValue
                        
                        if val is not None:
                            quants[q.Name] = val
                    quantities[qset_name] = quants

        return {
            "element": self._summarize_element(element),
            "attributes": attributes,
            "property_sets": property_sets,
            "quantities": quantities
        }

    def _find_element(self, ifc_file, element_id: Any):
        if not element_id:
            return None
        # Try as int Express ID
        try:
            return ifc_file.by_id(int(element_id))
        except (ValueError, TypeError, RuntimeError):
            pass
        # Try as GlobalId/GUID
        guid = str(element_id)
        try:
            return ifc_file.by_guid(guid)
        except Exception:
            pass
        # ifcopenshell 0.9 resolves GUIDs through a validated index, so files
        # with a malformed GlobalId (wrong length/charset, seen in exports from
        # other tools) are no longer found by by_guid. Scan for the raw string.
        for root in ifc_file.by_type("IfcRoot"):
            if getattr(root, "GlobalId", None) == guid:
                return root
        return None

    def _get_bounding_box(self, ifc_file, arguments: Dict[str, Any]) -> Dict[str, Any]:
        el_id = arguments.get("element_id")
        element = self._find_element(ifc_file, el_id)
        if not element:
            raise ValueError(f"Element not found: {el_id}")

        summary = {
            "element": self._summarize_element(element),
            "placement": None,
            "bounding_box": None
        }

        # Placement extraction
        if hasattr(element, "ObjectPlacement") and element.ObjectPlacement:
            try:
                matrix = _ifcopenshell().util.placement.get_local_placement(element.ObjectPlacement)
                # Convert matrix array to list
                summary["placement"] = {
                    "matrix": matrix.tolist() if hasattr(matrix, "tolist") else list(matrix)
                }
            except Exception as e:
                summary["placement_error"] = str(e)

        # Bounding box geometry extraction
        if _has_submodule("geom"):
            try:
                geom = importlib.import_module("ifcopenshell.geom")
                settings = geom.settings()
                shape = geom.create_shape(settings, element)
                # Compute min/max from vertices
                verts = shape.geometry.verts
                if verts:
                    xs = verts[0::3]
                    ys = verts[1::3]
                    zs = verts[2::3]
                    min_x, max_x = min(xs), max(xs)
                    min_y, max_y = min(ys), max(ys)
                    min_z, max_z = min(zs), max(zs)
                    
                    summary["bounding_box"] = {
                        "min": [min_x, min_y, min_z],
                        "max": [max_x, max_y, max_z],
                        "size": [max_x - min_x, max_y - min_y, max_z - min_z]
                    }
            except Exception as e:
                summary["bounding_box_error"] = f"Failed to compute geometry: {e}"
        else:
            summary["bounding_box_error"] = "IfcOpenShell.geom (OpenCascade) not available in this environment."

        # Fallback to structural checks if bounding box not resolved
        if not summary["bounding_box"]:
            # Check if element has Representation
            rep = getattr(element, "Representation", None)
            if rep:
                for representation in getattr(rep, "Representations", []):
                    if representation.RepresentationType == "BoundingBox":
                        for item in representation.Items:
                            if item.is_a("IfcBoundingBox"):
                                summary["bounding_box"] = {
                                    "corner": getattr(item.Corner, "Coordinates", None),
                                    "x_dim": item.XDim,
                                    "y_dim": item.YDim,
                                    "z_dim": item.ZDim,
                                    "source": "IfcBoundingBox representation"
                                }
                                break

        return summary

    def _validate(self, ifc_file) -> Dict[str, Any]:
        errors = []
        if _has_submodule("validate"):
            try:
                # Runs standard validation
                validate = importlib.import_module("ifcopenshell.validate")
                for error in validate.validate(ifc_file):
                    errors.append({
                        "message": error.message,
                        "element_id": error.instance.id() if error.instance else None,
                        "element_class": error.instance.is_a() if error.instance else None
                    })
                    if len(errors) >= 100:  # cap validation reports
                        break
            except Exception as e:
                errors.append({"message": f"Validation engine execution failed: {e}"})
        else:
            # Custom basic parser checks
            # 1. Check for missing required attributes
            # 2. Check for type mismatched attributes
            errors.append({"message": "ifcopenshell.validate module is not available. Performing basic check: file loaded successfully."})
            
        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "error_count": len(errors)
        }

    async def shutdown(self) -> None:
        pass

