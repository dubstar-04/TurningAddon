# FreeCAD Turning Addon

A FreeCAD CAM workbench addon for creating CNC lathe toolpaths.

> **Experimental:** This addon is under development. Review and verify every toolpath before machining.

## Features

- Turning roughing, including facing and grooving
- Turning profiling, parting, threading, and drilling
- A turning tool library and toolpath simulation
- Containment controls and a remaining-stock guide

## Requirements

- FreeCAD 26.3 or later
- [LibLathe](https://pypi.org/project/liblathe/)

The addon is available from **CAM > CAM Addons > Turning Addon**.

## Turning operations

<table>
  <tr>
    <td align="center"><strong>Roughing</strong><br><img src="Screenshots/screenshot_op_rough_clear.png" alt="Roughing toolpath"></td>
    <td align="center"><strong>Facing</strong><br><img src="Screenshots/screenshot_op_rough_face.png" alt="Facing toolpath"></td>
  </tr>
  <tr>
    <td align="center"><strong>Grooving</strong><br><img src="Screenshots/screenshot_op_grooving.png" alt="Grooving toolpath"></td>
    <td align="center"><strong>Profiling</strong><br><img src="Screenshots/screenshot_op_profile.png" alt="Profiling toolpath"></td>
  </tr>
  <tr>
    <td align="center"><strong>Boring</strong><br><img src="Screenshots/screenshot_op_bore.png" alt="Boring toolpath"></td>
    <td align="center"><strong>Containment</strong><br><img src="Screenshots/screenshot_containment.png" alt="Containment bounds"></td>
  </tr>
</table>

## Tools and simulation

Use the **Turning Tool Library** to create and edit tools. The containment controls set operation bounds, and the remaining-stock guide shows stock before or after an operation. Use **Turning Simulation** to preview a toolpath.

<table>
  <tr>
    <td align="center"><strong>Tool library</strong><br><img src="Screenshots/screenshot_toollibrary.png" alt="Turning Tool Library"></td>
    <td align="center"><strong>ToolBit shapes</strong><br><img src="Screenshots/screenshot_toollibrary_shape.png" alt="ToolBit shape selection"></td>
  </tr>
  <tr>
    <td align="center"><strong>Remaining-stock guide</strong><br><img src="Screenshots/screenshot_remainingstock.png" alt="Remaining-stock guide"></td>
    <td align="center"><strong>Simulation</strong><br><img src="Screenshots/screenshot_simulation.png" alt="Turning simulation"></td>
  </tr>
</table>

## License

[LGPL-2.1](LICENSE)
