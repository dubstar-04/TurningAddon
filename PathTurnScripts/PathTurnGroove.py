# -*- coding: utf-8 -*-

# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2026 Daniel Wood <s.d.wood.82@gmail.com>                *
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

import liblathe.op.groove as LLG

__title__ = "Path Turn Groove Operation"
__author__ = "dubstar-04 (Daniel Wood)"
__url__ = "http://www.freecadweb.org"
__doc__ = "Radial grooving operation for turning."


def translate(context, text, disambig=None):
    return QtCore.QCoreApplication.translate(context, text, disambig)


class ObjectTurnGroove(PathTurnBase.ObjectOp):
    '''Proxy class for turning grooving operations.'''

    pass_offset_label = translate("TurnPath", "Radial Pass Offset")

    def op_generate_gcode(self, obj, turnTool):
        '''
        Generate GCode for the op
        '''
        GrooveOP = LLG.GrooveOP()
        GrooveOP.setParams(self.getProps(obj))
        containmentBounds = PathTurnHelpers.getContainment(obj)
        GrooveOP.add_containment(containmentBounds)
        GrooveOP.add_stock(PathTurnHelpers.getStock(obj))
        GrooveOP.addPartSegments(self.part_outline)
        GrooveOP.add_tool(turnTool)
        PathCode = GrooveOP.getGCode()

        for command in PathCode:
            pathCommand = Path.Command(command.get_movement(), command.getParams())
            self.commandlist.append(pathCommand)


def SetupProperties():
    setup = []
    setup.append("PassOffset")
    setup.append("FinishPasses")
    return setup


def Create(name, obj=None, parentJob=None):
    '''Create(name) ... Creates and returns a TurnGroove operation.'''
    if obj is None:
        obj = FreeCAD.ActiveDocument.addObject("Path::FeaturePython", name)
    obj.Proxy = ObjectTurnGroove(obj, name, parentJob)
    return obj
