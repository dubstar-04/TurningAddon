"""Native FreeCAD asset access for the independent turning tool table."""

from copy import deepcopy
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from uuid import uuid4

import FreeCAD
import Path.Preferences as preferences
from Path.Tool.assets import AssetUri
from Path.Tool.camassets import cam_assets

from . import iso
from .library import ToolEntry, ToolLibrary


_STORES = ("local", "builtin")
_ISO_UNITS = {"EdgeLength": "mm", "TipAngle": "deg", "TipRadius": "mm", "Rotation": "deg"}


@dataclass
class LibrarySnapshot:
    uri: str
    name: str
    table: ToolLibrary
    attributes: dict
    tools: dict
    issues: tuple


@dataclass
class ToolBitSnapshot:
    uri: str
    attributes: dict
    values: dict
    shape_data: bytes


def _iso_values(attributes):
    if attributes.get("version") != 2 or not isinstance(attributes.get("parameter"), dict):
        raise ValueError("Expected a version 2 ToolBit with ISO parameters.")
    name = attributes.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("ToolBit name must be a non-empty string.")
    values = {"name": name}
    for field, unit in _ISO_UNITS.items():
        raw = attributes["parameter"].get(field)
        if isinstance(raw, bool) or not isinstance(raw, (str, int, float)):
            raise ValueError(f"This editor requires the ISO parameter {field}.")
        quantity = FreeCAD.Units.Quantity(raw)
        if quantity.Unit not in (FreeCAD.Units.Quantity(f"1 {unit}").Unit, FreeCAD.Units.Quantity(1).Unit):
            raise ValueError(f"Unexpected units for {field}.")
        if not math.isfinite(quantity.Value):
            raise ValueError(f"{field} must be finite.")
        values[field] = quantity.Value
    if values["EdgeLength"] <= 0 or values["TipRadius"] <= 0:
        raise ValueError("Edge length and nose radius must be positive.")
    if not 0 < values["TipAngle"] < 180:
        raise ValueError("Tip angle must be between 0 and 180 degrees.")
    return values


def load_iso_tool(uri):
    """Load stored ISO dimensions without inferring sizes or restricting shape names."""
    uri = AssetUri(str(uri))
    if uri.asset_type != "toolbit" or not cam_assets.exists(uri, store="local"):
        raise ValueError("Only an existing user ToolBit can be edited in place.")
    attributes = _read_object(uri)
    values = _iso_values(attributes)
    shape_uri = _reference("toolbitshape", attributes.get("shape"))
    shape_data = cam_assets.get_raw(shape_uri, store=_STORES)
    return ToolBitSnapshot(str(uri), attributes, values, shape_data)


def save_iso_tool(snapshot, values):
    """Update a shared ToolBit in place, preserving shape references and extra metadata."""
    uri = AssetUri(snapshot.uri)
    if uri.asset_type != "toolbit" or not cam_assets.exists(uri, store="local"):
        raise ValueError("Only an existing user ToolBit can be edited in place.")
    if _read_object(uri) != snapshot.attributes:
        raise ValueError("ToolBit changed since loading. Reload before saving.")
    shape_uri = _reference("toolbitshape", snapshot.attributes.get("shape"))
    if cam_assets.get_raw(shape_uri, store=_STORES) != snapshot.shape_data:
        raise ValueError("ToolShape changed since loading. Reload before saving.")
    if set(values) != set(snapshot.values):
        raise ValueError("Expected a name and all four ISO dimensions.")
    attributes = deepcopy(snapshot.attributes)
    attributes["name"] = values["name"]
    for field, unit in _ISO_UNITS.items():
        value = values[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{field} must be a finite number.")
        if value != snapshot.values[field]:
            if field == "Rotation" and abs(value) > 360:
                raise ValueError("Mounting angle must be between -360 and 360 degrees.")
            attributes["parameter"][field] = f"{value} {unit}"
    updated_values = _iso_values(attributes)
    if attributes == snapshot.attributes:
        return snapshot
    with TemporaryDirectory() as directory:
        shape_path = Path(directory) / "insert.fcstd"
        shape_path.write_bytes(snapshot.shape_data)
        validate_iso_template(shape_path, attributes["parameter"])
    cam_assets.add_raw(
        uri.asset_type, uri.asset_id,
        json.dumps(attributes, indent=2, allow_nan=False).encode("utf-8"), store="local",
    )
    return ToolBitSnapshot(snapshot.uri, attributes, updated_values, snapshot.shape_data)


def library_location():
    """Report configured library access without creating or migrating assets."""
    directory = preferences.getAssetPath() / "Tools" / "Library"
    return {
        "path": str(directory),
        "readable": directory.is_dir() and os.access(directory, os.R_OK | os.X_OK),
        "writable": directory.is_dir() and os.access(directory, os.W_OK | os.X_OK),
    }


def _read_object(uri):
    data = json.loads(cam_assets.get_raw(uri, store=_STORES))
    if not isinstance(data, dict):
        raise ValueError(f"Asset {uri} must contain a JSON object.")
    return data


def _reference(asset_type, filename):
    if not isinstance(filename, str) or not filename.strip():
        raise ValueError(f"Missing {asset_type} reference.")
    return AssetUri.build(
        asset_type=asset_type,
        asset_id=str(PurePosixPath(filename.replace("\\", "/")).with_suffix("")),
    )


def list_libraries():
    """Return native library identities; loading validates their contents."""
    return tuple(sorted(str(uri) for uri in cam_assets.list_assets(
        asset_type="toolbitlibrary")))


def list_toolbits():
    """List available ToolBits with user assets taking precedence over built-ins."""
    return tuple(sorted({
        str(AssetUri.build(asset_type="toolbit", asset_id=uri.asset_id))
        for store in _STORES
        for uri in cam_assets.list_assets(asset_type="toolbit", store=store)
    }))


def _load_entry(number, tool_uri):
    tool_id = str(tool_uri)
    name = tool_uri.asset_id
    shape = ""
    tool = None
    issues = []
    if not cam_assets.exists(tool_uri, store=_STORES):
        issues.append(f"Tool {number}: missing {tool_id}")
    else:
        try:
            tool = _read_object(tool_uri)
            tool_name = tool.get("name", name)
            shape_uri = _reference("toolbitshape", tool.get("shape"))
            shape_name = tool.get("shape-type", shape_uri.asset_id)
            if not isinstance(tool_name, str) or not isinstance(shape_name, str):
                raise ValueError("Tool name and shape type must be strings.")
            name, shape = tool_name, shape_name
            if not cam_assets.exists(shape_uri, store=_STORES):
                issues.append(f"Tool {number}: missing {shape_uri}")
        except (ValueError, UnicodeError) as error:
            issues.append(f"Tool {number}: {error}")
    return ToolEntry(number, tool_id, name, shape), tool, tuple(issues)


def load_tool_entry(uri, number):
    """Load a usable existing ToolBit as an entry, without changing any library."""
    uri = AssetUri(str(uri))
    if uri.asset_type != "toolbit":
        raise ValueError("Select a ToolBit asset.")
    uri = AssetUri.build(asset_type="toolbit", asset_id=uri.asset_id)
    entry, _, issues = _load_entry(number, uri)
    if issues:
        raise ValueError("Cannot add ToolBit: " + "; ".join(issues))
    return entry


def iso_tool_definition(shape, size, radius, direction):
    """Apply supported ISO selections to the bundled native ToolBit definition."""
    if shape not in ("C", "D", "S", "T"):
        raise ValueError("Tool creation supports C, D, S and T shapes.")
    if size not in iso.SHAPE_SIZES[shape]:
        raise ValueError("Choose a supported insert size.")
    if radius not in iso.NOSE_RADII or iso.NOSE_RADII[radius] <= 0:
        raise ValueError("Tool creation requires a non-zero nose radius.")
    if direction not in ("L", "R", "N"):
        raise ValueError("Choose L, R or N insert direction.")
    tools = Path(__file__).resolve().parent.parent / "Tools"
    with (tools / "Bit" / f"iso_shape_{shape.lower()}.fctb").open() as source:
        attributes = json.load(source)
    parameters = attributes["parameter"]
    parameters["EdgeLength"] = f"{iso.get_edge_length(shape, size)} mm"
    parameters["TipAngle"] = f"{iso.get_tip_angle(shape)} deg"
    parameters["TipRadius"] = f"{iso.get_radius_value(radius)} mm"
    rotation = FreeCAD.Units.Quantity(parameters["Rotation"]).Value
    if direction == "L":
        rotation = -rotation
    elif direction == "N":
        rotation = 0
    parameters["Rotation"] = f"{rotation} deg"
    attributes["name"] = f"{shape}---{size}--{radius}--{direction}"
    return attributes, tools / "Shape" / attributes["shape"]


def validate_iso_template(shape_path, parameters, *, preview=False):
    """Check a recomputed solid and XZ profile without requiring an active job."""
    import Part
    from PathTurnScripts import PathTurnAddonHelpers as helpers

    if FreeCAD.Units.Quantity(parameters["TipRadius"]).Value <= 0:
        raise ValueError("Tool creation requires a non-zero nose radius.")
    active = FreeCAD.ActiveDocument
    template = FreeCAD.newDocument("TurningToolTemplate", hidden=True)
    try:
        template.load(str(shape_path))
        bags = template.getObjectsByLabel("Attributes")
        if len(bags) != 1:
            raise ValueError("The insert template must have one Attributes object.")
        if not all(field in bags[0].PropertiesList for field in _ISO_UNITS):
            raise ValueError("The ToolShape does not expose the supported ISO dimensions.")
        for name, value in parameters.items():
            if name in bags[0].PropertiesList:
                setattr(bags[0], name, FreeCAD.Units.Quantity(value))
        template.recompute()
        errors = [obj.getStatusString() for obj in template.Objects if "Invalid" in obj.State]
        if errors:
            raise ValueError("The selected insert dimensions cannot form a valid tool: " + "; ".join(errors))
        solid = template.Body.Shape
        if solid.isNull() or not solid.isValid() or len(solid.Solids) != 1:
            raise ValueError("The selected insert dimensions cannot form a valid solid.")
        helpers.getToolSegments(solid)
        if preview:
            box = solid.BoundBox
            corners = [
                FreeCAD.Vector(radial, box.Center.y, axial)
                for radial, axial in (
                    (box.XMin - 1, box.ZMin - 1),
                    (box.XMax + 1, box.ZMin - 1),
                    (box.XMax + 1, box.ZMax + 1),
                    (box.XMin - 1, box.ZMax + 1),
                )
            ]
            plane = Part.Face(Part.makePolygon(corners + [corners[0]]))
            outlines = tuple(
                tuple((point.x, point.z) for point in edge.discretize(Deflection=0.01))
                for edge in solid.section(plane).Edges)
            if not outlines:
                raise ValueError("The ToolShape has no preview section.")
            return outlines
    except Part.OCCError as error:
        raise ValueError(str(error)) from error
    finally:
        FreeCAD.closeDocument(template.Name)
        FreeCAD.setActiveDocument(active.Name if active else "")


def iso_tool_preview(snapshot, values):
    """Return plain XZ outlines from the stored shape without publishing assets."""
    parameters = dict(snapshot.attributes["parameter"])
    for field, unit in _ISO_UNITS.items():
        parameters[field] = f"{values[field]} {unit}"
    _iso_values(dict(snapshot.attributes, name=values["name"], parameter=parameters))
    with TemporaryDirectory() as directory:
        shape_path = Path(directory) / "insert.fcstd"
        shape_path.write_bytes(snapshot.shape_data)
        return validate_iso_template(shape_path, parameters, preview=True)


def create_iso_tool(shape, size, radius, direction, number):
    """Publish a validated native ToolBit; library membership is saved separately."""
    attributes, shape_path = iso_tool_definition(shape, size, radius, direction)
    tool_uri = AssetUri.build(asset_type="toolbit", asset_id=str(uuid4()))
    shape_uri = _reference("toolbitshape", attributes["shape"])
    entry = ToolEntry(number, str(tool_uri), attributes["name"], shape_uri.asset_id)
    if cam_assets.exists(tool_uri, store=_STORES):
        raise FileExistsError("The generated ToolBit identity is already in use.")
    shape_data = shape_path.read_bytes()
    shape_exists = cam_assets.exists(shape_uri, store=_STORES)
    if shape_exists and cam_assets.get_raw(shape_uri, store=_STORES) != shape_data:
        raise ValueError("An existing shape differs from the bundled template: " + str(shape_uri))
    validate_iso_template(shape_path, attributes["parameter"])
    tool_data = json.dumps(attributes, indent=2, allow_nan=False).encode("utf-8")
    if not shape_exists:
        cam_assets.add_raw(shape_uri.asset_type, shape_uri.asset_id, shape_data, store="local")
    cam_assets.add_raw(tool_uri.asset_type, tool_uri.asset_id, tool_data, store="local")
    return entry


def load_iso_form():
    """Load the shared insert form through FreeCAD's native Qt loader."""
    import FreeCADGui

    path = Path(__file__).resolve().parent.parent / "Gui/Resources/panels/DlgTurnToolHelper.ui"
    return FreeCADGui.PySideUic.loadUi(str(path))


def job_choices():
    """Return active-document job identities and a selection-aware default."""
    import Path.Main.Job as jobs

    document = FreeCAD.ActiveDocument
    available = jobs.Instances()
    selected = set()
    if FreeCAD.GuiUp:
        import FreeCADGui
        import PathScripts.PathUtils as utils

        selected = {
            job.Name
            for obj in FreeCADGui.Selection.getSelection()
            if obj.Document == document
            for job in [utils.findParentJob(obj)]
            if job in available
        }
    preferred = next(iter(selected)) if len(selected) == 1 else (
        available[0].Name if len(available) == 1 else "")
    return (
        document.Name if document else None,
        tuple((job.Name, job.Label) for job in available), preferred,
    )


def _job(document_name, job_name):
    import Path.Main.Job as jobs

    document = FreeCAD.ActiveDocument
    if document is None or document.Name != document_name:
        raise ValueError("Choose a CAM job in the active document.")
    job = document.getObject(job_name) if job_name else None
    if job is None or not hasattr(job, "Proxy") or not isinstance(job.Proxy, jobs.ObjectJob):
        raise ValueError("Choose a CAM job in the active document.")
    return job


def job_add_problem(document_name, job_name, number):
    """Report cheap job/number checks without loading geometry or mutating a job."""
    try:
        job = _job(document_name, job_name)
    except ValueError as error:
        return str(error)
    if job.Document.HasPendingTransaction:
        return "Finish the current document edit before adding a turning tool."
    if type(number) is not int or not 1 <= number <= 10000:
        return "The job tool number must be between 1 and 10000."
    if any(controller.ToolNumber == number for controller in job.Tools.Group):
        return f"Tool number {number} is already in use in this job. Renumber the library row first."
    return None


def add_to_job(entry, document_name, job_name):
    """Copy a stored ToolBit into a job in one undo step, without changing its asset."""
    import Part
    import Path.Tool.Controller as controllers
    from PathTurnScripts import PathTurnAddonHelpers as helpers
    from PathTurnScripts import PathTurnToolBit as bridge

    problem = job_add_problem(document_name, job_name, entry.number)
    if problem:
        raise ValueError(problem)
    job = _job(document_name, job_name)
    document = job.Document
    uri = AssetUri(entry.tool_id)
    if uri.asset_type != "toolbit":
        raise ValueError("Select a ToolBit asset.")
    attributes = _read_object(uri)
    if attributes.get("version") != 2 or not isinstance(attributes.get("parameter"), dict):
        raise ValueError("Expected a version 2 native ToolBit with parameters.")
    shape_uri = _reference("toolbitshape", attributes.get("shape"))
    shape_data = cam_assets.get_raw(shape_uri, store=_STORES)
    with TemporaryDirectory() as directory:
        shape_path = Path(directory) / (PurePosixPath(shape_uri.asset_id).name + ".fcstd")
        shape_path.write_bytes(shape_data)
        staging = FreeCAD.newDocument("TurningToolStaging", hidden=True)
        staging.UndoMode = 0
        try:
            staged_tool = bridge.create_tool(shape_path, attributes, staging)
            staging.recompute()
            if any("Invalid" in obj.State for obj in staging.Objects):
                raise ValueError("FreeCAD could not recompute the selected ToolBit.")
            solid = staged_tool.Shape
            if solid.isNull() or not solid.isValid() or len(solid.Solids) != 1:
                raise ValueError("The selected ToolBit must form one valid solid.")
            helpers.getToolSegments(solid)
            FreeCAD.setActiveDocument(document.Name)
            problem = job_add_problem(document_name, job_name, entry.number)
            if problem:
                raise ValueError(problem)
            document.openTransaction("Add turning tool from library")
            committed = False
            try:
                tool = document.copyObject(staged_tool, True)
                if tool.ViewObject:
                    tool.ViewObject.Visibility = False
                controller = controllers.Create(
                    name="TC: " + tool.Label, tool=tool, toolNumber=entry.number)
                job.Proxy.addToolController(controller)
                document.recompute()
                document.commitTransaction()
                committed = True
            finally:
                if not committed:
                    document.abortTransaction()
        except Part.OCCError as error:
            raise ValueError(str(error)) from error
        finally:
            FreeCAD.closeDocument(staging.Name)
            FreeCAD.setActiveDocument(document.Name)
    if FreeCAD.GuiUp:
        import FreeCADGui

        FreeCADGui.Selection.clearSelection()
        FreeCADGui.Selection.addSelection(controller)
    return controller


def load_library(uri):
    """Load membership and metadata without discarding unresolved entries."""
    uri = AssetUri(str(uri))
    if uri.asset_type != "toolbitlibrary":
        raise ValueError("Select a tool library asset.")
    return _snapshot(uri, _read_object(uri))


def _snapshot(uri, attributes):
    if attributes.get("version") != 1 or not isinstance(attributes.get("tools"), list):
        raise ValueError("Expected a version 1 FreeCAD tool library with a tools list.")

    table = ToolLibrary()
    tools = {}
    issues = []
    for member in attributes["tools"]:
        if not isinstance(member, dict):
            raise ValueError("Library membership must contain tool objects.")
        tool_uri = _reference("toolbit", member.get("path"))
        entry, tool, tool_issues = _load_entry(member.get("nr"), tool_uri)
        if tool is not None:
            tools[entry.tool_id] = tool
        issues.extend(tool_issues)
        table.add(entry)

    name = attributes.get("label", uri.asset_id)
    if not isinstance(name, str):
        raise ValueError("Library label must be a string.")
    return LibrarySnapshot(str(uri), name, table, attributes, tools, tuple(issues))


def create_library(name):
    """Create an empty native library without replacing existing assets."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Library name must be a non-empty string.")
    uri = AssetUri.build(asset_type="toolbitlibrary", asset_id=str(uuid4()))
    attributes = {"version": 1, "label": name.strip(), "tools": []}
    snapshot = _snapshot(uri, attributes)
    saved_uri = cam_assets.add_raw(
        uri.asset_type, uri.asset_id,
        json.dumps(attributes, indent=2, allow_nan=False).encode("utf-8"),
        store="local",
    )
    snapshot.uri = str(saved_uri)
    return snapshot


def save_library(snapshot, table):
    """Save proposed membership, leaving the loaded snapshot unchanged."""
    if snapshot.issues:
        raise ValueError("Resolve library dependency issues before saving.")
    uri = AssetUri(snapshot.uri)
    if uri.asset_type != "toolbitlibrary" or not cam_assets.exists(uri, store="local"):
        raise ValueError("Only an existing user library can be updated.")
    if _read_object(uri) != snapshot.attributes:
        raise ValueError("Library changed since loading. Reload before saving.")

    previous = {
        str(_reference("toolbit", member["path"])): member
        for member in snapshot.attributes["tools"]
    }
    attributes = deepcopy(snapshot.attributes)
    attributes["tools"] = []
    for entry in table.entries:
        tool_uri = AssetUri(entry.tool_id)
        if tool_uri.asset_type != "toolbit":
            raise ValueError("Library entries must reference ToolBit assets.")
        member = deepcopy(previous.get(entry.tool_id, {
            "path": f"{tool_uri.asset_id}.fctb",
        }))
        member["nr"] = entry.number
        attributes["tools"].append(member)

    updated = _snapshot(uri, attributes)
    if updated.issues:
        raise ValueError("Cannot save library: " + "; ".join(updated.issues))
    if updated.table.entries != table.entries:
        raise ValueError("Save ToolBit definition edits separately from library membership.")
    cam_assets.add_raw(
        uri.asset_type, uri.asset_id,
        json.dumps(attributes, indent=2, allow_nan=False).encode("utf-8"),
        store="local",
    )
    return updated


def selected_library():
    """Read the addon's preference without changing FreeCAD's library selection."""
    settings = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/TurningAddon")
    return settings.GetString("ToolLibrary", "")


def set_selected_library(uri):
    """Remember a loadable library, or clear the addon's selection with an empty string."""
    selected = load_library(uri).uri if uri != "" else ""
    settings = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/TurningAddon")
    settings.SetString("ToolLibrary", selected)