"""Shared signed-coordinate containment editor for turning operations."""

import math
from functools import partial

import FreeCAD
import FreeCADGui
import Part
import Path.Log as PathLog
import Path.Op.Gui.Base as PathOpGui
from PySide import QtCore, QtGui

from . import PathTurnAddonHelpers as helpers
from .PathTurnToolBit import post_from_parameters


class TaskPanelContainment(PathOpGui.TaskPanelPage):
    def getForm(self):
        return FreeCADGui.PySideUic.loadUi(helpers.getResourcePath("PageTurnContainment.ui"))

    def getTitle(self, obj):
        return FreeCAD.Qt.translate("PathTurn", "Containment")

    def initPage(self, obj):
        self.updating = False
        self.bindings = {}
        self.widgets = {name: getattr(self.form, name) for name in self.mapping(obj)}
        self.setFields(obj)
        for name, widget in self.widgets.items():
            widget.valueChanged.connect(partial(self.changeLimit, name))
            widget.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            widget.customContextMenuRequested.connect(partial(self.expressionMenu, name))
            getattr(self.form, name + "Set").clicked.connect(partial(self.setFromSelection, name))

    def mapping(self, obj):
        post = post_from_parameters({"ToolPost": obj.ToolController.Tool.ToolPost})
        if post == "Rear":
            radial = {"plusX": ("MinDiameter", -0.5), "minusX": ("MaxDiameter", -0.5)}
        else:
            radial = {"plusX": ("MaxDiameter", 0.5), "minusX": ("MinDiameter", 0.5)}
        return dict(radial, plusZ=("StartDepth", 1), minusZ=("FinalDepth", 1))

    def setFields(self, obj):
        self.updating = True
        try:
            self.bindings = self.mapping(obj)
            expressions = dict(obj.ExpressionEngine)
            standard_dimensions = (
                hasattr(obj, "ThreadStandard") and obj.ThreadStandard != "Custom")
            for name, (prop, scale) in self.bindings.items():
                widget = self.widgets[name]
                preset_locked = standard_dimensions and prop in ("MinDiameter", "MaxDiameter")
                widget.setEnabled(not preset_locked)
                getattr(self.form, name + "Set").setEnabled(not preset_locked)
                widget.setProperty(
                    "unit", FreeCAD.Units.Quantity(1, FreeCAD.Units.Length).getUserPreferred()[2])
                widget.setProperty("minimum", -1e9 if scale < 0 or name.endswith("Z") else 0)
                widget.setProperty("maximum", 0 if scale < 0 else 1e9)
                expression = expressions.get(prop)
                value = (FreeCAD.Units.Quantity(obj.evalExpression(expression)).Value
                         if expression else getattr(obj, prop).Value)
                widget.setProperty("rawValue", value * scale)
                widget.setToolTip(
                    FreeCAD.Qt.translate(
                        "PathTurn", "Expression: {value}\nEditing the value replaces the expression.").format(
                        value=f"({expression}) * {scale:g}") if expression else
                    FreeCAD.Qt.translate(
                        "PathTurn", "Signed coordinate in mm (X is radius, not diameter). "
                        "Right-click to set an expression." if not preset_locked else
                        "The selected standard thread size controls this diameter. Choose Custom to edit it."))
        finally:
            self.updating = False
        self.updateSelection(obj, FreeCADGui.Selection.getSelectionEx())

    def changeLimit(self, name, *args):
        if self.updating:
            return
        prop, scale = self.bindings[name]
        value = self.widgets[name].property("rawValue") / scale
        if math.isfinite(value) and not math.isclose(
                getattr(self.obj, prop).Value, value, rel_tol=0, abs_tol=1e-7):
            self.updating = True
            try:
                if prop in dict(self.obj.ExpressionEngine):
                    self.obj.setExpression(prop, None)
                setattr(self.obj, prop, value)
            finally:
                self.updating = False
            self.setDirty()

    def getFields(self, obj):
        for name in self.widgets:
            if self.bindings[name][0] not in dict(obj.ExpressionEngine):
                self.changeLimit(name)

    def updateData(self, obj, prop):
        if not self.updating and prop in (
                "MinDiameter", "MaxDiameter", "StartDepth", "FinalDepth",
                "ExpressionEngine", "ToolController", "ThreadStandard"):
            self.setFields(obj)

    def expressionMenu(self, name, position):
        widget = self.widgets[name]
        menu = QtGui.QMenu(widget)
        action = menu.addAction(FreeCAD.Qt.translate("PathTurn", "Set expression..."))
        clear = menu.addAction(FreeCAD.Qt.translate("PathTurn", "Clear expression"))
        prop, scale = self.bindings[name]
        expression = dict(self.obj.ExpressionEngine).get(prop)
        clear.setEnabled(bool(expression))
        chosen = menu.exec_(widget.mapToGlobal(position))
        if chosen == clear:
            self.obj.setExpression(prop, None)
            self.setDirty()
            self.setFields(self.obj)
        elif chosen == action:
            text = f"({expression}) * {scale:g}" if expression else ""
            text, accepted = QtGui.QInputDialog.getText(
                widget, FreeCAD.Qt.translate("PathTurn", "Containment expression"),
                FreeCAD.Qt.translate("PathTurn", "Coordinate expression (length):"),
                QtGui.QLineEdit.Normal, text)
            if accepted and text.strip():
                try:
                    self.setCoordinateExpression(name, text)
                except (FreeCAD.Base.FreeCADError, ValueError) as error:
                    self.show_error_message(
                        FreeCAD.Qt.translate("PathTurn", "Invalid expression"), str(error))
                else:
                    self.setDirty()
                    self.setFields(self.obj)

    def setCoordinateExpression(self, name, expression):
        prop, scale = self.bindings[name]
        expression = f"({expression}) / ({scale:g})"
        value = FreeCAD.Units.Quantity(self.obj.evalExpression(expression))
        if value.Unit != FreeCAD.Units.Quantity(1, FreeCAD.Units.Length).Unit:
            raise ValueError(FreeCAD.Qt.translate("PathTurn", "Expression must evaluate to a length."))
        if not math.isfinite(value.Value) or (name.endswith("X") and value.Value < 0):
            raise ValueError(FreeCAD.Qt.translate("PathTurn", "Expression is outside the tool side."))
        self.obj.setExpression(prop, expression)
        setattr(self.obj, prop, value)

    def selectionValue(self, name, selection):
        if name.endswith("Z"):
            return PathOpGui.TaskPanelHeightsPage.selectionZLevel(self, self.obj, selection)
        if len(selection) != 1 or len(selection[0].SubObjects) != 1:
            return None
        sub = selection[0].SubObjects[0]
        radius = None
        if sub.ShapeType == "Vertex":
            radius = math.hypot(sub.Point.x, sub.Point.y)
        elif sub.ShapeType in ("Edge", "Face"):
            geometry = sub.Curve if sub.ShapeType == "Edge" else sub.Surface
            if isinstance(geometry, (Part.Circle, Part.Cylinder)):
                axis = geometry.Axis
                center = geometry.Center
                if (abs(abs(axis.z) - 1) < 1e-7
                        and math.hypot(center.x, center.y) < 1e-7):
                    radius = geometry.Radius
            elif (sub.ShapeType == "Edge" and isinstance(geometry, Part.Line)
                  and len(sub.Vertexes) == 2):
                a, b = [v.Point for v in sub.Vertexes]
                if math.hypot(a.x - b.x, a.y - b.y) < 1e-7:
                    radius = math.hypot(a.x, a.y)
        if radius is None:
            return None
        return -radius if self.bindings["plusX"][1] < 0 else radius

    def updateSelection(self, obj, selection):
        for name in self.widgets:
            getattr(self.form, name + "Set").setEnabled(
                self.widgets[name].isEnabled()
                and self.selectionValue(name, selection) is not None)

    def setFromSelection(self, name):
        value = self.selectionValue(name, FreeCADGui.Selection.getSelectionEx())
        if value is None:
            PathLog.warning(FreeCAD.Qt.translate(
                "PathTurn", "Select a vertex, an axial edge or a spindle-centred circle/cylinder "
                "for X; select a vertex or horizontal edge/face for Z."))
            return
        prop, scale = self.bindings[name]
        if prop in dict(self.obj.ExpressionEngine):
            self.obj.setExpression(prop, None)
        setattr(self.obj, prop, value / scale)
        self.setDirty()
        self.setFields(self.obj)
