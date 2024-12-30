# -*- coding: utf-8 -*-

# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2021 Schildkroet                                        *
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
import FreeCADGui
import PathTurnScripts.PathTurnBaseGui as PathTurnBaseGui
import PathTurnScripts.PathTurnThread as PathTurnThread
import PathScripts.PathLog as PathLog
import PathScripts.PathOpGui as PathOpGui
import PathScripts.PathGui as PathGui

from PySide import QtCore

import PathTurnScripts.PathTurnAddonHelpers as PathTurnHelpers

__title__ = "Path Turn Thread Gui"
__author__ = "Schildkroet"
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
    
    def initPage(self, obj):
        self.updating = False  # pylint: disable=attribute-defined-outside-init
    
    def getForm(self):
        '''getForm() ... return UI'''
        turnUi = PathTurnHelpers.getResourcePath("PageOpTurnThreadEdit.ui")
        return FreeCADGui.PySideUic.loadUi(turnUi)
    
    def getFields(self, obj):
        '''getFields(obj) ... transfers values from UI to obj's proprties'''
        PathLog.track()

        PathGui.updateInputField(obj, 'DOC', self.form.doc)

        obj.Pitch = self.form.threadPitch.value()
        obj.Peak = self.form.Peak.value()
        obj.ThreadDepth = self.form.threadDepth.value()
        obj.SpringPasses = self.form.springPasses.value()
        obj.SlideAngle = self.form.slideAngle.value()

        self.updateToolController(obj, self.form.toolController)
        self.updateCoolant(obj, self.form.coolantController)
        
        if obj.ThreadType != str(self.form.threadType.currentText()):
            obj.ThreadType = str(self.form.threadType.currentText())

    def setFields(self, obj):
        '''setFields(obj) ... transfers obj's property values to UI'''
        PathLog.track()
        
        self.form.doc.setText(FreeCAD.Units.Quantity(obj.DOC.Value, FreeCAD.Units.Length).UserString)
        self.form.threadPitch.setValue(obj.Pitch)
        self.form.Peak.setValue(obj.Peak)
        self.form.threadDepth.setValue(obj.ThreadDepth)
        self.form.springPasses.setValue(obj.SpringPasses)
        self.form.slideAngle.setValue(obj.SlideAngle)
        
        self.setupToolController(obj, self.form.toolController)
        self.setupCoolant(obj, self.form.coolantController)
        
        self.selectInComboBox(obj.ThreadType, self.form.threadType)

        self.setOpFields(obj)

    def getSignalsForUpdate(self, obj):
        '''getSignalsForUpdate(obj) ... return list of signals for updating obj'''
        signals = []

        signals.append(self.form.doc.editingFinished)
        signals.append(self.form.threadPitch.valueChanged)
        signals.append(self.form.Peak.valueChanged)
        signals.append(self.form.threadDepth.valueChanged)
        signals.append(self.form.springPasses.valueChanged)
        signals.append(self.form.slideAngle.valueChanged)

        signals.append(self.form.toolController.currentIndexChanged)
        signals.append(self.form.coolantController.currentIndexChanged)
        signals.append(self.form.threadType.currentIndexChanged)

        return signals
        
    def setOpFields(self, obj):
        '''setFields(obj) ... transfers obj's property values to UI'''
        pass


Command = PathOpGui.SetupOperation('TurnThread',
                                   PathTurnThread.Create,
                                   TaskPanelOpPage,
                                   'Path-TurnThread',
                                   QtCore.QT_TRANSLATE_NOOP("PathTurnThread", "Turn Thread"),
                                   QtCore.QT_TRANSLATE_NOOP("PathTurnThread",
                                                            "Creates a Path Turning Thread object from a features of a base object"),
                                   PathTurnThread.SetupProperties)

FreeCAD.Console.PrintLog("Loading PathTurnThreadGui... done\n")
