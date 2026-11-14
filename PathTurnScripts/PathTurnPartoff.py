# -*- coding: utf-8 -*-

# Copyright (c) 2020 Daniel Wood <s.d.wood.82@gmail.com>
# SPDX-License-Identifier: LGPL-2.0-or-later
# See LICENSE for terms. This software is provided WITHOUT ANY WARRANTY.

import FreeCAD
import Path
import PathTurnScripts.PathTurnBase as PathTurnBase
from PySide import QtCore

import PathTurnScripts.PathTurnAddonHelpers as PathTurnHelpers

import liblathe.op.partoff as LLP

__title__ = "Path Turn Part Operation"
__author__ = "dubstar-04 (Daniel Wood)"
__url__ = "http://www.freecadweb.org"
__doc__ = "Class implementation for turning profiling operations."


def translate(context, text, disambig=None):
    return QtCore.QCoreApplication.translate(context, text, disambig)


class ObjectTurnPart(PathTurnBase.ObjectOp):
    '''Proxy class for turning Part operations.'''

    uses_pass_offset = False

    def op_generate_gcode(self, obj, turnTool):
        '''
        Generate GCode for the op
        '''
        PartOP = LLP.PartoffOP()
        PartOP.setParams(self.getProps(obj))

        containmentBounds = PathTurnHelpers.getContainment(obj)
        PartOP.add_containment(containmentBounds)
        PartOP.add_stock(PathTurnHelpers.getStock(obj))

        PartOP.addPartSegments(self.part_outline)
        PartOP.add_tool(turnTool)

        PathCode = PartOP.getGCode()

        for command in PathCode:
            pathCommand = Path.Command(command.get_movement(), command.getParams())
            self.commandlist.append(pathCommand)


def SetupProperties():
    return []


def Create(name, obj=None, parentJob=None):
    '''Create(name) ... Creates and returns a TurnPart operation.'''
    if obj is None:
        obj = FreeCAD.ActiveDocument.addObject("Path::FeaturePython", name)
    obj.Proxy = ObjectTurnPart(obj, name, parentJob)
    return obj
