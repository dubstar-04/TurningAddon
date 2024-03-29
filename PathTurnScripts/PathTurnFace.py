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

import FreeCAD
import Path
import PathTurnScripts.PathTurnBase as PathTurnBase
from PySide import QtCore

import PathTurnScripts.PathTurnAddonHelpers as PathTurnHelpers

import liblathe.op.face as LLF

__title__ = "Path Turn Facing Operation"
__author__ = "dubstar-04 (Daniel Wood)"
__url__ = "http://www.freecadweb.org"
__doc__ = "Class implementation for turning facing operations."


def translate(context, text, disambig=None):
    return QtCore.QCoreApplication.translate(context, text, disambig)


class ObjectTurnFace(PathTurnBase.ObjectOp):
    '''Proxy class for turning facing operations.'''

    # def opFeatures(self, obj):
    #    '''opFeatures(obj) ... returns the OR'ed list of features used and supported by the operation.'''
    #    return PathTurnBase.PathOp.FeatureDiameters | PathTurnBase.PathOp.FeatureTool | PathTurnBase.PathOp.FeatureDepths | PathTurnBase.PathOp.FeatureNoFinalDepth | PathTurnBase.PathOp.FeatureCoolant

    def op_generate_gcode(self, obj, turnTool):
        '''
        Generate GCode for the op
        '''
        # self.clear_path()
        facingOP = LLF.FaceOP()
        facingOP.set_params(self.getProps(obj))

        stockBoundbox = PathTurnHelpers.getliblatheBoundBox(self.stock_silhoutte.BoundBox)
        facingOP.add_stock(stockBoundbox)

        facingOP.add_part_edges(self.part_outline)
        facingOP.add_tool(turnTool)

        PathCode = facingOP.get_gcode()

        for command in PathCode:
            pathCommand = Path.Command(command.get_movement(), command.get_params())
            self.commandlist.append(pathCommand)

    def opSetDefaultValues(self, obj, job):
        obj.OpStartDepth = job.Stock.Shape.BoundBox.ZMax
        obj.OpFinalDepth = job.Stock.Shape.BoundBox.ZMin
        # obj.MaxDiameter = job.Stock.Shape.BoundBox.XMin # - job.SetupSheet.SafeHeightOffset.Value

    def opUpdateDepths(self, obj):
        obj.OpStartDepth = obj.OpStockZMax
        obj.OpFinalDepth = obj.OpStockZMin


def SetupProperties():
    setup = []
    setup.append("StepOver")
    setup.append("FinishPasses")
    setup.append("AllowGrooving")
    return setup


def Create(name, obj=None, parentJob=None):
    '''Create(name) ... Creates and returns a TurnFace operation.'''
    if obj is None:
        obj = FreeCAD.ActiveDocument.addObject("Path::FeaturePython", name)
    obj.Proxy = ObjectTurnFace(obj, name, parentJob)
    return obj
