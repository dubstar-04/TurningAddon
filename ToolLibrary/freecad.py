"""Native FreeCAD asset access for the independent turning tool table."""

from copy import deepcopy
from dataclasses import dataclass
import json
import os
from pathlib import PurePosixPath
from uuid import uuid4

import FreeCAD
import Path.Preferences as preferences
from Path.Tool.assets import AssetUri
from Path.Tool.camassets import cam_assets

from .library import ToolEntry, ToolLibrary


_STORES = ("local", "builtin")


@dataclass
class LibrarySnapshot:
    uri: str
    name: str
    table: ToolLibrary
    attributes: dict
    tools: dict
    issues: tuple


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