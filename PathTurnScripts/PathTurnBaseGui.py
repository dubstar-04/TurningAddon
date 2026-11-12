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

import os

import FreeCAD
import FreeCADGui
import Path.Log as PathLog
import Path.Op.Gui.Base as PathOpGui
import Path.Op.Gui.Selection as PathSelection
from PathScripts import PathUtils
#import PathGui

import Path.Base.Gui.Util as PathGuiUtil

from PySide import QtCore, QtGui

import PathTurnScripts.PathTurnAddonHelpers as PathTurnHelpers
from PathTurnScripts.PathTurnContainment import ContainmentPreview
from PathTurnScripts.PathTurnContainmentGui import TaskPanelContainment
from PathTurnScripts.PathTurnToolBit import post_from_parameters

__title__ = "Path Turn Base Gui"
__author__ = "dubstar-04 (Daniel Wood)"
__url__ = "http://www.freecadweb.org"
__doc__ = "Base class Gui implementation for turning operations."

# Operation view providers resolve tree icons as ":/icons/<pixmap>.svg",
# so register every addon icon under that resource-style name.
_iconDir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Gui", "Resources", "Icons")
for _iconFile in os.listdir(_iconDir):
    if _iconFile.endswith(".svg"):
        with open(os.path.join(_iconDir, _iconFile), encoding="utf-8") as _f:
            _svg = _f.read()
        FreeCADGui.addIcon(os.path.splitext(_iconFile)[0], _svg, "SVG")
        FreeCADGui.addIcon(":/icons/" + _iconFile, _svg, "SVG")

LOGLEVEL = False

if LOGLEVEL:
    PathLog.setLevel(PathLog.Level.DEBUG, PathLog.thisModule())
    PathLog.trackModule(PathLog.thisModule())
else:
    PathLog.setLevel(PathLog.Level.NOTICE, PathLog.thisModule())

_path_selection = PathSelection.select


def _select_with_turning_fallback(op):
    if op in ("TurnBore", "TurnDrill"):
        return PathSelection.profileselect
    try:
        return _path_selection(op)
    except KeyError:
        if op.startswith("Turn"):
            return PathSelection.turnselect
        raise


_select_with_turning_fallback._turning_fallback = True
if not getattr(PathSelection.select, "_turning_fallback", False):
    PathSelection.select = _select_with_turning_fallback


if not getattr(PathOpGui.ViewProvider.setEdit, "_turning_tool_check", False):
    _set_edit = PathOpGui.ViewProvider.setEdit

    def _set_edit_with_turning_tool_check(self, vobj=None, mode=0):
        view = vobj if vobj is not None else self.vobj
        if mode == 0 and self.OpPageModule.startswith("PathTurnScripts."):
            controller = getattr(view.Object, "ToolController", None)
            tool = getattr(controller, "Tool", None)
            if not view.Object.Proxy.isToolSupported(view.Object, tool):
                compatible = PathUtils.findToolController(view.Object, view.Object.Proxy)
                if compatible is not None:
                    PathLog.warning(FreeCAD.Qt.translate(
                        "PathTurn", "Replacing incompatible Tool Controller with {name}.").format(
                            name=compatible.Label))
                    view.Object.ToolController = compatible
                    tool = compatible.Tool
            try:
                if getattr(view.Object.Proxy, "centreline_drilling", False):
                    from .PathTurnDrill import getDrill

                    getDrill(tool)
                else:
                    post_from_parameters({"ToolPost": getattr(tool, "ToolPost", None)})
            except ValueError as error:
                message = (str(error) if getattr(view.Object.Proxy, "centreline_drilling", False) else
                           FreeCAD.Qt.translate(
                               "PathTurn", "The selected tool is not configured for turning: "
                               "ToolPost must be Front or Rear.\n\n"
                               "Select a turning tool with a valid ToolPost in the operation's "
                               "Tool Controller before editing."))
                PathLog.warning(message)
                QtGui.QMessageBox.warning(
                    FreeCADGui.getMainWindow(),
                    FreeCAD.Qt.translate("PathTurn", "Invalid turning tool"), message)
                return False
        return _set_edit(self, vobj, mode)

    _set_edit_with_turning_tool_check._turning_tool_check = True
    PathOpGui.ViewProvider.setEdit = _set_edit_with_turning_tool_check


class TaskPanelTurnBase(PathOpGui.TaskPanelPage):
    '''Page controller class for turning operations '''

    taskPanelDepthsPage = TaskPanelContainment

    def initPage(self, obj):
        self.updating = False  # pylint: disable=attribute-defined-outside-init
        # CAM initializes this operation page last, before constructing the panel layout.
        for page in list(self.parent.featurePages):
            if isinstance(page, PathOpGui.TaskPanelDiametersPage):
                page.pageCleanup()
                self.parent.featurePages.remove(page)
                page.form.deleteLater()
        self.containment_page = next(
            page for page in self.parent.featurePages if isinstance(page, TaskPanelContainment))
        self.form.showContainment = self.containment_page.form.showContainment
        self.form.showStock = self.containment_page.form.showStock
        if not getattr(obj.Proxy, "supports_stock_guide", True):
            self.form.showStock.setChecked(False)
            self.form.showStock.setEnabled(False)
            self.form.showStock.setToolTip(FreeCAD.Qt.translate(
                "PathTurn", "The stock guide is unavailable for internal boring."))
        self.containment = ContainmentPreview(obj.ViewObject.RootNode)
        from .PathTurnStockPreview import StockGuide

        self.stock_guide = StockGuide()
        self.stock_mode = QtGui.QComboBox()
        self.stock_mode.addItems([
            FreeCAD.Qt.translate("PathTurn", "Stock before operation"),
            FreeCAD.Qt.translate("PathTurn", "Stock after operation")])
        self.stock_mode.setCurrentIndex(0)
        self.stock_status = QtGui.QLabel()
        self.stock_status.setWordWrap(True)
        layout = self.containment_page.form.layout()
        row = layout.rowCount()
        layout.addWidget(self.stock_mode, row, 0, 1, 3)
        layout.addWidget(self.stock_status, row + 1, 0, 1, 3)
        self.stock_mode.currentIndexChanged.connect(self.updateContainment)
        self.stock_timer = QtCore.QTimer(self.form)
        self.stock_timer.setSingleShot(True)
        self.stock_timer.timeout.connect(self.updateContainment)
        self.containment_error = None
        self.form.showContainment.toggled.connect(self.updateContainment)
        self.form.showStock.toggled.connect(self.updateContainment)
        self.updateContainment()
        self.observing = True
        FreeCAD.addDocumentObserver(self)
        self.form.destroyed.connect(self.stopObserving)
        self.containment_page.form.destroyed.connect(self.stopObserving)

    def stopObserving(self, *args):
        if self.observing:
            self.stock_timer.stop()
            FreeCAD.removeDocumentObserver(self)
            self.observing = False

    def slotChangedObject(self, obj, prop):
        if obj.Document == self.obj.Document:
            self.stock_guide.key = None
            self.stock_status.setText(FreeCAD.Qt.translate("PathTurn", "Stock guide updating..."))
            self.containment.clear()
            self.stock_timer.start(250)
        if ((obj == getattr(self.job, "SetupSheet", None) and prop == "SafeHeightOffset")
                or (obj == getattr(self.obj.ToolController, "Tool", None) and prop == "ToolPost")):
            self.containment_page.setFields(self.obj)
            self.updateContainment()

    def updateContainment(self, *args):
        self.containment.clear()
        if self.form.showContainment.isChecked():
            try:
                self.containment.update(self.obj)
            except ValueError as error:
                message = str(error)
                if message != self.containment_error:
                    PathLog.warning(message)
                self.containment_error = message
            else:
                self.containment_error = None
        show_stock = self.form.showStock.isChecked()
        self.stock_mode.setEnabled(show_stock)
        self.stock_status.setVisible(show_stock)
        if not show_stock:
            return
        try:
            show_after = bool(self.stock_mode.currentIndex())
            before, after, complete = self.stock_guide.calculate(
                self.obj, include_current=show_after)
            snapshot = after if self.stock_mode.currentIndex() else before
            rear = PathTurnHelpers.getContainment(self.obj).XMax <= 0
            self.containment.show_stock(snapshot.edges(), rear, polygons=snapshot.polygons())
            message = ""
            if show_after and not complete:
                message = FreeCAD.Qt.translate("PathTurn", "No current path: showing stock before operation.")
            self.stock_status.setText(message)
            self.stock_status.setVisible(bool(message))
        except (ValueError, RuntimeError) as error:
            self.stock_status.setText(FreeCAD.Qt.translate(
                "PathTurn", "Stock guide unavailable: {error}").format(error=str(error)))

    def updateData(self, obj, prop):
        if prop in ("MinDiameter", "MaxDiameter", "StartDepth", "FinalDepth", "ToolController"):
            self.updateContainment()

    def cleanupPage(self, obj):
        self.stopObserving()
        try:
            self.form.showContainment.toggled.disconnect(self.updateContainment)
            self.form.showStock.toggled.disconnect(self.updateContainment)
        except (ReferenceError, RuntimeError) as error:
            PathLog.debug("Containment controls already destroyed: {}".format(error))
        try:
            self.containment.close()
        except (ReferenceError, RuntimeError) as error:
            PathLog.debug("Containment view already destroyed: {}".format(error))

    def getForm(self):
        '''getForm() ... return UI'''
        # return FreeCADGui.PySideUic.loadUi(":/panels/PageOpTurnBaseEdit.ui")
        turnUi = PathTurnHelpers.getResourcePath("PageOpTurnBaseEdit.ui")
        return FreeCADGui.PySideUic.loadUi(turnUi)

    def getFields(self, obj):
        '''getFields(obj) ... transfers values from UI to obj's proprties'''
        PathLog.track()

        if obj.Proxy.uses_pass_offset:
            PathGuiUtil.updateInputField(obj, "PassOffset", self.form.passOffset)

        obj.FinishPasses = self.form.finishPasses.value()
        obj.StockToLeave = self.form.stockToLeave.value()
        if hasattr(obj, "FinishPassOffset"):
            PathGuiUtil.updateInputField(obj, 'FinishPassOffset', self.form.finishPassOffset)

        if obj.AllowGrooving != self.form.allowGrooving.isChecked():
            obj.AllowGrooving = self.form.allowGrooving.isChecked()

        self.updateToolController(obj, self.form.toolController)
        self.updateCoolant(obj, self.form.coolantController)

    def setFields(self, obj):
        '''setFields(obj) ... transfers obj's property values to UI'''
        PathLog.track()

        self.form.passOffset.setVisible(obj.Proxy.uses_pass_offset)
        self.form.passOffsetLabel.setVisible(obj.Proxy.uses_pass_offset)
        self.form.passOffsetLabel.setText(obj.Proxy.pass_offset_label)
        self.form.passOffset.setText(obj.PassOffset.UserString)
        self.form.finishPasses.setValue(obj.FinishPasses)
        self.form.stockToLeave.setValue(obj.StockToLeave)
        has_finish_offset = hasattr(obj, "FinishPassOffset")
        self.form.finishPassOffset.setVisible(has_finish_offset)
        self.form.finishPassOffsetLabel.setVisible(has_finish_offset)
        if has_finish_offset:
            self.form.finishPassOffset.setText(obj.FinishPassOffset.UserString)
        self.setupToolController(obj, self.form.toolController)
        self.setupCoolant(obj, self.form.coolantController)

        if obj.AllowGrooving:
            self.form.allowGrooving.setCheckState(QtCore.Qt.Checked)
        else:
            self.form.allowGrooving.setCheckState(QtCore.Qt.Unchecked)

        self.setOpFields(obj)
        self.updateContainment()

    def getSignalsForUpdate(self, obj):
        '''getSignalsForUpdate(obj) ... return list of signals for updating obj'''
        signals = []

        if obj.Proxy.uses_pass_offset:
            signals.append(self.form.passOffset.editingFinished)
        signals.append(self.form.finishPasses.valueChanged)
        signals.append(self.form.stockToLeave.valueChanged)
        if hasattr(obj, "FinishPassOffset"):
            signals.append(self.form.finishPassOffset.editingFinished)
        signals.append(self.form.allowGrooving.stateChanged)

        signals.append(self.form.toolController.currentIndexChanged)
        signals.append(self.form.coolantController.currentIndexChanged)

        return signals

    def setOpFields(self, obj):
        '''setOpFields(obj) ... overwrite to set operations specific values.
        Should be overwritten by subclasses.'''
        pass  # pylint: disable=unnecessary-pass
