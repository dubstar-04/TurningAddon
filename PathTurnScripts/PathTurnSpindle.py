import math


RPM = "RPM"
CSS = "CSS"


def spindle_commands(
        mode, supports_css, spindle_speed, surface_speed, max_rpm, machine_max_rpm=0,
        imperial_output=False):
    """Return mode commands as (G-code, parameters) pairs, validating spindle limits."""
    if mode not in (RPM, CSS):
        raise ValueError("Unknown spindle speed control mode.")
    if mode == RPM:
        return ()

    if not math.isfinite(spindle_speed) or spindle_speed <= 0:
        raise ValueError("Set a positive fixed spindle speed on the Tool Controller.")
    if machine_max_rpm and spindle_speed > machine_max_rpm:
        raise ValueError(
            "Fixed spindle speed cannot exceed the machine limit of {limit} RPM.")
    if not supports_css:
        return (("G97", {"S": spindle_speed}),)

    # FreeCAD posts write S unchanged, so m/min would be read as ft/min under G20.
    if imperial_output:
        raise ValueError(
            "Constant surface speed is not supported with imperial output. "
            "Use metric output or Fixed RPM.")
    if not math.isfinite(surface_speed) or surface_speed <= 0:
        raise ValueError("Set a positive surface speed on the Tool Controller.")
    if max_rpm <= 0:
        raise ValueError("Set a positive maximum spindle speed on the Tool Controller.")
    if machine_max_rpm and max_rpm > machine_max_rpm:
        raise ValueError(
            "Maximum spindle speed cannot exceed the machine limit of {limit} RPM.")

    return (
        ("G96", {"S": surface_speed, "D": max_rpm}),
        ("G97", {"S": spindle_speed}),
    )
