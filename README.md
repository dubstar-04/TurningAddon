# FreeCAD Turning Addon ![Python package](https://github.com/dubstar-04/FreeCAD_Turning_Addon/workflows/Python%20package/badge.svg?branch=master)
A FreeCAD CAM Addon to encourage the development of CNC turning functionality for the CAM workbench.  

| :warning: WARNING: Turning Addon is currently experimental / proof of concept and only suitable for testing. |

## Description
This addon when installed will appear in the CAM Workbench toolbar menu and will allow the creation of turning paths for use with a CNC lathe. This addon requires [LibLathe](https://github.com/dubstar-04/LibLathe) to be installed. 

## Features
* Turning Roughing operation
* Turning Facing operation
* Turning Profiling operation
* Turning Parting operation

## Requirements
* FreeCAD >=v1.0.0
* CAM Toolbits (Legacy tools are not supported)
* Python3  
* Qt5
* Liblathe

## Installation
1. Use `git clone --recurse` or download the `.zip` file of this repo directly in to your [FreeCAD `Mod/` directory](https://www.freecadweb.org/wiki/Installing_more_workbenches).  
2. Restart FreeCAD 

## Feedback  
If you have feedback or need to report bugs please participate on the related [CAM Forum](https://forum.freecadweb.org/viewtopic.php?f=15&t=30563&start=0). 

## Disclaimer
This is an experimental tool for development purposes and must be used at your own risk. Machine tools are dangerous and the author of this tool will not be responsible for any damage or personal injury caused by using incorrect tool paths or machining parameters.
