# -*- coding: utf-8 -*-

# Copyright (c) 2019 Daniel Wood <s.d.wood.82@gmail.com>
# SPDX-License-Identifier: LGPL-2.0-or-later
# See LICENSE for terms. This software is provided WITHOUT ANY WARRANTY.

import FreeCAD
import Path
import PathTurnScripts.PathTurnBase as PathTurnBase
from PySide import QtCore

import PathTurnScripts.PathTurnAddonHelpers as PathTurnHelpers

import liblathe.op.profile as LLP

__title__ = "Path Turn Profile Operation"
__author__ = "dubstar-04 (Daniel Wood)"
__url__ = "http://www.freecadweb.org"
__doc__ = "Class implementation for turning profiling operations."


def translate(context, text, disambig=None):
    return QtCore.QCoreApplication.translate(context, text, disambig)


class ObjectTurnProfile(PathTurnBase.ObjectOp):
    '''Proxy class for turning profile operations.'''

    supports_internal_mode = True
    uses_finish_passes = True
    uses_stock_to_leave = True
    uses_allow_grooving = True
    direction_tooltip = translate("TurnPath", "Profiling direction")

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
