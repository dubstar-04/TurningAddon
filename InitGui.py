
"""
Path Turning Addon module for FreeCAD.
This file is a standard FreeCAD Addon file
it exists to load the liblathe library.
"""

import FreeCAD

try:
    import liblathe  # noqa: F401
except ImportError:
    FreeCAD.Console.PrintError("liblathe module not found. Please ensure the Turning Addon is installed correctly.\n")
