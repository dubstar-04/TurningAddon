"""Native FreeCAD asset access for the independent turning tool table."""

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
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
from .PathTurnToolTable import ToolEntry, ToolLibrary


_STORES = ("local", "builtin")


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
    fields: dict = None

    @property
    def shape_name(self):
        return self.attributes.get(
            "shape-type", _reference("toolbitshape", self.attributes["shape"]).asset_id)


def _custom_snapshot(uri, attributes, shape_data):
    from PathTurnScripts.PathTurnToolBit import custom_shape_from_bytes

    if attributes.get("version") != 2 or not isinstance(attributes.get("parameter"), dict):
        raise ValueError("Expected a version 2 native ToolBit with parameters.")
    shape = custom_shape_from_bytes(shape_data, _reference("toolbitshape", attributes["shape"]).asset_id)
    values = {"name": attributes["name"]}
    for name, field in shape.fields.items():
        value = attributes["parameter"].get(name, shape.get_parameter(name))
        if not field["readonly"]:
            shape.set_parameter(name, value)
        value = shape.get_parameter(name)
        values[name] = str(value) if isinstance(value, FreeCAD.Units.Quantity) else value
    return ToolBitSnapshot(str(uri), attributes, values, shape_data, shape.fields)


def custom_tool_preset(shape_path):
    """Import any conforming native shape without a shape-specific Python schema."""
    from PathTurnScripts.PathTurnToolBit import custom_shape_from_bytes

    path = Path(shape_path)
    if path.suffix.lower() != ".fcstd":
        raise ValueError("Select a native FreeCAD .fcstd ToolShape.")
    data = path.read_bytes()
    shape = custom_shape_from_bytes(data, path.stem)
    parameters = {name: str(value) if isinstance(value, FreeCAD.Units.Quantity) else value
                  for name, value in shape.get_parameters().items()}
    attributes = {"version": 2, "name": path.stem, "shape-type": "TurningCustom",
                  "shape": f"{path.stem}_{sha256(data).hexdigest()}.fcstd",
                  "parameter": parameters, "attribute": {}}
    return _custom_snapshot("", attributes, data)


def tool_shape_presets():
    """Discover the bundled file-defined starting tools."""
    presets = []
    tools = Path(__file__).resolve().parent.parent / "Tools"
    for path in sorted((tools / "Bit").glob("*.fctb")):
        definition = json.loads(path.read_text(encoding="utf-8"))
        if (definition.get("shape-type") != "TurningCustom"
                or definition.get("attribute", {}).get("deprecated", False)):
            continue
        filename = definition["shape"]
        if Path(filename).name != filename:
            raise ValueError(f"Bundled ToolShape must be a filename: {filename}")
        snapshot = custom_tool_preset(tools / "Shape" / filename)
        attributes = deepcopy(definition)
        attributes["shape"] = snapshot.attributes["shape"]
        presets.append(_custom_snapshot("", attributes, snapshot.shape_data))
    return tuple(presets)


def load_custom_tool(uri):
    """Load file-defined custom controls from the stored native shape."""
    uri = AssetUri(str(uri))
    if uri.asset_type != "toolbit" or not cam_assets.exists(uri, store="local"):
        raise ValueError("Only an existing user ToolBit can be edited in place.")
    attributes = _read_object(uri)
    if attributes.get("shape-type") != "TurningCustom":
        raise ValueError("Select a custom turning ToolBit.")
    data = cam_assets.get_raw(_reference("toolbitshape", attributes["shape"]), store=_STORES)
    return _custom_snapshot(uri, attributes, data)


def load_tool_definition(uri):
    """Load an editable file-defined turning ToolBit."""
    if _read_object(AssetUri(str(uri))).get("shape-type") != "TurningCustom":
        raise ValueError("Only file-defined turning tools can be edited. "
                         "Recreate legacy ISO tools from the bundled ISO templates.")
    return load_custom_tool(uri)


def _updated_custom_definition(snapshot, values):
    from PathTurnScripts.PathTurnToolBit import custom_shape_from_bytes

    if set(values) != set(snapshot.values):
        raise ValueError("Expected the complete native custom-tool definition.")
    if not isinstance(values["name"], str) or not values["name"].strip():
        raise ValueError("ToolBit name must be a non-empty string.")
    attributes = deepcopy(snapshot.attributes)
    attributes["name"] = values["name"]
    shape = custom_shape_from_bytes(snapshot.shape_data, "custom")
    for name, field in snapshot.fields.items():
        if field["readonly"]:
            if values[name] != snapshot.values[name]:
                raise ValueError(f"{name} is defined by the native shape and is read-only.")
        else:
            shape.set_parameter(name, values[name])
            if values[name] != snapshot.values[name]:
                attributes["parameter"][name] = values[name]
    return attributes


def custom_tool_preview(snapshot, values):
    """Validate the native solid and preview its true section and calculated properties."""
    import Part
    from PathTurnScripts import PathTurnAddonHelpers as helpers

    attributes = _updated_custom_definition(snapshot, values)
    active = FreeCAD.ActiveDocument
    document = FreeCAD.newDocument("TurningCustomPreview", hidden=True)
    try:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "shape.fcstd"
            path.write_bytes(snapshot.shape_data)
            document.load(str(path))
        bag = document.getObjectsByLabel("Attributes")[0]
        for name, field in snapshot.fields.items():
            if not field["readonly"]:
                setattr(bag, name, attributes["parameter"].get(name, snapshot.values[name]))
        document.recompute()
        diameter = float(bag.Diameter)
        if not math.isfinite(diameter) or diameter <= 0:
            raise ValueError("CAM Diameter must be positive and finite.")
        solid = document.Body.Shape
        if (any("Invalid" in obj.State for obj in document.Objects)
                or solid.isNull() or not solid.isValid() or len(solid.Solids) != 1):
            raise ValueError("The custom tool must form one valid solid.")
        helpers.getToolSegments(solid)
        bounds = solid.BoundBox
        corners = [FreeCAD.Vector(radial, bounds.Center.y, axial) for radial, axial in (
            (bounds.XMin - 1, bounds.ZMin - 1), (bounds.XMax + 1, bounds.ZMin - 1),
            (bounds.XMax + 1, bounds.ZMax + 1), (bounds.XMin - 1, bounds.ZMax + 1))]
        section = solid.section(Part.Face(Part.makePolygon(corners + [corners[0]])))
        outlines = tuple(tuple((point.x, point.z) for point in edge.discretize(Deflection=0.01))
                         for edge in section.Edges)
        if not outlines:
            raise ValueError("The custom tool has no XZ preview section.")
        calculated = {name: str(bag.getPropertyByName(name)) for name, field in snapshot.fields.items()
                      if field["readonly"]}
        return {"outlines": outlines, "nose_centre": None, "active_tip": None,
                "fit_radius": max(math.hypot(*point) for edge in outlines for point in edge),
                "calculated": calculated}
    except Part.OCCError as error:
        raise ValueError(str(error)) from error
    finally:
        FreeCAD.closeDocument(document.Name)
        FreeCAD.setActiveDocument(active.Name if active else "")


def create_custom_tool(snapshot, number, *, values=None):
    """Publish a file-defined custom ToolBit and native ToolShape into the asset library."""
    values = snapshot.values if values is None else values
    attributes = _updated_custom_definition(snapshot, values)
    custom_tool_preview(snapshot, values)
    tool_uri = AssetUri.build(asset_type="toolbit", asset_id=str(uuid4()))
    shape_uri = _reference("toolbitshape", attributes["shape"])
    entry = ToolEntry(number, str(tool_uri), attributes["name"], attributes["shape-type"])
    if cam_assets.exists(tool_uri, store=_STORES):
        raise FileExistsError("The generated ToolBit identity is already in use.")
    if cam_assets.exists(shape_uri, store=_STORES):
        if cam_assets.get_raw(shape_uri, store=_STORES) != snapshot.shape_data:
            raise ValueError("A different ToolShape already uses this identity.")
    else:
        cam_assets.add_raw(shape_uri.asset_type, shape_uri.asset_id, snapshot.shape_data, store="local")
    cam_assets.add_raw(tool_uri.asset_type, tool_uri.asset_id,
                       json.dumps(attributes, indent=2, allow_nan=False).encode("utf-8"), store="local")
    return entry


def save_custom_tool(snapshot, values):
    """Preserve shared native shapes, unchanged units, metadata and stale-edit checks."""
    uri = AssetUri(snapshot.uri)
    if uri.asset_type != "toolbit" or not cam_assets.exists(uri, store="local"):
        raise ValueError("Only an existing user ToolBit can be edited in place.")
    if _read_object(uri) != snapshot.attributes:
        raise ValueError("ToolBit changed since loading. Reload before saving.")
    if cam_assets.get_raw(_reference("toolbitshape", snapshot.attributes["shape"]), store=_STORES) != snapshot.shape_data:
        raise ValueError("ToolShape changed since loading. Reload before saving.")
    attributes = _updated_custom_definition(snapshot, values)
    if attributes == snapshot.attributes:
        return snapshot
    custom_tool_preview(snapshot, values)
    cam_assets.add_raw(uri.asset_type, uri.asset_id,
                       json.dumps(attributes, indent=2, allow_nan=False).encode("utf-8"), store="local")
    return _custom_snapshot(uri, attributes, snapshot.shape_data)


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
    if FreeCAD.GuiUp:
        import FreeCADGui

        gui_document = FreeCADGui.getDocument(job.Document.Name)
        if gui_document.getInEdit() is not None or FreeCADGui.Control.activeDialog():
            return "Finish the current document edit before adding a turning tool."
    if type(number) is not int or not 1 <= number <= 10000:
        return "The job tool number must be between 1 and 10000."
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
