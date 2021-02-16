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
import Path
import PathTurnScripts.PathTurnBase as PathTurnBase
import PathScripts.PathLog as PathLog
from PySide import QtCore

import PathTurnScripts.PathTurnAddonHelpers as PathTurnHelpers
from liblathe.command import Command


__title__ = "Path Turn Thread Operation"
__author__ = "Schildkroet"
__url__ = "http://www.freecadweb.org"
__doc__ = "Class implementation for turning thread operations."


def translate(context, text, disambig=None):
    return QtCore.QCoreApplication.translate(context, text, disambig)


class ObjectTurnThread(PathTurnBase.ObjectOp):
    '''Proxy class for turning profile operations.'''

    def initOperation(self, obj):
        '''initOperation(obj)'''

        obj.addProperty("App::PropertyLength", "DOC", "Turn Path", translate("TurnPath", "Depth of Cut"))
        obj.addProperty("App::PropertyInteger", "SpringPasses", "Turn Path", translate("TurnPath", "Number of Spring Passes"))
        
        obj.addProperty("App::PropertyFloat", "Pitch", "Turn Path", translate("TurnPath", "Depth of Cut"))
        obj.addProperty("App::PropertyFloat", "Peak", "Turn Path", translate("TurnPath", "Drive line offset"))
        obj.addProperty("App::PropertyFloat", "ThreadDepth", "Turn Path", translate("TurnPath", "Depth of Thread"))
        obj.addProperty("App::PropertyFloat", "SlideAngle", "Turn Path", translate("TurnPath", "Compound Slide Angle"))
        
        obj.addProperty("App::PropertyEnumeration", "ThreadType", "Turn Path", "Type of Thread")
        obj.ThreadType = ['External', 'Internal']

        # Set default values
        obj.SpringPasses = 0
        obj.DOC = FreeCAD.Units.Quantity(0.1, FreeCAD.Units.Length)
        obj.Pitch = 1.0
        obj.Peak = 4.0
        obj.ThreadDepth = 0.5
        obj.SlideAngle = 29.5
        obj.ThreadType = "External"
    
    def opExecute(self, obj):
        '''opExecute(obj) ... processes all Base features
        '''
        PathLog.track()
        self.tool = None
        self.minDia = obj.MinDiameter.Value
        self.maxDia = obj.MaxDiameter.Value

        if self.minDia >= self.maxDia:
            raise RuntimeError(translate('PathTurn', "Minimum diameter is equal or greater than maximum diameter"))

        if obj.StartDepth.Value <= obj.FinalDepth.Value:
            raise RuntimeError(translate('PathTurn', "Start depth is equal or less than final depth"))

        self.startOffset = 0
        self.endOffset = 0

        # Clear any existing gcode
        obj.Path.Commands = []

        print("Process...")
        self.generate_gcode(obj)
    
    def op_generate_gcode(self, obj, turnTool):
        '''
        Generate GCode for the op
        '''
        # Check for external/internal thread
        if obj.ThreadType == "External":
            obj.Peak *= -1
        
        # Move to start of drive line
        params = {'Z': obj.StartDepth.Value+obj.Pitch+1, 'X': obj.MaxDiameter.Value/2 - obj.Peak}
        move = Command('G0', params)
        
        # Threading command
        params = {'Z': obj.OpStockZMin.Value+obj.FinalDepth.Value, 'P': obj.Pitch, 'I': obj.Peak, 'J': obj.DOC.Value, 'K': obj.ThreadDepth, 'Q': obj.SlideAngle, 'H': obj.SpringPasses}
        thread = Command('G76', params)
        
        # Add commands
        pathCommand = Path.Command(move.get_movement(), move.get_params())
        self.commandlist.append(pathCommand)
        pathCommand = Path.Command(thread.get_movement(), thread.get_params())
        self.commandlist.append(pathCommand)

    def opSetDefaultValues(self, obj, job):
        obj.OpStartDepth = job.Stock.Shape.BoundBox.ZMax
        obj.OpFinalDepth = job.Stock.Shape.BoundBox.ZMin
        #print('opSetDefaultValues:', obj.OpStartDepth.Value, obj.OpFinalDepth.Value)

    def opUpdateDepths(self, obj):
        obj.OpStartDepth = obj.OpStockZMax
        obj.OpFinalDepth = obj.OpStockZMin
        #print('opUpdateDepths:', obj.OpStartDepth.Value, obj.OpFinalDepth.Value)


def SetupProperties():
    setup = []
    setup.append("ThreadType")
    setup.append("DOC")
    setup.append("Pitch")
    setup.append("Peak")
    setup.append("ThreadDepth")
    setup.append("SpringPasses")
    setup.append("SlideAngle")
    
    return setup


def Create(name, obj=None):
    '''Create(name) ... Creates and returns a TurnProfile operation.'''
    if obj is None:
        obj = FreeCAD.ActiveDocument.addObject("Path::FeaturePython", name)
        
    obj.Proxy = ObjectTurnThread(obj, name)
    
    return obj
