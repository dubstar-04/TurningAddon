# -*- coding: utf-8 -*-

# Copyright (c) 2019 Daniel Wood <s.d.wood.82@gmail.com>
# SPDX-License-Identifier: LGPL-2.0-or-later
# See LICENSE for terms. This software is provided WITHOUT ANY WARRANTY.

import FreeCAD
import PathTurnScripts.PathTurnBaseGui as PathTurnBaseGui
import PathTurnScripts.PathTurnProfile as PathTurnProfile
import Path.Log as PathLog
import Path.Op.Gui.Base as PathOpGui

from PySide import QtCore

__title__ = "Path Turn Profile Gui"
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

    def setOpFields(self, obj):
        '''setFields(obj) ... transfers obj's property values to UI'''
        pass


Command = PathOpGui.SetupOperation('TurnProfile',
                                   PathTurnProfile.Create,
                                   TaskPanelOpPage,
                                   'CAM-TurnProfile',
                                   QtCore.QT_TRANSLATE_NOOP("PathTurnProfile", "Turn Profile"),
                                   QtCore.QT_TRANSLATE_NOOP("PathTurnProfile",
                                                            "Creates a Path Turning Profile object from a features of a base object"),
                                   PathTurnProfile.SetupProperties)

FreeCAD.Console.PrintLog("Loading PathTurnProfileGui... done\n")
