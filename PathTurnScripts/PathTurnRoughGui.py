# -*- coding: utf-8 -*-

# Copyright (c) 2019 Daniel Wood <s.d.wood.82@gmail.com>
# SPDX-License-Identifier: LGPL-2.0-or-later
# See LICENSE for terms. This software is provided WITHOUT ANY WARRANTY.

import FreeCAD
import PathTurnScripts.PathTurnBaseGui as PathTurnBaseGui
import PathTurnScripts.PathTurnRough as PathTurnRough
import Path.Log as PathLog
import Path.Op.Gui.Base as PathOpGui

from PySide import QtCore

__title__ = "Path Turn Rough Gui"
__author__ = "dubstar-04 (Daniel Wood)"
__url__ = "http://www.freecadweb.org"
__doc__ = "Gui implementation for turning profiling operations."

LOGLEVEL = False

if LOGLEVEL:
    PathLog.setLevel(PathLog.Level.DEBUG, PathLog.thisModule())
    PathLog.trackModule(PathLog.thisModule())
else:
    PathLog.setLevel(PathLog.Level.NOTICE, PathLog.thisModule())


class TaskPanelOpPage(PathTurnBaseGui.TaskPanelTurnBase):
    '''Page controller class for Turning operations.'''


Command = PathOpGui.SetupOperation('TurnRough',
                                   PathTurnRough.Create,
                                   TaskPanelOpPage,
                                   'CAM-TurnRough',
                                   QtCore.QT_TRANSLATE_NOOP("PathTurnRough", "Turn Rough"),
                                   QtCore.QT_TRANSLATE_NOOP("PathTurnRough",
                                                            "Creates a Path Turning Roughing object from a features of a base object"),
                                   PathTurnRough.SetupProperties)

FreeCAD.Console.PrintLog("Loading PathTurnRoughGui... done\n")
