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
from LibLathe.LLBoundBox import BoundBox
from LibLathe.LLPoint import Point

def getResourcePath(resName):
    # get this directory
    pathScripts = os.path.dirname(__file__)
    # get the parent directory 
    __dir__ = os.path.dirname(pathScripts)
    # get the resourse directory
    resourcePath = os.path.join( __dir__, 'Gui/Resources/panels')
    res = os.path.join( resourcePath, resName)
    
    return res

def getLibLatheBoundBox(FcBB):
    LibLatheBoundbox =  BoundBox(Point(FcBB.XMin, FcBB.YMin, FcBB.ZMin), Point(FcBB.XMax, FcBB.YMax, FcBB.ZMax))
    return LibLatheBoundbox