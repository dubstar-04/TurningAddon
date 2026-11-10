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
* Turning Tool Library


While editing turning operations, Show containment displays a temporary coloured
XZ rectangle marking diameter/depth limits; it does not represent remaining stock.
The Containment panel combines signed +X/-X (radius) and +Z/-Z limits in unit-aware
spinboxes. Changes update the rectangle immediately; arrows use selected model
geometry, and right-clicking a spinbox edits its coordinate expression.
The dashed purple clearance outline adds the job's Safe Height Offset radially
(minimum 0.01 mm); actual transfers can be farther out for stock or shoulder clearance.

## Requirements
* FreeCAD v1.1 or later with the CAM workbench
* Path Toolbits (Legacy tools are not supported)
* Python3
* FreeCAD's Qt/PySide runtime

## Feedback
If you have feedback or need to report bugs please participate on the related [Path Forum](https://forum.freecadweb.org/viewtopic.php?f=15&t=30563&start=0).

## Disclaimer
This is an experimental tool for development purposes and must be used at your own risk. Machine tools are dangerous and the author of this tool will not be responsible for any damage or personal injury caused by using incorrect tool paths or machining parameters.
