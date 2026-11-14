# -*- coding: utf-8 -*-

# Copyright (c) 2019 Daniel Wood <s.d.wood.82@gmail.com>
# SPDX-License-Identifier: LGPL-2.0-or-later
# See LICENSE for terms. This software is provided WITHOUT ANY WARRANTY.

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
    uses_stock_to_leave = True
    uses_allow_grooving = True
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
    setup.append("AllowGrooving")
    return setup


def Create(name, obj=None, parentJob=None):
    '''Create(name) ... Creates and returns a TurnRough operation.'''
    if obj is None:
        obj = FreeCAD.ActiveDocument.addObject("Path::FeaturePython", name)
    obj.Proxy = ObjectTurnRough(obj, name, parentJob)
    return obj
