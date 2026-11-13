"""Sampling of internal FreeCAD turning paths in the XZ plane."""

import math


def sample_turning(commands, step_distance, initial=(0.0, 0.0, 0.0)):
    """Sample straight turning moves, retaining short moves and exact endpoints.

    Commands are ``(name, parameters)`` pairs. X is radial unless G7 explicitly
    selects diameter coordinates. The first move locates the tool; it does not
    invent a cutting move from an unknown starting position.
    """
    return [point for point, _ in sample_turning_moves(commands, step_distance, initial)]


def sample_turning_moves(commands, step_distance, initial=(0.0, 0.0, 0.0)):
    """Sample turning positions with their rapid/feed motion classification."""
    return sample_turning_path(commands, step_distance, initial)[0]


def sample_turning_path(commands, step_distance, initial=(0.0, 0.0, 0.0)):
    """Return motion samples and the exclusive sample index of each command end.

    Command boundaries allow straight sweeps to be batched without skipping
    corners. G0/G1 commands without X, Y or Z are skipped; the first coordinate
    move remains a single tool-locating sample.
    """
    if not math.isfinite(step_distance) or step_distance <= 0:
        raise ValueError("step_distance must be finite and positive")
    position = tuple(float(value) for value in initial)
    if len(position) != 3 or not all(math.isfinite(value) for value in position):
        raise ValueError("Initial turning position must have three finite coordinates")
    samples = []
    command_ends = []
    absolute = True
    xscale = 1.0
    for name, params in commands:
        if name in ("G18", "G21", "G40", "G94", "G95", "G96", "G97", "G4", "G04"):
            continue
        if name in ("G90", "G91"):
            absolute = name == "G90"
            continue
        if name in ("G7", "G07", "G8", "G08"):
            xscale = 0.5 if name in ("G7", "G07") else 1.0
            continue
        if name not in ("G0", "G00", "G1", "G01"):
            if name.startswith("G"):
                raise ValueError("Turning motion {} is not supported yet".format(name))
            continue
        if not any(axis in params for axis in ("X", "Y", "Z")):
            continue
        end = list(position)
        for index, axis in enumerate(("X", "Y", "Z")):
            if axis in params:
                value = float(params[axis]) * (xscale if axis == "X" else 1.0)
                if not math.isfinite(value):
                    raise ValueError("Turning coordinates must be finite")
                end[index] = value if absolute else position[index] + value
        end = tuple(end)
        if abs(end[1]) > 1e-7:
            raise ValueError("Turning paths must stay in the XZ plane (Y = 0)")
        distance = math.dist(position, end)
        rapid = name in ("G0", "G00")
        first = len(samples)
        if not samples:
            samples.append((end, rapid))
        elif distance > 0:
            steps = max(1, math.ceil(distance / step_distance))
            for step in range(1, steps):
                t = step / steps
                samples.append((tuple(a + (b - a) * t for a, b in zip(position, end)), rapid))
            samples.append((end, rapid))
        if len(samples) > first:
            command_ends.append(len(samples))
        position = end
    return samples, command_ends


def move_duration(start, end, horizontal_speed, vertical_speed, rapid=False, turning=False):
    """Travel time in seconds for millimetre coordinates and mm/s speeds.

    Turning feed follows the generator's XZ-plane horizontal feed. Milling
    plunges use vertical feed, other feed moves use horizontal feed. Rapids
    respect both axis rates, with simultaneous horizontal and vertical travel.
    """
    if not all(math.isfinite(speed) and speed > 0
               for speed in (horizontal_speed, vertical_speed)):
        raise ValueError("Motion speeds must be finite and positive")
    dx, dy, dz = (b - a for a, b in zip(start, end))
    horizontal = math.hypot(dx, dy)
    if rapid:
        return max(horizontal / horizontal_speed, abs(dz) / vertical_speed)
    speed = horizontal_speed if turning or horizontal > 1e-9 else vertical_speed
    return math.sqrt(dx * dx + dy * dy + dz * dz) / speed
