# FreeCAD Turning Addon ![Python package](https://github.com/dubstar-04/FreeCAD_Turning_Addon/workflows/Python%20package/badge.svg?branch=master)
A FreeCAD CAM Addon to encourage the development of CNC turning functionality for the CAM workbench.

| :warning: WARNING: Turning Addon is currently experimental / proof of concept and only suitable for testing. |

## Description
This addon appears under **CAM -> CAM Addons -> Turning Addon** and allows the creation of
turning paths for use with a CNC lathe. It uses an externally installed
[LibLathe](https://github.com/dubstar-04/LibLathe) library; no library is bundled.

## Features
* Turning Roughing
* Turning Profiling
* Turning Parting
* Turning Threading
* Turning Drilling
* Turning Tool Library
* CAM Simulation with turning-profile and generic dexel engines

## Requirements
* FreeCAD v1.1 or later with the CAM workbench

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

**Stock before operation** or **Stock after operation**

## Simulation

Open **CAM -> CAM Addons -> Turning Addon -> Simulation**, select the job,
operations and engine, then use the timeline to play, pause, seek or step 1 mm
forwards/backwards. Both turning and milling are retained. The
`turning_profile_engine` uses NumPy and requires complete cylindrical stock
centred on the Z spindle; `dexel_engine` also supports milling.

Thread operations show tool motion only and leave the simulated stock unchanged.
Helical thread geometry and turning arcs/G33/G76 commands are not supported.
Close the simulation panel before editing the job or switching documents.

The simulator is imported from [FreeCAD-CAM-Sim](https://github.com/dubstar-04/FreeCAD-CAM-Sim).
Its original GPL-2.0 licence and source notices are retained separately in
[PathTurnSimulation/LICENSE](PathTurnSimulation/LICENSE); the existing addon
code retains its LGPL-2.1 licence.

Simulator tests: `python3 -m pytest -q tests/simulation`.

## Disclaimer
This is an experimental tool for development purposes and must be used at your own risk. Machine tools are dangerous and the author of this tool will not be responsible for any damage or personal injury caused by using incorrect tool paths or machining parameters.
