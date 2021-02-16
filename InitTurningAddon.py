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

import FreeCADGui
from PySide import QtGui

# import all turning operations
from PathTurnScripts import PathTurnFaceGui  # noqa: F401
from PathTurnScripts import PathTurnPartoffGui  # noqa: F401
from PathTurnScripts import PathTurnProfileGui  # noqa: F401
from PathTurnScripts import PathTurnRoughGui  # noqa: F401
from PathTurnScripts import PathTurnThreadGui  # noqa: F401
from PathTurnScripts import PathTurnToolHelperGui  # noqa: F401
import os
import re

__dir__ = os.path.dirname(__file__)
iconPath = os.path.join(__dir__, 'Gui/Resources/Icons')


def getIcon(iconName):
    return os.path.join(iconPath, iconName)


def updateMenu(workbench):
    if workbench == 'PathWorkbench':

        print('FreeCAD Turning Addon loaded:', workbench)

        mw = FreeCADGui.getMainWindow()
        addonMenu = None

        # Find the main path menu
        pathMenu = mw.findChild(QtGui.QMenu, "&Path")

        for menu in pathMenu.actions():
            if menu.text() == "Turning Addon":
                # create a new addon menu
                addonMenu = menu.menu()
                break

        if addonMenu is None:
            addonMenu = QtGui.QMenu("Turning Addon")
            addonMenu.setObjectName("Turning_Addons")
            addonMenu.setIcon(QtGui.QPixmap(getIcon('Path-TurningAddon.svg')))

            # Find the dressup menu entry
            dressupMenu = mw.findChild(QtGui.QMenu, "Path Dressup")

            pathMenu.insertMenu(dressupMenu.menuAction(), addonMenu)

        # list of commands to add to the menu, add new commands here:
        commands = ['TurnFace', 'TurnProfile', 'TurnPartoff', 'TurnRough', 'TurnThread', 'TurnToolHelper']

        # load the commands to the FreeCAD Menu
        for command in commands:
            print('Loading Command: ', command)
            # create an action for this addon
            action = createAction(addonMenu, command)
            # append this addon to addon menu
            addonMenu.addAction(action)


def createAction(menu, actionName):
    # space the actionName at caps
    text = re.sub(r"(\w)([A-Z])", r"\1 \2", actionName)
    command = "Path_" + actionName
    icon = "Path-" + actionName + ".svg"

    action = QtGui.QAction(menu)
    action.setText(text)
    action.setIcon(QtGui.QPixmap(getIcon(icon)))
    action.setStatusTip("Path " + actionName + " Operation")
    action.triggered.connect(lambda: FreeCADGui.runCommand(command, 0))

    return action


FreeCADGui.getMainWindow().workbenchActivated.connect(updateMenu)
