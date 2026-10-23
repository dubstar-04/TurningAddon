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