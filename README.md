# FreeCAD Turning Addon ![Python package](https://github.com/dubstar-04/FreeCAD_Turning_Addon/workflows/Python%20package/badge.svg?branch=master)
A FreeCAD CAM Addon to encourage the development of CNC turning functionality for the CAM workbench.

| :warning: WARNING: Turning Addon is currently experimental / proof of concept and only suitable for testing. |

## Description
This addon appears under **CAM -> CAM Addons -> Turning Addon** and allows the creation of
turning paths for use with a CNC lathe. The menu is restored whenever the CAM
workbench is activated. It uses an externally installed
[LibLathe](https://github.com/dubstar-04/LibLathe) library; no library is bundled.

## Features
* Turning Roughing operation
* Turning Facing operation
* Turning Profiling operation
* Turning Parting operation
* Turning Tool Library: create and edit file-defined ToolBits (ISO C, D, S, T and custom) and add them to a CAM job

Paths follow the part's full rotating outline. Profiles use fast native extraction
where possible, are checked before use, and are reused for faster updates.

In **Turning Tool Library**, choose **New ToolBit** to select a base tool from a
resizable image-and-title grid. Images show each template's actual native cutting
outline, not a generic icon or a hashed asset filename. The grid lists the bundled
**ISO C rhombic 80°**, **ISO D rhombic 55°**, **ISO S square**, **ISO T triangle**
and **Custom profile** tools. Select a tile and **Choose shape**, or double-click it,
to configure the tool before saving. **Import shape...** accepts a trusted custom
`.fcstd` file. Invalid previews are reported and their tiles cannot be selected.
Opening or cancelling the picker does not publish assets.

Create a ToolBit, select a job, then **Add to job**.
Set feeds, spindle speed and spindle direction in the new controller before use.

Creating and **Edit ToolBit** use the same generic form. Its controls are
discovered from the native template's `Attributes` properties, alongside the
name and a live preview of the actual native section. Values can be adjusted
before confirming **Create ToolBit** or **Save**.

**Rotation** in the bundled ISO templates measures from the active theoretical
tip into the insert body: 0 degrees points along +Z, 90 along +X, 180 along -Z
and 270 along -X. The preview has **+X down and +Z right**, away from the chuck;
positive angles are clockwise in that view. The tip angle is the included angle
between cutting edges, not this rotation.
The library path is shown as a tooltip on the **Library** drop-down.

**Tool post** selects physical **Front (+X)** or **Rear (-X)**, independently
of rotation. Spindle speed and direction remain Tool Controller settings;
changing post does not select M3/M4. The native `ToolPost` enumeration is required.
Removed property names and old angle conventions are not migrated.

ToolBits based on the removed `IsoShape` tool type (`iso_shape_*.fctb`) are no
longer supported. They cannot be edited, and job documents containing them do
not restore. Recreate them from the bundled ISO templates.

Far-side operations pass negative-X stock and part geometry to a side-aware
LibLathe build. LibLathe reflects copies of the part, stock and actual native
tool outline into its positive-X planning frame, then restores signed paths,
arc directions and centre offsets. Returned Rear paths remain negative X:
X and I are negated, G2/G3 are swapped, and Z, K and feed are unchanged.
Front maps to LibLathe `ToolSide.NEAR`; Rear maps to `ToolSide.FAR`.
This is not an output-only X sign change, and the machine/postprocessor must
match this signed-X convention.
It does not add internal boring support. Signed-side planning is experimental:
existing defeature/clearance issues remain, and tiny native outline differences
can materially change generated passes. These checks are not machining approval.

**Compensation** in the bundled ISO templates offers **Tip Tangent** (the
intersection of the X- and Z-parallel nose-circle tangents toward the theoretical
tip), **Tip** (the theoretical sharp tip), **Tip centre** (the centre of the active
nose radius), and **Insert centre** (the nominal geometric centre of the insert).
The native `Compensation` enumeration selects the sketch origin before the
solid is built. Its dropdown is available in both the library editor and the
model-instance property editor. New ISO tools default to **Tip Tangent**;
restored instances keep their saved selection.
Tip Tangent follows the rotation quadrant. At an axis-aligned tie, tool post
selects the radial tangent (toward the spindle), and the axial tangent is
chuck-facing. Its origin is built into the native shape, not offset in the planner.
The preview, LibLathe outline and simulation tool shape
therefore share the same origin; no separate operation-side offset is applied.
The LibLathe outline uses the native mid-Y section to preserve rounded insert
arcs without projection-induced straight chords.
**Flip X view** only changes the preview. It does not change the saved tool or paths.
The datum cross marks the tool-local origin, not the spindle centre.

Only confirming **Save** changes the stored ToolBit definition.
Opening, previewing or cancelling does not change assets.
The update preserves the ToolBit identity, unchanged dimensions and extra metadata;
existing shared shapes and other ToolBits are left untouched.

## File-Defined Custom Tools

Every turning tool, including the bundled ISO tools, uses native `.fctb`
definitions, `.fcstd` ToolShapes and `.fctl` libraries. Adding a new shape
requires no Python class, registered shape name or code changes.

Choose **New ToolBit**, then a file-driven base tool, or **Import shape...** to
select a trusted `.fcstd` file.
Configure the discovered properties and
confirm **Create ToolBit**. Save the library membership, then use **Add to job**.
**Edit ToolBit** reopens the same form.
Importing or cancelling does not publish assets; saving a definition updates all
libraries that reference it, but not existing job instances.

### Native Template Contract

* The file contains a native `PartDesign::Body` named `Body`. Its label is arbitrary.
   The recomputed cutting body must be one valid solid with a supported, closed
   mid-Y XZ section. Lines and circular arcs are supported by the turning planner.
* One object is labelled `Attributes` and is a child of `Body`, like the sketch
   and pad. Include the PropertyBag in `Body.Group` so native ToolBit body copies
   retain it and its expression dependencies. Define configurable properties in
   its `Shape` property group. Names, types, descriptions, defaults and enum
   choices come from this file, not a tool-specific Python schema.
* Supported types are `App::PropertyLength`, `Distance`, `Angle`, `Float`,
   `Integer`, `Bool`, `String` and `Enumeration` (all with the `App::Property`
   prefix). Other types are rejected explicitly rather than silently discarded.
* `ToolPost` is an enumeration containing `Front` and `Rear`.
   `Compensation` is an enumeration whose choices and origin expressions are
   defined by the template. Custom tools do not inherit the ISO reference choices.
* `Diameter` must be a positive, finite `App::PropertyLength` in `Shape`.
   FreeCAD CAM reads it before executing any turning operation. Define its nominal
   cutting width or size in the native file, using an expression if appropriate.
   The bundled profile derives it from `TipWidth`. This CAM metadata does not
   replace the actual cutting outline or apply a geometry offset.
* Use native expressions to connect properties to geometry. Expression-driven
   and read-only properties are displayed but cannot be overridden in the form;
   calculated values update with the native geometry. Hidden fields stay hidden.
* ToolBit identity and geometry names such as `Shape`, `Placement`, `Proxy`,
   `ShapeID` and `ToolBitID` are reserved. Do not use them as custom parameters.

The preview displays the actual native section and authored origin with +X down
and +Z right. Rotation controls appear only if the file defines an angle property;
the editor applies no inferred ISO pose, nose compensation or output offset.
Changing `ToolPost` selects a physical post; any intended geometry change must
be expressed in the native template. Spindle settings remain in the controller.

The bundled [custom profile](Tools/Shape/Custom_profile.fcstd) and
[ToolBit definition](Tools/Bit/custom_profile.fctb) provide a constrained stepped
profile example. Users can copy the native file, replace the geometry, and add
their own properties in `Attributes` without changing the addon. New shapes are
stored under content-specific identities so an existing shared shape is not
overwritten. Saved job documents embed the template for copy and reopen.
These are cutting-tool definitions, not holder or fixture collision models.

Custom tools imported before the required `Diameter` property was added retain
their original shared and embedded shapes. Re-import the updated shape, add the
new tool to the job, and select its Tool Controller on the operation. Existing
native assets and saved job instances are not silently rewritten.

### Bundled ISO C, D, S and T Tools

Each ISO insert is a [native template](Tools/Shape) (`Iso_C.fcstd`, `Iso_D.fcstd`,
`Iso_S.fcstd`, `Iso_T.fcstd`) with a matching [ToolBit definition](Tools/Bit)
(`iso_c.fctb` and so on). They use the same generic editor as any custom tool,
and can also be imported directly. No shape-specific Python class, editor
controls or runtime ISO lookup is involved. Bundled presets are discovered from
their `.fctb` definitions and native shape files; definitions marked
`attribute.deprecated` are omitted from the grid.

`Attributes` is a child of `Body`. There is no `InsertShape` property: the file
itself defines the insert. The native file contains size, radius and thickness
choices, lookup values in `ISOData`, descriptions and expressions. `EdgeLength`,
`TipRadius` and `Thickness` are enumerations displaying codes with nominal
millimetre values, not unconstrained numeric inputs. There is no separate
`SizeCode` field. The fixed corner angle (C: 80, D: 55, S: 90, T: 60 degrees) is
internal and is not shown as a control. CAM `Diameter` is calculated but hidden
in the form. Dimensional quantities used by sketch expressions remain internal
properties. Rotation accepts unitless degrees such as `90` as well as `90 deg`.

Each template is a single sketch and pad with native tangent constraints. `00`
is drawn with a 0.01 mm nose radius because sketch arcs cannot be zero. T sizes
are inscribed-circle diameters, like C/D/S. T applies rotation and compensation
through the sketch attachment offset, so its fixed sketch only follows size and
nose radius. Rotation, post and all four compensation origins are expressed in
the native file, not corrected in the preview or planner. Tests check actual
nose-circle centres across quadrants and both posts, nominal dimensions,
rounded-insert volume, the `00` minimum radius, and copied/reopened ToolBits.

Tools created from the earlier `Experimental_*` templates keep working, because
their shapes are embedded, but they are no longer offered in the grid.

These templates are not a certified insert catalogue. The thickness list is a
subset (03, T3, 04 and 06), and arbitrary combinations are not guaranteed to
represent purchasable inserts. Invalid solids are rejected. Relief, tolerance
classes, chipbreakers, mounting holes and holders are not modelled, and full
ISO designation validation is not performed.

## Requirements
* FreeCAD v1.1 or later with the CAM workbench
* Path Toolbits (Legacy tools are not supported)
* Python3
* FreeCAD's Qt/PySide runtime
* An updated LibLathe development build providing `ToolSide.NEAR` and `ToolSide.FAR`, installed in FreeCAD's Python environment. Version 0.0.8 alone does not guarantee this API.
* `packaging`, for checking the LibLathe version before nose-centred machining

## Installation
1. Clone this repository or extract its source ZIP into your
   [FreeCAD `Mod/` directory](https://www.freecadweb.org/wiki/Installing_more_workbenches).
2. Build an updated LibLathe wheel from the matching source checkout, using a
   Python version and native runtime compatible with FreeCAD. Install that wheel
   into FreeCAD's environment. The Addon Manager dependency is `liblathe`, but
   an older release without `ToolSide` is insufficient. For matching system Python:

   ```sh
   python3 -m pip install --user --force-reinstall /path/to/liblathe-wheel.whl
   python3 -m pip install --user packaging
   ```

   For the FreeCAD Flatpak, build against its matching SDK and Python ABI, then
   use its interpreter rather than the host's. A host-built native wheel may
   require an incompatible GLIBC version:

   ```sh
   flatpak run --command=python org.freecad.FreeCAD -m pip install --user --force-reinstall /path/to/liblathe-wheel.whl
   flatpak run --command=python org.freecad.FreeCAD -m pip install --user packaging
   ```

3. Restart FreeCAD and activate the CAM workbench.
4. Use **CAM -> CAM Addons -> Turning Addon** to create turning operations.

The bundled ISO inserts use the XZ turning plane and expose the native reference
parameter. Create test ToolBits from these shapes. If a shared shape with the same
name has different contents, creation saves the bundled template under a
content-specific name and reuses it for subsequent tools. Existing shapes and
the ToolBits referencing them are not changed.

The add-on uses normal Python package discovery; it does not add a bundled
library or another source checkout to `sys.path`. If startup reports a missing
LibLathe package, install it into FreeCAD's Python environment and restart.
On startup, the add-on prints the loaded LibLathe version and module path in
FreeCAD's Report view so you can identify which installation is being used.

## Feedback
If you have feedback or need to report bugs please participate on the related [Path Forum](https://forum.freecadweb.org/viewtopic.php?f=15&t=30563&start=0).

## Disclaimer
This is an experimental tool for development purposes and must be used at your own risk. Machine tools are dangerous and the author of this tool will not be responsible for any damage or personal injury caused by using incorrect tool paths or machining parameters.
