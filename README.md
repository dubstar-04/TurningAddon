# FreeCAD Turning Addon ![Python package](https://github.com/dubstar-04/FreeCAD_Turning_Addon/workflows/Python%20package/badge.svg?branch=master)
A FreeCAD CAM Addon to encourage the development of CNC turning functionality for the CAM workbench.

| :warning: WARNING: Turning Addon is currently experimental / proof of concept and only suitable for testing. |

## Description
This addon appears under **CAM -> CAM Addons -> Turning Addon** and allows the creation of
turning paths for use with a CNC lathe. The menu is restored whenever the CAM
workbench is activated. This addon includes a pinned version of
[LibLathe](https://github.com/dubstar-04/LibLathe) as a submodule; the standalone
operations require that version, rather than a separately installed newer library.

## Features
* Turning Roughing operation
* Turning Facing operation
* Turning Profiling operation
* Turning Parting operation

## Requirements
* FreeCAD v1.0 or later with the CAM workbench
* Path Toolbits (Legacy tools are not supported)
* Python3
* Qt5

## Installation
1. Clone this repository with `git clone --recurse-submodules` into your
   [FreeCAD `Mod/` directory](https://www.freecadweb.org/wiki/Installing_more_workbenches).
   Source ZIP downloads do not include the LibLathe submodule.
2. Restart FreeCAD and activate the CAM workbench.
3. Use **CAM -> CAM Addons -> Turning Addon** to create turning operations.

Note: If the LibLathe folder inside the addon is empty or missing you may need to add the submodule manually: `git submodule update --init --recursive`

## Feedback
If you have feedback or need to report bugs please participate on the related [Path Forum](https://forum.freecadweb.org/viewtopic.php?f=15&t=30563&start=0).

## Disclaimer
This is an experimental tool for development purposes and must be used at your own risk. Machine tools are dangerous and the author of this tool will not be responsible for any damage or personal injury caused by using incorrect tool paths or machining parameters.
