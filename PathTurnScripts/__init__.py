import os
import sys


liblathePath = os.path.join(os.path.dirname(os.path.dirname(__file__)), "LibLathe")
if not os.path.isfile(os.path.join(liblathePath, "liblathe", "__init__.py")):
    raise ImportError(
        "Turning Addon requires its LibLathe submodule. "
        "Run 'git submodule update --init --recursive' in the add-on directory.")
if liblathePath not in sys.path:
    sys.path.insert(0, liblathePath)