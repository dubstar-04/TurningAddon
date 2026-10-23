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

Turning uses positive radial X coordinates and the operation's minimum/maximum
diameters and start/final depths as stock limits. Tools use their actual XZ
insert section, including its existing orientation, rather than an inferred ISO
shape. Position the tool geometry appropriately for the XZ turning plane.
Tool sections may contain straight lines and circular arcs and must form one
closed outline.

All turning operations use the part's full rotational envelope about the Z axis,
not a single viewing direction. This preserves material around partial features,
which must be finished separately. Rotational line/arc profiles retain their
original geometry. Other profiles use an adaptive radial mesh envelope with a
0.01 mm approximation allowance, including a small outward/axial margin. Before
accepting either profile, the add-on revolves it and checks that it contains the
complete model. Unsupported or unverified profiles stop generation with an error.
The four most recent profiles are cached across operations; changing the model
geometry or placement invalidates its cached result. Complex curved models take
longer to extract initially, but tool and cutting-parameter changes reuse the
verified geometry.

## Requirements
* FreeCAD v1.0 or later with the CAM workbench
* Path Toolbits (Legacy tools are not supported)
* Python3
* Qt5
* LibLathe 0.0.7, installed in the Python environment used by FreeCAD

## Installation
1. Clone this repository or extract its source ZIP into your
   [FreeCAD `Mod/` directory](https://www.freecadweb.org/wiki/Installing_more_workbenches).
2. Install LibLathe through your system package manager or PyPI, using the same
   Python environment as FreeCAD. The Addon Manager dependency is `liblathe`.
   For a matching system Python:

   ```sh
   python3 -m pip install --user "liblathe==0.0.7"
   ```

   For the FreeCAD Flatpak, use its Python interpreter rather than the host's:

   ```sh
   flatpak run --command=python org.freecad.FreeCAD -m pip install --user "liblathe==0.0.7"
   ```

3. Restart FreeCAD and activate the CAM workbench.
4. Use **CAM -> CAM Addons -> Turning Addon** to create turning operations.

The add-on uses normal Python package discovery; it does not add a bundled
library or another source checkout to `sys.path`. If startup reports a missing
LibLathe package, install it into FreeCAD's Python environment and restart.
On startup, the add-on prints the loaded LibLathe version and module path in
FreeCAD's Report view so you can identify which installation is being used.

## Feedback
If you have feedback or need to report bugs please participate on the related [Path Forum](https://forum.freecadweb.org/viewtopic.php?f=15&t=30563&start=0).

## Disclaimer
This is an experimental tool for development purposes and must be used at your own risk. Machine tools are dangerous and the author of this tool will not be responsible for any damage or personal injury caused by using incorrect tool paths or machining parameters.
