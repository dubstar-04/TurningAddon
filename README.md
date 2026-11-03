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
* Turning Tool Library: create and edit C, D, S and T ToolBits and add them to a CAM job

Paths follow the part's full rotating outline. Profiles use fast native extraction
where possible, are checked before use, and are reused for faster updates.

In **Turning Tool Library**, create a ToolBit, select a job, then **Add to job**.
Set feeds and spindle speed in the new controller before use. Other shapes and
sharp noses (`00`) remain reference-only for ISO creation.

**New ISO ToolBit** and **Edit ToolBit** use the same form for dimensions, mounting
angle, tool reference and native preview. Creation adds C/D/S/T ISO presets;
editing prefills the saved values without inferring an ISO code. Numeric values
and the name can be adjusted before confirming **Create ToolBit** or **Save**.
The square preview keeps its axes centred and uses a consistent fit scale as the
mounting angle changes, refitting when tool dimensions or the reference change.

**Tool reference** offers **Stored origin** (the theoretical sharp tip in the bundled
shapes) and **Nose centre**. The native `NoseCentre` parameter offsets the sketch
before the solid is built. The preview, LibLathe outline and simulation tool shape
therefore share the same origin; no separate operation-side offset is applied.
**Flip X view** only changes the preview. It does not change the saved tool or paths.

Existing C/D/S/T ToolBits without `NoseCentre` open with **Stored origin** selected.
Only confirming **Save** adds the native parameter and references an updated
template where needed. Opening, previewing or cancelling does not change assets.
The update preserves the ToolBit identity, unchanged dimensions and extra metadata;
existing shared shapes and other ToolBits are left untouched.

## Requirements
* FreeCAD v1.1 or later with the CAM workbench
* Path Toolbits (Legacy tools are not supported)
* Python3
* FreeCAD's Qt/PySide runtime
* LibLathe 0.0.8 or later, installed in the Python environment used by FreeCAD
* `packaging`, for checking the LibLathe version before nose-centred machining

## Installation
1. Clone this repository or extract its source ZIP into your
   [FreeCAD `Mod/` directory](https://www.freecadweb.org/wiki/Installing_more_workbenches).
2. Install LibLathe through your system package manager or PyPI, using the same
   Python environment as FreeCAD. The Addon Manager dependency is `liblathe`.
   For a matching system Python:

   ```sh
   python3 -m pip install --user 'liblathe>=0.0.8' packaging
   ```

   For the FreeCAD Flatpak, use its Python interpreter rather than the host's:

   ```sh
   flatpak run --command=python org.freecad.FreeCAD -m pip install --user 'liblathe>=0.0.8' packaging
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
