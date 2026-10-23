try:
    import liblathe
except ModuleNotFoundError as error:
    if error.name != "liblathe":
        raise
    raise ImportError(
        "Turning Addon requires LibLathe. Install liblathe into the "
        "Python environment used by FreeCAD, then restart FreeCAD.") from error