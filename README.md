# FreeCAD Turning Addon
A FreeCAD Path Addon to encourage the development of CNC turning functionality for the PATH workbench.  

## Description
This addon when installed will appear in the Path Workbench toolbar menu and will allow the creation of turning paths for use with a CNC lathe. This addon includes [LibLathe](https://github.com/dubstar-04/LibLathe) as a submodule. 

## Features
* Turning Profiling operation
* Turning Facing operation

## Requirements
* FreeCAD v0.19  
* Python3  
* Qt5

## Installation
1. Use `git clone --recurse` or download the `.zip` file of this repo directly in to your [FreeCAD `Mod/` directory](https://www.freecadweb.org/wiki/Installing_more_workbenches).  
2. Restart FreeCAD 

Note: If the LibLathe folder inside the addon is empty or missing you may need to add the submodule manually: `git submodule update --init --recursive`

## Feedback  
If you have feedback or need to report bugs please participate on the related [Path Forum](https://forum.freecadweb.org/viewtopic.php?f=15&t=30563&start=0). 

## Disclaimer
This is an experimental tool and must be used at your own risk. Machine tools are dangerous and the author of this tool will not be responsible for any damage or personal injury caused by using incorrect tool paths or machining parameters.
