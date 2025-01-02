# -*- coding: utf-8 -*-

# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2025 Daniel Wood <s.d.wood.82@gmail.com>                *
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

from PySide import QtGui, QtCore
from PySide.QtGui import QApplication, QDialog, QMainWindow

import FreeCAD, FreeCADGui

import PathTurnScripts.PathTurnAddonHelpers as PathTurnHelpers

class TurnToolHelperPanel():
    def __init__(self):

        self.form = self.getForm()

        self.tip_angle = {
            "A": 85,  # Parallelogram (85 degree)
            "B": 82,  # Parallelogram (82 degree)
            "C": 80,    # Rhombic (80 degree)
            "D": 55,    # Rhombic (55 degree)
            "E": 75,  # Rhombic (75 degree)
            "F": 50,  # Rhombic (50 degree)
            "H": 120,  # Hexagonal
            "K": 55,  # Parallelogram (55 degree)
            "L": 90, 	# Rectangular
            "M": 86, 	# Rhombic (86 degree)
            "O": 135, 	# Octagonal
            "P": 108, 	# Pentagonal
            "R": 90, 	# Round
            "S": 90, 	# Square
            "T": 60, 	# Triangular
            "V": 35,    # Rhombic (35 degree)
            "W": 60, 	# Trigon
            "X": None   # Special Shape
        }

        self.shape_size = {
            "C": {"03": 3.97, "04": 4.76, "05": 5.56, "06": 6.35, "08": 7.94, \
            "09": 9.525, "12": 12.7, "16": 15.875, "19": 19.05, "22": 22.225, \
            "25": 25.4},
            "D": {"04": 3.97, "05": 4.76, "06": 5.56, "07": 6.35, "09": 7.94, \
            "11": 9.525, "15": 12.7, "19": 15.875, "23": 19.05},
            "R": {"06": 6.0, "08": 8.0, "09": 9.525, "10": 10, "12": 12.0, \
            "16": 16, "20": 20, "25": 25},
            "S": {"03": 3.97, "04": 4.76, "05": 5.56, "06": 6.35, "08": 7.94, \
            "09": 9.525, "12": 12.7, "16": 15.875, "19": 19.05, "22": 22.225, \
            "25": 25.4},
            "T": {"08": 4.76, "09": 5.56, "11": 6.35, "13": 7.94, "16": 9.525, \
            "22": 12.7, "27": 15.875, "33": 19.05, "38": 22.225, "44": 25.4},
            "V": {"08": 4.76, "09": 5.56, "11": 6.35, "13": 7.94, "16": 9.525, \
            "22": 12.7},
            "W": {"02": 3.97, "L3": 4.76, "03": 5.56, "04": 6.35, "05": 7.94, \
            "06": 9.525, "08": 12.7, "10": 15.875, "13": 19.05},
            "X" : {}
        }

        self.nose_radius = {
            "00": 0,  # sharp
            "V3": 0.03,
            "V5": 0.05,
            "01": 0.1,
            "02": 0.2,
            "04": 0.4,
            "08": 0.8,
            "12": 1.2,
            "16": 1.6,
            "20": 2.0,
            "24": 2.4,
            "28": 2.8,
            "32": 3.2
        }

        #Load UI Components
        self.shape_cb = self.form.shape_cb
        self.size_cb = self.form.size_cb
        self.radius_cb = self.form.radius_cb
        self.direction_cb = self.form.direction_cb

        # self.shape_val = self.form.shape_val
        self.size_val = self.form.size_val
        # self.rotation_val = self.form.rotation_val
        self.tipangle_val = self.form.tipangle_val
        self.radius_val = self.form.radius_val
        # self.direction_val = self.form.direction_val
        self.result_val = self.form.result_val
        


        #connect
        self.shape_cb.currentIndexChanged.connect(self.load_shape_size)

        self.shape_cb.currentIndexChanged.connect(self.load_tool_data)
        self.size_cb.currentIndexChanged.connect(self.load_tool_data)
        self.radius_cb.currentIndexChanged.connect(self.load_tool_data)
        self.direction_cb.currentIndexChanged.connect(self.load_tool_data)

        self.load_shape_size(0)
		
    def getForm(self):
        """getForm() ... return UI"""
        # return FreeCADGui.PySideUic.loadUi(":/panels/DlgTurnToolHelper.ui")
        turnUi = PathTurnHelpers.getResourcePath("DlgTurnToolHelper.ui")
        return FreeCADGui.PySideUic.loadUi(turnUi)

    def load_tool_data(self):
        """ 
        Load all tool data and create a tool string
        """
        if self.size_cb.currentText():
            _shape = self.shape_cb.currentText()
            _size = self.size_cb.currentText()
            _radius = self.radius_cb.currentText()
            _direction = self.direction_cb.currentText()
            _size_val = self.get_edge_length(_shape, _size)
            _radius_val = self.get_radius_value(_radius)
            _tip_angle = self.get_tip_angle(_shape)

            # print('tool data', _shape, _size, _radius, _direction)
            # self.shape_val.setText(_shape)
            self.size_val.setText(str(_size_val))
            self.tipangle_val.setText(str(_tip_angle))

            if _shape == "X":
                _radius = "-"
                _direction = "-"
                self.radius_val.setText("-")
                # self.direction_val.setText("-")
            else:
                self.radius_val.setText(str(_radius_val))
                # self.direction_val.setText(_direction)

            tool_string = "{shape}---{size}--{radius}--{direction}".format(shape = _shape, size = _size, \
                                                                radius = _radius, direction = _direction)
            self.result_val.setText(tool_string)

    def get_edge_length(self, _shape, _length ):
        """
        Return the edge length for the tool
        """

        try:
            edgeLength = self.shape_size[_shape][_length]
            return edgeLength
        except(KeyError):
            return "-"

    def get_radius_value(self, radius):
        """
        Return the nose radius for the tool
        """

        try:
            _radius = self.nose_radius[radius]
            return _radius
        except(KeyError):
            return "-"

    def get_tip_angle(self, shape):
        """
        Return the tip angle for the tool
        """

        try:
            _tip_angle = self.tip_angle[shape]
            return _tip_angle
        except(KeyError):
            return "-"

    def load_shape_size(self, index):
        """
        Load the sizes for the selected tool shape
        """
        shape = self.shape_cb.itemText(index)
        shape_size = self.shape_size[shape]
        self.size_cb.clear()

        if shape == "X":
            self.size_cb.addItem("-")
        else:
            for key in shape_size: 
                self.size_cb.addItem(key)

    def setup_ui(self):
        pass

    def show(self):
        self.form.show()
        self.form.exec_()

    def reject(self):
        FreeCAD.Console.PrintMessage("Reject Signal")
        self.quit()

    def accept(self):
        self.quit()
        
    def quit(self):
        FreeCADGui.Control.closeDialog(self)

    def reset(self):
        pass
		
		
class CommandPathTurnToolHelper:
		
    def GetResources(self):
        return {'Pixmap': 'CAM-TurnToolHelper',
                'MenuText': QtCore.QT_TRANSLATE_NOOP("CAM", "Derive toolbit parameters from isocode"),
                'ToolTip': QtCore.QT_TRANSLATE_NOOP("CAM", "Derive toolbit parameters from isocode")}
	
    def Activated(self):
        panel = TurnToolHelperPanel()
        panel.show()


if FreeCAD.GuiUp:
    # register the FreeCAD command
    FreeCADGui.addCommand('CAM_TurnToolHelper', CommandPathTurnToolHelper())



