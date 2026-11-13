# FreeCAD Turning Addon ![Python package](https://github.com/dubstar-04/FreeCAD_Turning_Addon/workflows/Python%20package/badge.svg?branch=master)
A FreeCAD CAM Addon to encourage the development of CNC turning functionality for the CAM workbench.

| :warning: WARNING: Turning Addon is currently experimental / proof of concept and only suitable for testing. |

## Description
This addon appears under **CAM -> CAM Addons -> Turning Addon** and allows the creation of
turning paths for use with a CNC lathe. The menu is restored whenever the CAM
workbench is activated. It uses an externally installed
[LibLathe](https://github.com/dubstar-04/LibLathe) library; no library is bundled.

## Features
* Turning Roughing operation: external/internal, axial `-Z`/`+Z` or `Radial`
* Turning Profiling operation: external/internal, axial `-Z`/`+Z` or `Radial`
* Turning Parting operation
* Turning Thread operation
* Turning Tool Library


## Requirements
* FreeCAD v1.1 or later with the CAM workbench
* The matching LibLathe `feature/architecture` build installed in FreeCAD's
  Python environment, including its native extensions. Released LibLathe
  packages do not yet provide this branch's architecture API. Restart FreeCAD
  after updating LibLathe; updating the Addon alone does not update the library.

## Tool management

Use the **Turning Tool Library** to create and edit tools from native templates,
preview their geometry and add Tool Controllers to a CAM job. Tool geometry and
parameters are stored with the native ToolBit.

New paths retain a compatible inherited Tool Controller when available.
Otherwise, a compatible controller is selected from the job. Opening an existing
path with an incompatible controller selects an available compatible controller
and reports the replacement. If none exists, add a suitable Tool Controller
to the job before editing.

The user is responsible for selecting the correct tool, datum, physical
orientation, feeds, spindle settings and coolant.

## Containment

Containment visually sets the limits for operations.

## Remaining-stock guide

The Containment page shows predicted remaining stock in amber. Choose
**Stock before operation** or **Stock after operation**, and use
**Show remaining stock** to toggle the preview. Apply/recompute changes to
keep the results up to date.


## Feedback
If you have feedback or need to report bugs please participate on the related [Path Forum](https://forum.freecadweb.org/viewtopic.php?f=15&t=30563&start=0).

## Disclaimer
This is an experimental tool for development purposes and must be used at your own risk. Machine tools are dangerous and the author of this tool will not be responsible for any damage or personal injury caused by using incorrect tool paths or machining parameters.
