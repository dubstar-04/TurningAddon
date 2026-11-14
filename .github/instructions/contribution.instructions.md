---
applyTo: "**"
---

# Code guidelines

## UI

- Keep UI elements aligned.
- Lay out label and input rows like the Tool Controller feed controls: a fixed-width label column (150 px) with a clear gap before the controls.
- Do not put complex information about operations or G-code in the UI.

## Tooltips

- Keep tooltips short and plain, with one option or idea per line.
- For enumerations, put each option on its own line as `Option: what it does`.
- Explain how Pass Offset is used in the specific operation; do not assume it has the same meaning everywhere.
- For roughing, axial cutting strokes are spaced radially along X; radial cutting strokes are spaced axially along Z.
- For profiling, Pass Offset is the normal distance between successive profile contours. For threading, it is the radial infeed between passes.
- Example:

  ```text
  How the drill clears chips.
  None: drill to depth in one feed.
  Partial Retract: step, then retract one drill diameter.
  Full Retract: step, then retract to clearance.
  ```

## Tests

- Do not add tests for UI elements, such as task panels, widgets, labels, tooltips or icons.

## README

- Keep the README to a basic overview of the addon.
- Do not add details about versions, operations or G-code.
