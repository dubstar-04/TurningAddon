# -*- coding: utf-8 -*-

# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2023 Daniel Wood <s.d.wood.82@googlemail.com>            *
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
import re
import os

import FreeCADGui
from PySide import QtGui

# import all turning operations
from PathTurnScripts import PathTurnFaceGui  # noqa: F401
from PathTurnScripts import PathTurnPartoffGui  # noqa: F401
from PathTurnScripts import PathTurnProfileGui  # noqa: F401
from PathTurnScripts import PathTurnRoughGui  # noqa: F401
from PathTurnScripts import PathTurnToolHelperGui  # noqa: F401

import PathAddonCommon


def getIcon(iconName):
    __dir__ = os.path.dirname(__file__)
    iconPath = os.path.join(__dir__, 'Gui/Resources/Icons')
    return os.path.join(iconPath, iconName)


def createAction(parent, actionName):
    """Create and return a QAction to trigger a turning command"""
    # space the actionName at caps
    text = re.sub(r"(\w)([A-Z])", r"\1 \2", actionName)
    command = "Path_" + actionName
    icon = "Path-" + actionName + ".svg"
    action = QtGui.QAction(parent)
    action.setText(text)
    action.setIcon(QtGui.QPixmap(getIcon(icon)))
    action.setStatusTip("Path " + actionName + " Operation")
    action.triggered.connect(lambda: FreeCADGui.runCommand(command, 0))

    return action


def getActions(parent):
    """ return a list of turning actions"""
    actions = []

    # list of commands to add to the menu, add new commands here:
    commands = ['TurnFace', 'TurnProfile', 'TurnPartoff', 'TurnRough', 'TurnToolHelper']

    # Add the commands to the addon Menu
    for command in commands:
        print('Loading Command: ', command)
        # create an action for this addon
        action = createAction(parent, command)
        # append this addon to addon menu
        actions.append(action)

    return actions


def updateMenu(workbench):
    if workbench == 'PathWorkbench':

        print('FreeCAD Turning Addon loaded:', workbench)

        mw = FreeCADGui.getMainWindow()

        pathAddonMenu = PathAddonCommon.loadPathAddonMenu()
        turningAddonAction = mw.findChild(QtGui.QAction, "TurningAddon")
        turningActions = getActions(mw)
        PathAddonCommon.loadToolBar("Turning Addon", turningActions)

        if not turningAddonAction:
            # create addon action
            turningAddonAction = QtGui.QAction(mw)
            turningAddonAction.setObjectName("TurningAddon")
            turningAddonAction.setIconText("Turning Addon")
            turningAddonAction.setIcon(QtGui.QPixmap(getIcon('Path-TurningAddon.svg')))
            # create addon menu
            turningAddonMenu = QtGui.QMenu("Turning Addon Menu")
            turningAddonMenu.setObjectName("TurningAddonMenu")
            turningAddonMenu.setIcon(QtGui.QPixmap(getIcon('Path-TurningAddon.svg')))

            # Add the commands to the addon Menu
            for action in turningActions:
                turningAddonMenu.addAction(action)

            turningAddonAction.setMenu(turningAddonMenu)
            pathAddonMenu.addAction(turningAddonAction)


FreeCADGui.getMainWindow().workbenchActivated.connect(updateMenu)
