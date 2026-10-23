# -*- coding: utf-8 -*-

# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2020 Daniel Wood <s.d.wood.82@googlemail.com>            *
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
from PySide import QtGui

# import all turning operations
from PathTurnScripts import PathTurnFaceGui  # noqa: F401
from PathTurnScripts import PathTurnPartoffGui  # noqa: F401
from PathTurnScripts import PathTurnProfileGui  # noqa: F401
from PathTurnScripts import PathTurnRoughGui  # noqa: F401
from PathTurnScripts import PathTurnToolHelperGui  # noqa: F401
import os
import re

__dir__ = os.path.dirname(__file__)
iconPath = os.path.join(__dir__, 'Gui/Resources/Icons')


def getIcon(iconName):
    return os.path.join(iconPath, iconName)


def updateMenu(workbench):
    if workbench == 'CAMWorkbench':

        print('FreeCAD Turning Addon loaded:', workbench)

        mw = FreeCADGui.getMainWindow()
        addonMenu = None

        CAMMenu = None
        # Detached menus remain as children after a workbench switch.
        activeActions = mw.menuBar().actions()
        for menu in mw.findChildren(QtGui.QMenu, "&CAM"):
            if menu.menuAction() in activeActions:
                CAMMenu = menu
                break
        if CAMMenu is None:
            FreeCAD.Console.PrintError("Turning Addon: CAM menu not found.\n")
            return

        camAddons = None
        for action in CAMMenu.actions():
            if action.menu() is not None and action.menu().objectName() == "CAM_Addons":
                camAddons = action.menu()
                break

        if camAddons is None:
            camAddons = QtGui.QMenu("CAM Addons", CAMMenu)
            camAddons.setObjectName("CAM_Addons")

            dressupMenu = CAMMenu.findChild(QtGui.QMenu, "Path Dressup")

            if dressupMenu is not None:
                CAMMenu.insertMenu(dressupMenu.menuAction(), camAddons)
            else:
                CAMMenu.addMenu(camAddons)

        for action in camAddons.actions():
            if action.menu() is not None and action.menu().objectName() == "Turning_Addons":
                addonMenu = action.menu()
                break

        if addonMenu is None:
            addonMenu = QtGui.QMenu("Turning Addon", camAddons)
            addonMenu.setObjectName("Turning_Addons")
            addonMenu.setIcon(QtGui.QIcon(getIcon('CAM-TurningAddon.svg')))
            camAddons.addMenu(addonMenu)

        # list of commands to add to the menu, add new commands here:
        commands = ['TurnFace', 'TurnProfile', 'TurnPartoff', 'TurnRough', 'TurnToolHelper']

        # load the commands to the FreeCAD Menu
        for command in commands:
            if any(action.objectName() == "CAM_" + command for action in addonMenu.actions()):
                continue
            print('Loading Command: ', command)
            # create an action for this addon
            action = createAction(addonMenu, command)
            # append this addon to addon menu
            addonMenu.addAction(action)


def createAction(menu, actionName):
    # space the actionName at caps
    text = re.sub(r"(\w)([A-Z])", r"\1 \2", actionName)
    command = "CAM_" + actionName
    icon = "CAM-" + actionName + ".svg"

    action = QtGui.QAction(menu)
    action.setObjectName(command)
    action.setText(text)
    action.setIcon(QtGui.QIcon(getIcon(icon)))
    action.setStatusTip("CAM " + actionName + " Operation")
    action.triggered.connect(lambda: FreeCADGui.runCommand(command, 0))

    return action


FreeCADGui.getMainWindow().workbenchActivated.connect(updateMenu)
