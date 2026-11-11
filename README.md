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
* Turning Grooving operation
* Internal clearing and finishing Boring operation
* Straight centreline Drilling operation (proof of concept)
* Turning Tool Library

## Requirements
* FreeCAD v1.1 or later with the CAM workbench
* Path Toolbits (Legacy tools are not supported)
* Python3
* FreeCAD's Qt/PySide runtime

Insert-based turning operation tools must define **ToolPost** as **Front** or **Rear**.
If the selected tool lacks a valid value, opening the operation editor shows
a warning instead of starting an incomplete task panel. Select a suitable
turning tool through the operation's Tool Controller, then reopen the editor.
**Turn Drill** instead requires a native FreeCAD **Drill** ToolBit or the bundled
**Centreline drill**, without
ToolPost or Front/Rear settings.
New operations retain a compatible inherited Tool Controller; otherwise they
select a compatible controller from the job. Tool lists are filtered by operation
type, so an insert operation following drilling does not inherit the drill.
Opening an existing operation with an incompatible controller selects an available
compatible controller and reports the replacement. If none exists, add a suitable
Tool Controller to the job before editing.

## Testing centreline drilling

Requires a LibLathe build containing `liblathe.op.drill.DrillOP` and
`liblathe.tool.drill.Drill`. Restart FreeCAD after installing them.

1. In **Turning Tool Library**, create a tool from the **Centreline drill**
   template. Set **Diameter**, **TipAngle** (included point angle in degrees)
   and **Length** (overall length), then add it to the CAM job.
   The template's Attributes object belongs to its Body, so parameters travel
   with the native tool geometry rather than becoming an unmanaged document object.
   The default tip angle is **118 degrees**; **135 degrees** is another typical
   choice and can be entered directly.
   The preview and native solid update with these values; the datum is the tip
   at X=0/Z=0 and the drill body extends toward +Z. No Front/Rear settings apply.
   Diameter must be positive, tip angle strictly between 0 and 180 degrees,
   and length greater than the conical point length.
   FreeCAD's standard native **Drill** ToolBits (for example **5mm Drill**)
   are also supported through standard tool management.
2. Create **CAM -> CAM Addons -> Turning Addon -> Turn Drill**. No Base
   Geometry selection is needed. Choose the drill's controller and set its
   **Vertical Feed**, spindle settings and coolant.
   Newly created Tool Controllers may have no feed set: enter a suitable positive
   Vertical Feed before generating a path. Tool dimensions do not determine a
   machining feed automatically.
3. On **Containment**, choose a safe **Start depth** entry plane and set
   **Final tip depth** below it. Start Depth may lie inside the original stock
   envelope; no starting-stock access check or automatic adjustment is made.
   The user is responsible for entry and retract clearance. X is fixed at zero. Final depth is
   the drill **tip**, not the full-diameter hole bottom; the latter lies one
   conical point length ahead of the tip.
4. The path rapids to Start Depth plus the job **Safe Height Offset**, approaches
   Start Depth axially, feeds to Final Tip Depth and retracts to front clearance.
   Clearance must be positive. Feed is passed through from the Tool Controller,
   consistently with the other turning operations. Depth exceeding the ToolBit's
   overall Length is rejected, but flute length and holder/chuck fit are not checked.
5. Apply/recompute to inspect the shared before/after stock preview. It includes
   the pointed bottom and carries the drilled cavity forward to later operations,
   including boring. It neither validates boring access nor changes its planner.

This POC performs **straight drilling only**: no pecks, canned cycles, dwell,
automatic breakthrough, off-axis/live-tool drilling or automatic hole recognition.
For through holes, explicitly account for point length in the tip depth.
It does not protect the target model from a chosen over-depth, certify travel
from an unknown initial position, or validate chip evacuation, tool/holder fit
or machine safety. Initial stock still uses its outer envelope.

## Containment and clearance

For every turning operation, containment bounds **all feed moves** (G1/G2/G3),
including entry, lead-in/out and withdrawal, at the tool reference. It does not
bound the entire insert or describe the physical stock. Only rapid moves may
leave containment to reach clearance.

External operations use the job stock separately when checking rapid routes.
If there is no stock-clear containment boundary entry or exit, generation reports
an error instead of feeding outside containment or rapiding through stock.
Enlarge the limits to include a safe entry/withdrawal and recompute. Grooving
retains its prepared-region assumption for local clearance, not a rest-stock
simulation. Boring does not certify opening or holder access (see below).

Facing lead-outs are clipped to the limits. Parting now places the tool reference
at **Final Depth**, not an insert-width offset beyond it; review that depth on
existing parting operations after updating.

## Testing internal boring

**Turn Bore** is available under **CAM -> CAM Addons -> Turning Addon**.
It requires the LibLathe build containing `liblathe.op.bore.BoreOP`.
Restart FreeCAD after updating the addon/library.

1. Create **Turn Bore** in a CAM job. **No Base Geometry selection or manual
   section is required.** The operation extracts internal geometry from the job
   models, then uses containment to choose the bore region.
2. Cylindrical, conical and toroidal walls must be coaxial with Z;
   flat upward-facing floors/steps attached at wall bottoms are included
   automatically. Their positive-X meridians must form one connected open contour.
   Containment must intersect exactly one such contour; zero or multiple matches
   produce an explicit error. Narrow X/Z limits to choose the intended region
   or exclude a floor. Legacy Base selections are ignored and hidden.
   Both Front and Rear tools use the same model geometry.
   The contour's first and last edges must be straight, with the first
   progressing into the bore.
   Finishing strokes stop at the model contour's axial endpoints (adjusted
   for the insert reference); wider containment does not extend the model's
   wall or floor. Entry and escape travel are separate from these cutting limits.
3. Use a turning Tool Controller whose insert is oriented for internal cutting.
   The addon does not automatically turn an external insert into a boring tool.
   For the supplied ISO C 80-degree tool, validation used Edge Length
   **06 - 6.35 mm**, with **Rotation 315 degrees / Front**, or
   **Rotation 45 degrees / Rear**. ToolPost alone does not mirror the insert;
   inspect its actual geometry and reference before testing.
4. Choose **Cut direction**: **Radial** (default) clears outward in X at successive
   depths toward Final Depth; **Axial** clears in Z toward Final Depth at
   successively increasing radii. Entry uses the containment minimum radius,
   normally X=0. Existing saved X/Z selections migrate to Radial/Axial on reopen;
   operations without a direction acquire the Radial default. The addon maps
   these names to LibLathe's `CutDirection.RADIAL` / `CutDirection.AXIAL`.
5. Set containment, Finish Passes, Pass Offset and Stock to Leave. The diameter
   properties become signed radii in the path. Pass Offset sets the maximum axial
   step for X clearing or radial step for Z clearing, and normal finishing spacing.
   Clearing reserves the outermost finishing allowance; finishing works down to
   Stock to Leave. Zero Finish Passes means clearing only. Finishing enters at the
   inner radius, feeds down, cuts outward (+X), then follows the internal profile
   toward the mouth (+Z), regardless of clearing direction. The job's
   **Safe Height Offset** supplies positive front clearance.

Front clearance is **Start Depth + Safe Height Offset**. Z clearing positions
to the next X radius at that plane, approaches Start Depth axially, then feeds
toward Final Depth. It does not position outward inside the bore under feed.
X clearing begins at **Start Depth**, not at the model mouth, then steps toward
Final Depth subject to the model's protected floor. Each outward cut starts at
the containment minimum radius. Ahead of the mouth it uses the compensated
mouth radius; finishing remains limited to the model contour.
These positioning routes are checked against the target model, not starting stock.

After radial cuts, the tool lifts toward the mouth before returning inward,
rather than reversing along the newly cut surface. The lift stays within
containment; at its front boundary an axial rapid reaches front clearance
before returning inward. Axial cuts disengage inward before returning toward
the mouth. The inner radius is reserved as an access lane, not an axial
clearing pass without withdrawal room.

This provides internal clearing and finishing, **not hole preparation**.
There are **no predrilling, opening, tool-fit, bar/holder or travel-clearance
checks**. The user must judge preparation and fit. Cutting, feed entry and inward
feed escape stay within the tool-reference containment. Rapid positioning and
axial return can leave it to reach front clearance; they are not checked against
starting stock or an existing hole. Inspect the complete path before any use.

The shared stock guide supports this operation and carries its removed material
forward to following operations. It subtracts the physical insert swept along
generated feeds; no bore-specific stock subtraction or planning feedback is used.
Its containment display shows only the cutting-limit rectangle,
not the external operation's radial-clearance line. Rapids can leave containment;
feed moves cannot.

## Feedback
If you have feedback or need to report bugs please participate on the related [Path Forum](https://forum.freecadweb.org/viewtopic.php?f=15&t=30563&start=0).

## Disclaimer
This is an experimental tool for development purposes and must be used at your own risk. Machine tools are dangerous and the author of this tool will not be responsible for any damage or personal injury caused by using incorrect tool paths or machining parameters.
# Remaining-stock guide

Turning operation task panels automatically show a translucent 2D amber
remaining-stock fill and outline alongside solid magenta containment limits and the
single thin dashed magenta line at the clearance radius. Both have white halos
to distinguish them from toolpaths. Containment has no fill, keeping material
and operation limits distinct. Only material polygons are filled; removed regions
and holes stay empty.
Choose **Stock before operation** or **Stock after operation** on the
Containment page. Editing defaults to **Stock before operation**, showing the
material left by preceding enabled operations (original stock for the first
operation). **Show remaining stock** and **Show containment** independently
control the stock outline and the containment/clearance overlays.
The before view remains available while the current operation has unapplied
edits; only preceding operations must have up-to-date generated paths.

The guide reads generated feeds in enabled job order. It does not generate or
modify paths, approve rapids, or change planning. Recompute/apply operations
before inspecting the guide; stale or unavailable results are reported in the
panel instead of being displayed as current.

This is predicted material, not measured machine stock or a safety certificate.
Internal boring uses the same stock subtraction as external turning, including
Radial/Axial clearing and Front/Rear tools. Bore-generated cavities remain empty
in the fill and are carried forward in job order.
Initial stock comes from its **outer rotational envelope**, closed to the axis:
pre-existing openings in imported or hollow stock are not represented. The
preview does not infer a pilot hole or certify access through one.
The first implementation supports convex initial stock and convex turning
inserts with straight X/Z feeds. Insert curves use inscribed chords with
0.005 mm sagitta; numerically uncertain material is retained. Non-turning
predecessors, arc feeds, and unsupported stock shapes are reported explicitly.
No rest machining or 3D stock is implemented. Requires a LibLathe build exposing
`liblathe.base.segmentgroup.StockPreview`.
