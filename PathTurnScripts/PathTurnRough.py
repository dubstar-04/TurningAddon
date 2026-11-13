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

import liblathe.op.rough as LLP
from liblathe.op.base import Direction

__title__ = "Path Turn Rough Operation"
__author__ = "dubstar-04 (Daniel Wood)"
__url__ = "http://www.freecadweb.org"
__doc__ = "Class implementation for turning profiling operations."


def translate(context, text, disambig=None):
    return QtCore.QCoreApplication.translate(context, text, disambig)


class ObjectTurnRough(PathTurnBase.ObjectOp):
    '''Proxy class for turning roughing operations.'''

    supports_internal_mode = True
    direction_tooltip = translate("TurnPath", "Roughing direction")
    pass_offset_label = translate("TurnPath", "Radial Pass Offset")

    def pass_offset_label_for(self, obj):
        if str(obj.Direction) == Direction.RADIAL.value:
            return translate("TurnPath", "Axial Pass Offset")
        return translate("TurnPath", "Radial Pass Offset")

    def op_generate_gcode(self, obj, turnTool):
        '''
        Generate GCode for the op
        '''
        RoughOP = LLP.RoughOP()
        RoughOP.setParams(self.getProps(obj))

        containmentBounds = PathTurnHelpers.getContainment(obj)
        RoughOP.add_containment(containmentBounds)
        RoughOP.add_stock(PathTurnHelpers.getStock(obj))

        RoughOP.addPartSegments(self.part_outline)
        RoughOP.add_tool(turnTool)

        PathCode = RoughOP.getGCode()

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
    '''Create(name) ... Creates and returns a TurnRough operation.'''
    if obj is None:
        obj = FreeCAD.ActiveDocument.addObject("Path::FeaturePython", name)
    obj.Proxy = ObjectTurnRough(obj, name, parentJob)
    return obj
