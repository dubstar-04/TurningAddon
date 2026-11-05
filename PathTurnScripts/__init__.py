"""Turning operations and independent tool-library logic."""


def initialize():
    """Check machining dependencies when the FreeCAD addon starts."""
    import FreeCAD

    try:
        import liblathe
    except ModuleNotFoundError as error:
        if error.name != "liblathe":
            raise
        raise ImportError(
            "Turning Addon requires LibLathe. Install liblathe into the "
            "Python environment used by FreeCAD, then restart FreeCAD.") from error

    liblathe_version = getattr(liblathe, "__version__", "unknown (not reported by package)")
    FreeCAD.Console.PrintMessage(
        f"Turning Addon: using LibLathe {liblathe_version} from {liblathe.__file__}\n")
    try:
        from liblathe.tool.tool import ToolSide
    except ImportError as error:
        raise ImportError(
            "Turning Addon requires a LibLathe build with the ToolSide enum. "
            f"The loaded LibLathe {liblathe_version} at {liblathe.__file__} "
            "does not provide it. Install the updated LibLathe build into "
            "FreeCAD's Python environment, then restart FreeCAD.") from error
    if not all(hasattr(ToolSide, name) for name in ("NEAR", "FAR")):
        raise ImportError("Turning Addon requires LibLathe ToolSide.NEAR and ToolSide.FAR.")
