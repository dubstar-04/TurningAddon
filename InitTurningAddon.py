# -*- coding: utf-8 -*-

# Copyright (c) 2020 Daniel Wood <s.d.wood.82@googlemail.com>
# SPDX-License-Identifier: LGPL-2.0-or-later
# See LICENSE for terms. This software is provided WITHOUT ANY WARRANTY.

import FreeCAD
import FreeCADGui
from PySide import QtGui

from PathTurnScripts import initialize

initialize()

# import all turning operations
from PathTurnScripts import PathTurnDrillGui  # noqa: F401
from PathTurnScripts import PathTurnPartoffGui  # noqa: F401
from PathTurnScripts import PathTurnProfileGui  # noqa: F401
from PathTurnScripts import PathTurnRoughGui  # noqa: F401
from PathTurnScripts import PathTurnToolLibraryGui  # noqa: F401
from PathTurnScripts import PathTurnThreadGui  # noqa: F401
from PathTurnScripts import PathTurnSimulationGui  # noqa: F401
import os

__dir__ = os.path.dirname(__file__)
iconPath = os.path.join(__dir__, 'Gui/Resources/Icons')

commands = [
    'TurnRough', 'TurnProfile','TurnDrill','TurnThread','TurnPartoff',
    'TurnToolLibrary', 'TurnSimulation',
]
FreeCADGui.addIconPath(iconPath)


def getIcon(iconName):
    return os.path.join(iconPath, iconName)


def updateMenu(workbench):
    if workbench == 'CAMWorkbench':

        print('FreeCAD Turning Addon loaded:', workbench)

        activeWorkbench = FreeCADGui.activeWorkbench()
        if 'Turning Addon' not in activeWorkbench.listToolbars():
            activeWorkbench.appendToolbar(
                'Turning Addon', ['CAM_' + command for command in commands])
            activeWorkbench.reloadActive()

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
    command = "CAM_" + actionName
    info = FreeCADGui.Command.get(command).getInfo()

    action = QtGui.QAction(menu)
    action.setObjectName(command)
    action.setText(info["menuText"])
    action.setIcon(QtGui.QIcon(getIcon(info["pixmap"] + ".svg")))
    action.setStatusTip(info["toolTip"])
    action.triggered.connect(lambda: FreeCADGui.runCommand(command, 0))

    return action


FreeCADGui.getMainWindow().workbenchActivated.connect(updateMenu)
