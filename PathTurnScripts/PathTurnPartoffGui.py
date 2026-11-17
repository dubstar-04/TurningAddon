# -*- coding: utf-8 -*-

# Copyright (c) 2020 Daniel Wood <s.d.wood.82@gmail.com>
# SPDX-License-Identifier: LGPL-2.0-or-later
# See LICENSE for terms. This software is provided WITHOUT ANY WARRANTY.

import FreeCAD
import PathTurnScripts.PathTurnBaseGui as PathTurnBaseGui
import PathTurnScripts.PathTurnPartoff as PathTurnPartoff
import Path.Log as PathLog
import Path.Op.Gui.Base as PathOpGui

from PySide import QtCore

__title__ = "Path Turn Part Gui"
__author__ = "dubstar-04 (Daniel Wood)"
__url__ = "http://www.freecadweb.org"
__doc__ = "Gui implementation for turning parting operations."

LOGLEVEL = False

if LOGLEVEL:
    PathLog.setLevel(PathLog.Level.DEBUG, PathLog.thisModule())
    PathLog.trackModule(PathLog.thisModule())
else:
    PathLog.setLevel(PathLog.Level.NOTICE, PathLog.thisModule())


class TaskPanelOpPage(PathTurnBaseGui.RetractionModeFields, PathTurnBaseGui.TaskPanelTurnBase):
    '''Page controller class for Turning operations.'''

    quantity_fields = {
        **PathTurnBaseGui.TaskPanelTurnBase.quantity_fields,
        "PeckDepth": "peckDepth",
    }
    retraction_tooltip = FreeCAD.Qt.translate(
        "PathTurn", "None: part off in one feed.\n"
        "Partial Retract: cut in Peck depth steps; back off one tool width to break the chip.\n"
        "Full Retract: cut in Peck depth steps; retract to the cut start to clear the chip.")
    peck_depth_tooltip = FreeCAD.Qt.translate("PathTurn", "Maximum radial depth per peck.")

    def getForm(self):
        form = super().getForm()
        self._setupRetractionMode(form)
        return form

    def setOpFields(self, obj):
        self._setRetractionFields(obj)

    def getFields(self, obj):
        super().getFields(obj)
        self._getRetractionFields(obj)

    def getSignalsForUpdate(self, obj):
        return super().getSignalsForUpdate(obj) + self._retractionSignals()


Command = PathOpGui.SetupOperation('TurnPartoff',
                                   PathTurnBaseGui.stockCheckedFactory(PathTurnPartoff.Create),
                                   TaskPanelOpPage,
                                   'CAM-TurnPartoff',
                                   QtCore.QT_TRANSLATE_NOOP("PathTurnPartoff", "Turn Part"),
                                   QtCore.QT_TRANSLATE_NOOP("PathTurnPartoff",
                                                            "Creates a Path Turning Part object from a features of a base object"),
                                   PathTurnPartoff.SetupProperties)

FreeCAD.Console.PrintLog("Loading PathTurnPartoffGui... done\n")
