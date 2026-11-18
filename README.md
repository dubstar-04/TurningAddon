# FreeCAD Turning Addon

A FreeCAD CAM workbench addon for creating CNC lathe toolpaths.

> **Experimental:** This addon is under development. Review and verify every toolpath before machining.

## Features

- Roughing: clears material with axial or radial cuts, including facing and grooving
- Profiling: follows the part shape with offset passes
- Drilling: drills holes on the spindle centreline
- Threading: cuts external threads (does not currently produce valid G-code; see [#65](https://github.com/dubstar-04/TurningAddon/issues/65))
- Parting: cuts through the workpiece to separate a finished part
- Constant surface speed: uses CSS on supported turning operations with a new-style postprocessor
- Tool Library: Create and edit turning tools.
- Simulation: Preview and navigate toolpaths.
- Containment: Set machining limits for each operation.
- Remaining Stock: View stock before or after an operation.

## Requirements

- FreeCAD 26.3 or later
- [LibLathe](https://pypi.org/project/liblathe/)

The addon is available from **CAM > CAM Addons > Turning Addon**.

## Turning operations

<table>
  <tr>
    <td align="center"><strong>Roughing</strong><br><img src="Screenshots/screenshot_op_rough_clear.png" alt="Roughing"></td>
    <td align="center"><strong>Facing</strong><br><img src="Screenshots/screenshot_op_rough_face.png" alt="Facing"></td>
  </tr>
  <tr>
    <td align="center"><strong>Grooving</strong><br><img src="Screenshots/screenshot_op_grooving.png" alt="Grooving "></td>
    <td align="center"><strong>Profiling</strong><br><img src="Screenshots/screenshot_op_profile.png" alt="Profiling"></td>
  </tr>
  <tr>
    <td align="center"><strong>Boring</strong><br><img src="Screenshots/screenshot_op_bore.png" alt="Boring"></td>
    <td align="center"><strong>Threading</strong><br><img src="Screenshots/screenshot_op_threading.png" alt="Threading"></td>
  </tr>
    <tr>
    <td align="center"><strong>Chamfer</strong><br><img src="Screenshots/screenshot_op_chamfer.png" alt="Chamfer"></td>
    <td align="center"><strong>Partoff</strong><br><img src="Screenshots/screenshot_op_partoff.png" alt="Partoff"></td>
  </tr>
</table>

### Tool Management

- Use the **Turning Tool Library** to create and edit tools.

<img src="Screenshots/screenshot_toollibrary.png" alt="Turning Tool Library" width="640">

<img src="Screenshots/screenshot_toollibrary_shape.png" alt="ToolBit shape selection" width="640">

### Containment

- Containment sets the area an operation can machine.
- While editing, a section view shows the limits on the model.
- Drag the handles to change a limit.
- Handles snap to model edges.

<img src="Screenshots/screenshot_containment.png" alt="Containment bounds" width="640">

### Remaining Stock

- View stock before or after an operation.

<img src="Screenshots/screenshot_remainingstock.png" alt="Remaining-stock guide" width="640">

### Simulation

- Choose which operations to simulate.
- Click an operation to jump to it.
- Scrub the timeline.
- Step forward or back 1 mm.
- Skip to the previous or next operation.
- Choose a simulation engine. More than one engine is available to help with development and testing.

<img src="Screenshots/screenshot_simulation.png" alt="Turning simulation" width="640">

### Constant surface speed

- In the operation's **Turning Spindle** page, choose **Constant Surface Speed**.
- Edit fixed RPM using **Spindle Speed** on the **Tool Controller** page.
- Surface speed and maximum RPM are stored on the Tool Controller and shared by operations using it.
- The maximum RPM defaults to the configured machine limit when the machine has one rotary toolhead; otherwise, set it manually.
- These Addon settings are saved with the document but are not included in FreeCAD's Tool Controller templates.
- The operation emits `G96` for cutting and restores the Tool Controller's fixed RPM with `G97`.
- Drilling and threading always use fixed RPM.
- Use a new-style postprocessor that supports converting `G96` and `G97` for the target controller.

## License

[LGPL-2.1](LICENSE)
