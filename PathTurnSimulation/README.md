# FreeCAD Path Simulation
A FreeCAD CAM addon for previewing milling and turning tool paths, with optional
material-removal simulation.

Imported from FreeCAD-CAM-Sim at commit 9175de0. Original source notices and
the GPL-2.0 licence are retained in this package.

## Features
* Milling and turning toolpath previews
* Material-removal simulation or tool-motion-only playback
* Operation selection and colour-coded machined surfaces
* Play, pause, 1 mm step backward/forward and previous/next operation controls
* Interactive timeline for moving forwards and backwards through a job
* Centreline drilling and turning across the spindle axis
* Stock visibility toggle for previewing tool motion only
* `turning_profile_engine` for fast turning-only simulation on the 2D stock profile

## Screenshots
![Milling simulation with operation colours and timeline controls](Screenshots/milling_simulation.png)
![Turning simulation with operation colours and timeline controls](Screenshots/turning_simulation.png)

## Requirements
* FreeCAD with the CAM workbench (the legacy Path workbench is not supported)

## Installation
This simulator is distributed inside TurningAddon. Install the parent addon
into FreeCAD's `Mod/` directory and restart FreeCAD; no separate simulator
addon installation is required.

`turning_profile_engine` needs only NumPy. Full-revolution turning keeps the
stock a solid of revolution, so the engine stores radial material intervals on
0.01 mm Z slices and displays the profile revolved into a closed mesh. Profile
simplification and angular segments target a 0.01 mm display tolerance. It requires
complete cylinder stock on the Z spindle at X = Y = 0, supports turning
operations only, and cannot simulate thread geometry.

## Usage
1. Open a CAM job and select **CAM -> CAM Addons -> Turning Addon -> Simulation**.
2. Choose the operations and the simulation engine.
3. Use **Previous operation**, **Play**, **Pause**, or **Next operation**. Click or drag the timeline to seek.
   **Next operation** skips to the end when already in the last operation.
   **Step forward 1 mm** pauses playback and advances along the sampled toolpath.
   **Step backward 1 mm** pauses playback and moves back along the sampled toolpath.
   Operation-change repositioning is instant in either direction and is not
   counted in the step distance. A step at the start or end may be shorter.
4. Use the stock button on the timeline to hide the stock and watch only the tool
   motion. Stock meshes are not built while it is hidden.

Tools need valid geometry, feeds and spindle speed. Turning currently supports
straight tool movements only.
Thread operations use tool-motion-only playback and do not remove material.

## Feedback
Report bugs or share feedback on the [Path Forum](https://forum.freecadweb.org/viewforum.php?f=15).

## Disclaimer
This experimental tool is used at your own risk. Machine tools are dangerous;
the author is not responsible for damage or injury caused by incorrect machining
parameters.
