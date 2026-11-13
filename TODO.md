# Grooving Operation

Implement an external radial grooving operation for front and rear tools.

## Behaviour

- StartDepth and FinalDepth are Z positions that limit the axial range. The
  full part is machined when those bounds cover it; a smaller range grooves
  only that section.
- MaxDiameter and MinDiameter limit X. Plunges start from the MaxDiameter
  radius and never go below the MinDiameter radius. Both limits are applied
  through the containment bound box from `getContainment()`.
- Use PassOffset for the radial distance between layers, matching
  LibLathe's `pass_offset` parameter.
- Limit the Z increment to slightly less than the tool's cutting width, so
  adjacent plunges overlap and no material is left between them. Take the
  width from the axial (Z) extent of the tool segment group's bound box, and
  use `max_increment = tool_width * (1 - overlap_percent / 100)`. Express the
  overlap as a percentage of tool width so it scales automatically when the
  tool changes. Use a fixed 10% overlap constant in LibLathe for now.
- Distribute Z stations evenly so the final pass is never very thin: use
  `count = ceil(range / max_increment)` increments of `range / count`. Every
  increment is equal and no larger than `max_increment`. Within each depth
  layer, stations are spaced separately over each run that the layer cuts,
  split where the reachable depth changes. Run ends hug feature walls, so
  grooves narrower than the full range are fully cleared. Wall positions are
  refined within the 0.05 offset tolerance to avoid ill-conditioned hits on
  near-radial offset walls.
- Complete every Z station in one radial depth layer before starting the next
  deeper layer. Include a shortened final radial increment when the depth is
  not an exact multiple of PassOffset.
- At each Z station, move the tool in X only, stopping at the layer depth, the
  first accessible part-profile limit or the MinDiameter radius, whichever is
  reached first.
- Retract radially clear before moving to another Z station. Do not use axial
  or diagonal cutting links between plunges.
- After the plunges, run FinishPasses spring passes along the final contour
  (0 disables them), clipped to the stock X and Z limits, to remove the
  scallops plunges leave on sloped or curved walls.
- Use the same geometry pipeline as the existing operations: build the
  machining boundary with `SegmentGroup.defeature()` and
  `SegmentGroup.offset()`, as `RoughOP` does. Defeature returns tool-origin
  positions, so the insert footprint, nose shape and datum are handled there.
  Preserve the existing front/rear signed-X behavior.
- Keep the full part profile for collision checks, even when grooving a
  restricted section. Reject invalid parameters and geometry that cannot be
  safely certified; do not publish partial or stale toolpaths on failure.

## Work

- [x] In LibLathe, add a dedicated `GrooveOP` (`liblathe/op/groove.py`) that
  uses `pass_offset` for radial layer spacing and a fixed 10%
  overlap constant for axial spacing; do not change roughing or
  part-off behavior.
- [x] Build the grooving boundary with the existing pipeline: defeature the part
  with `allow_grooving` enabled, so reachable grooves are retained, then offset
  it by `stock_to_leave` plus the minimal clearance used by `RoughOP`. Do not
  add a separate radial-limit or footprint query.
- [x] At each Z station between the stock ZMax and ZMin (StartDepth and
  FinalDepth), intersect a radial line from the stock XMax (MaxDiameter radius)
  with the offset boundary. Each plunge ends at the first intersection, the
  layer depth or the stock XMin (MinDiameter radius), whichever comes first.
- [x] Generate depth-first layers and Z stations. Check passes against the
  internal negative offset with `intersectsGroup()`, as `RoughOP` does, and
  certify plunges and withdrawals with `validateToolSweep()`.
- [x] Add operation-specific G-code that allows only radial cutting and
  withdrawal, with Z repositioning after clearance. Preserve existing routing
  for other operations and support front/rear reflection.
- [x] Add LibLathe tests (`tests/op/test_groove_op.py`) for layer ordering,
  X-only cuts, profile-limited depth, MinDiameter limit, stock-to-leave, partial
  axial ranges, even Z spacing, Z increments below tool width, overlap scaling
  after a tool change, material removal per step-down, front/rear output, and
  failure without partial paths.
- [x] Add a LibLathe example, `examples/ex6_groove_op.py`, following
  `ex3_rough_op.py`. It grooves a part with a wide and a narrow groove using a
  2 mm wide S-shaped (square) tool built from segments, as ISO S string codes
  start at 3.97 mm. It backplots the G-code with `Plot().backplot()`, draws the
  part and `tool_paths` with `Debug().draw()`, and writes `groove.gcode` to the
  examples folder. A comment shows how to restrict the stock Z range to groove
  a section.
- [x] In TurningAddon, add the grooving operation proxy and task panel, map
  FreeCAD's PassOffset property to `pass_offset`, and use LibLathe's default 10% overlap
  controlling maximum axial spacing.
- [x] Reuse the existing StartDepth/FinalDepth (Z) and MinDiameter/MaxDiameter
  (X) conversion to the LibLathe stock bound box. Disable the unrelated
  AllowGrooving control for this operation.
- [x] Create a new `CAM-TurnGroove.svg` icon in `Gui/Resources/Icons`. Match the
  existing 64×64 px turning icons in style and palette, and show a grooving
  tool plunging radially into a groove so it is distinct from the part-off and
  roughing icons.
- [x] Register the `TurnGroove` command with the `CAM-TurnGroove` pixmap and
  add it to the add-on menu command list in `InitTurningAddon.py`. Verify the
  icon appears in the menu, task panel and model tree, and verify property
  persistence across save/reopen and path regeneration.
- [ ] Validate whole-part and restricted-section grooving with front and rear
  tools, and confirm existing turning operations remain unchanged.
- [ ] Update the documentation to cover the grooving operation, including
  setup, tool selection, diameter and depth limits, Radial Pass Offset, LibLathe's
  default 10% overlap, and example workflows.
- [x] Replace the `emit` helper in `GrooveOP.generateGCode` with the shared
  `Path.fromSegmentGroup` routing. Use its radial direction for grooving;
  existing operations retain automatic routing, with axial routing also available.
- [ ] Investigate why `GrooveOP` is so complex compared to the other
  operations, for example its Z sampling, run classification and wall-end
  refinement, and simplify it where possible.
- [x] Add a grooving finishing pass that follows the groove walls and floor,
  removing the scallops radial plunges leave on sloped or curved walls.
  FinishPasses sets the number of spring passes along the final contour
  (0 disables them), and the FinishPasses control is enabled for grooving.


## Acceptance checks

- All Z stations in a layer are machined before any deeper layer begins.
- Radial layers use PassOffset; Z increments are equal and slightly less
  than the tool width by the configured overlap percentage, so adjacent
  plunges overlap and leave no material between them, including after a tool
  change.
- Ranges that are not an exact multiple of the maximum increment do not
  produce a thin final pass.
- Every cutting plunge and withdrawal keeps Z constant; Z only changes after
  the tool is radially clear. Finishing passes follow the contour but still
  approach and retract radially.
- No plunge passes the target layer depth, the first accessible profile limit
  or the MinDiameter radius.
- Partial sections do not cut outside their StartDepth/FinalDepth Z range or
  MinDiameter/MaxDiameter X range, while the complete part remains available
  for collision checking.
- Invalid step values, uncertifiable moves, and generation failures produce an
  explicit error without leaving partial or stale output.

- check M Iso tool
- Cache tool images to make the form load faster