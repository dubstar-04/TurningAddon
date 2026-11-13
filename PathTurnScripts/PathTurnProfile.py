# -*- coding: utf-8 -*-

# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2019 Daniel Wood <s.d.wood.82@gmail.com>                *
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU Lesser General Public License (LGPL)    *
# *   as published by the Free Software Foundation; either version 2 of     *
# *   the License, or (at your option) any later version.                   *
# *   for detail see the LICENCE text file.                                 *
# *                                                                         *
# *   This program is distributed in the hope that it will be useful,       *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
# *   GNU Library General Public License for more details.                  *
# *                                                                         *
# *   You should have received a copy of the GNU Library General Public     *
# *   License along with this program; if not, write to the Free Software   *
# *   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
# *   USA                                                                   *
# *                                                                         *
# ***************************************************************************

import FreeCAD
import Path
import PathTurnScripts.PathTurnBase as PathTurnBase
from PySide import QtCore

import PathTurnScripts.PathTurnAddonHelpers as PathTurnHelpers

import liblathe.op.profile as LLP
from liblathe.op.profile import ProfileDirection

__title__ = "Path Turn Profile Operation"
__author__ = "dubstar-04 (Daniel Wood)"
__url__ = "http://www.freecadweb.org"
__doc__ = "Class implementation for turning profiling operations."


def translate(context, text, disambig=None):
    return QtCore.QCoreApplication.translate(context, text, disambig)


class ObjectTurnProfile(PathTurnBase.ObjectOp):
    '''Proxy class for turning profile operations.'''

    supports_internal_mode = True
    external_direction = "-Z"
    internal_direction = "Radial"

    @staticmethod
    def _addDirection(obj):
        values = ["-Z", "+Z", "Radial"]
        created = not hasattr(obj, "Direction")
        if created:
            obj.addProperty(
                "App::PropertyEnumeration", "Direction", "Turn Path",
                translate("TurnPath", "Profiling direction"))
        default = "Radial" if str(getattr(obj, "Mode", "External")) == "Internal" else "-Z"
        current = default if created else str(obj.Direction)
        if current == "Inward":
            current = "Radial"
        if created or obj.getEnumerationsOfProperty("Direction") != values:
            obj.Direction = values
            obj.Direction = current if current in values else default

    def initOperation(self, obj):
        super().initOperation(obj)
        self._addDirection(obj)

    def opOnDocumentRestored(self, obj):
        super().opOnDocumentRestored(obj)
        self._addDirection(obj)

    def getProps(self, obj):
        directions = {
            "-Z": ProfileDirection.NEGATIVE_Z,
            "+Z": ProfileDirection.POSITIVE_Z,
            "Radial": ProfileDirection.RADIAL,
        }
        try:
            direction = directions[str(obj.Direction)]
        except KeyError as error:
            raise ValueError(f"Unsupported profiling direction: {obj.Direction}") from error
        return {**super().getProps(obj), "direction": direction}


    def op_generate_gcode(self, obj, turnTool):
        '''
        Generate GCode for the op
        '''
        profileOP = LLP.ProfileOP()
        profileOP.setParams(self.getProps(obj))

        containmentBounds = PathTurnHelpers.getContainment(obj)
        profileOP.add_containment(containmentBounds)
        profileOP.add_stock(PathTurnHelpers.getStock(obj))

        profileOP.addPartSegments(self.part_outline)
        profileOP.add_tool(turnTool)

        PathCode = profileOP.getGCode()

        for command in PathCode:
            pathCommand = Path.Command(command.get_movement(), command.getParams())
            self.commandlist.append(pathCommand)


def SetupProperties():
    setup = []
    setup.append("Mode")
    setup.append("Direction")
    setup.append("PassOffset")
    setup.append("FinishPasses")
    setup.append("AllowGrooving")
    return setup


def Create(name, obj=None, parentJob=None):
    '''Create(name) ... Creates and returns a TurnProfile operation.'''
    if obj is None:
        obj = FreeCAD.ActiveDocument.addObject("Path::FeaturePython", name)
    obj.Proxy = ObjectTurnProfile(obj, name, parentJob)
    return obj
