# -*- coding: utf-8 -*-

# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2021 Daniel Wood <s.d.wood.82@googlemail.com>            *
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

from PySide import QtGui, QtCore

import FreeCADGui

dir = os.path.dirname(__file__)
ui_name = "PathSimTimelineGui.ui"
path_to_ui = dir + "/" + ui_name
path_to_icons = os.path.join(dir, "Icons")

mw = FreeCADGui.getMainWindow()


class ProgressGraphicsShape(QtGui.QGraphicsObject):
    ''' graphics item to represent the progress marker on the timeline '''

    progresschange = QtCore.Signal(float)
    skipRequested = QtCore.Signal(float)

    def __init__(self, w, h):
        super().__init__()
        self.setFlag(QtGui.QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QtGui.QGraphicsItem.ItemSendsGeometryChanges, True)
        self.xMax = 0
        self.width = w
        self.height = h
        self.skipping = False  # true if the widget is being dragged
        self.segments = []
        self.brush = QtGui.QBrush()
        self.brush.setStyle(QtCore.Qt.SolidPattern)
        self.pen = QtGui.QPen()

    def setColour(self, colour):
        self.brush.setColor(colour)
        self.pen.setColor(colour)

    def setRect(self, x, y, w, h):
        self.prepareGeometryChange()
        self.setPos(x, y)
        self.width = w
        self.height = h
        self.update()

    def setMaxX(self, x):
        self.xMax = x

    def setBrush(self, brush):
        self.brush = brush

    def setPen(self, pen):
        self.pen = pen

    def setSegments(self, segments):
        self.segments = list(segments)
        self.update()

    def paint(self, painter, option, widget):
        painter.setBrush(self.brush)
        painter.setPen(self.pen)
        painter.drawRect(QtCore.QRectF(
            0, -self.height / 2, self.width, self.height))
        if self.segments:
            painter.save()
            painter.setPen(QtCore.Qt.NoPen)
            for start, end, colour in self.segments:
                painter.setBrush(colour)
                painter.drawRect(QtCore.QRectF(
                    start * self.width, -self.height / 2,
                    (end - start) * self.width, self.height))
            painter.restore()

    def boundingRect(self):
        ''' include a larger click target around the visible timeline '''
        height = max(24, self.height)
        return QtCore.QRectF(0, -height / 2, self.width, height)

    def itemChange(self, change, value):

        if change == QtGui.QGraphicsItem.ItemPositionChange:

            x = value.x()

            if x < 0:
                x = 0

            if x > self.xMax:
                x = self.xMax

            self.progresschange.emit(x)

            return QtCore.QPointF(x, self.y())

        return value

    def mouseReleaseEvent(self, event):
        movable = self.flags() & QtGui.QGraphicsItem.ItemIsMovable
        if movable:
            super().mouseReleaseEvent(event)
        position = self.pos().x() if movable else event.pos().x()
        self.skipping = False
        self.skipRequested.emit(position)
        event.accept()

    def mousePressEvent(self, event):
        self.skipping = True
        if self.flags() & QtGui.QGraphicsItem.ItemIsMovable:
            super().mousePressEvent(event)
        else:
            event.accept()


class ProgressMarker(ProgressGraphicsShape):
    def boundingRect(self):
        return QtCore.QRectF(-self.width / 2, -self.height / 2, self.width, self.height)

    def shape(self):
        path = QtGui.QPainterPath()
        path.addEllipse(self.boundingRect())
        return path

    def paint(self, painter, option, widget):
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(self.brush)
        painter.drawEllipse(self.boundingRect())


class timeline(QtCore.QObject):
    ''' form and controls shown on screen during the simulation '''
    # quitSignal = QtCore.Signal()
    playSignal = QtCore.Signal()
    stopSignal = QtCore.Signal()
    progressChangedSignal = QtCore.Signal(float)
    skipRequested = QtCore.Signal(float)
    stepBackwardRequested = QtCore.Signal()
    stepForwardRequested = QtCore.Signal()
    stockVisibilityChanged = QtCore.Signal(bool)

    def __init__(self):
        super(timeline, self).__init__()
        #Build GUI
        self.form = FreeCADGui.PySideUic.loadUi(path_to_ui)
        self.form.setParent(mw.centralWidget())
        self.form.setWindowFlags(QtCore.Qt.Widget | QtCore.Qt.FramelessWindowHint | QtCore.Qt.CustomizeWindowHint)
        self.form.setAttribute(QtCore.Qt.WA_TranslucentBackground)

        # timeline members
        self.progress = 0  # progess complete as a float i.e. 1.0 = %100 
        self.progressMarker = None  # graphics item representing the progress marker
        self.progressBarWidth = 0  # length of the timeline used for progess calculations and positions
        self.operationRanges = []

        self.timeLine = ProgressGraphicsShape(10, 12)
        self.timeLine.setFlag(QtGui.QGraphicsItem.ItemIsMovable, False)
        self.progressMarker = ProgressMarker(16, 16)
        self.progressMarker.setZValue(1)


        ### collect widget
        self.previousOperationButton = self.form.findChild(
            QtGui.QPushButton, "previousOperationButton")
        self.playButton = self.form.findChild(QtGui.QPushButton, "playButton")
        self.stepBackButton = self.form.findChild(QtGui.QPushButton, "stepBackButton")
        self.stepButton = self.form.findChild(QtGui.QPushButton, "stepButton")
        self.nextOperationButton = self.form.findChild(
            QtGui.QPushButton, "nextOperationButton")
        self.stockButton = self.form.findChild(QtGui.QPushButton, "stockButton")
        buttonLayout = self.form.findChild(QtGui.QWidget, "buttonGroup").layout()
        buttonLayout.setContentsMargins(0, 0, 0, 0)
        buttonLayout.setSpacing(4)
        buttonLayout.setSizeConstraint(QtGui.QLayout.SetFixedSize)
        self.setPlaying(False)
        self.previousOperationButton.setIcon(
            QtGui.QIcon(os.path.join(path_to_icons, "previous_operation.svg")))
        self.stepBackButton.setIcon(QtGui.QIcon(os.path.join(path_to_icons, "step_backward.svg")))
        self.stepButton.setIcon(QtGui.QIcon(os.path.join(path_to_icons, "step_forward.svg")))
        self.nextOperationButton.setIcon(
            QtGui.QIcon(os.path.join(path_to_icons, "next_operation.svg")))
        stockIcon = QtGui.QIcon()
        stockIcon.addFile(os.path.join(path_to_icons, "stock_visible.svg"),
                          QtCore.QSize(), QtGui.QIcon.Normal, QtGui.QIcon.On)
        stockIcon.addFile(os.path.join(path_to_icons, "stock_hidden.svg"),
                          QtCore.QSize(), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        self.stockButton.setIcon(stockIcon)
        self.updateStockButton()
        self.progressBar = self.form.progressBar
        self.progressBar.setRenderHint(QtGui.QPainter.Antialiasing)
        self.scene = QtGui.QGraphicsScene()
        self.progressBar.setScene(self.scene)

        ### connect
        self.previousOperationButton.clicked.connect(self.jumpToPreviousOperation)
        self.playButton.clicked.connect(self.play)
        self.stepBackButton.clicked.connect(self.stepBackwardRequested.emit)
        self.stepButton.clicked.connect(self.stepForwardRequested.emit)
        self.nextOperationButton.clicked.connect(self.jumpToNextOperation)
        self.stockButton.toggled.connect(self.onStockToggled)
        # self.progressMarker.progresschange.connect(self.progressUpdate)
        self.progressMarker.skipRequested.connect(self.skip)
        self.timeLine.skipRequested.connect(self.skip)

        # initialise form
        self.initProgressBar()
        self._positionTimer = QtCore.QTimer(self)
        self._positionTimer.setSingleShot(True)
        self._positionTimer.timeout.connect(self.setPosition)
        mw.installEventFilter(self)
        mw.centralWidget().installEventFilter(self)
        self.setPosition()
        self.setProgress(0)

    def initProgressBar(self):
        ''' initialise the ui, loading the graphics widgets'''

        def addToScene(colour, drawItem):
            drawItem.setColour(colour)
            self.scene.addItem(drawItem)

        addToScene(QtGui.QColor(175, 175, 175, 175), self.timeLine)
        addToScene(QtGui.QColor(0, 0, 0), self.progressMarker)


    def eventFilter(self, object, event):
        ''' reposition after FreeCAD has finished updating its dock layout '''
        if event.type() in (
                QtCore.QEvent.Type.Resize, QtCore.QEvent.Type.LayoutRequest,
                QtCore.QEvent.Type.Show):
            self._positionTimer.start(0)

        return False

    def setProgress(self, progress):
        ''' set the progress for the current simulation'''
        self.progress = progress
        pos = self.progressMarker.pos()
        position = self.progress * self.progressBarWidth
        if self.progressMarker.skipping is False:
            self.progressMarker.setPos(position, pos.y())

    def setOperationRanges(self, ranges):
        self.operationRanges = list(ranges)
        self.timeLine.setSegments(self.operationRanges)

    def progressUpdate(self, position):
        ''' handle progress changes from the progress marker position '''
        percent_progress = position / self.progressBarWidth
        if self.progress * 0.05 > percent_progress or self.progress * 0.05 < percent_progress:
            self.progress = percent_progress
            # print("progress Update:", progress, "=", round(self.progress * 100, 2), "%")
            self.progressChangedSignal.emit(self.progress)

    def setPosition(self):
        ''' position the form on the screen and progress bar on the form'''
        cen = mw.centralWidget()
        cengeom = cen.geometry()

        x = cengeom.width() * 0.1
        y = max(0, cengeom.height() - self.form.height() - 36)
        newWidth = cengeom.width() * 0.8
        newHeight = self.form.height()
        self.form.setGeometry(round(x), round(y), round(newWidth), newHeight)

        self.progressBarWidth = self.form.geometry().width() * 0.9
        self.progressMarker.setMaxX(self.progressBarWidth)
        self.timeLine.setRect(0, 0, self.progressBarWidth, self.timeLine.height)
        radius = self.progressMarker.width / 2
        halfHeight = max(radius, self.timeLine.boundingRect().height() / 2)
        self.scene.setSceneRect(
            -radius, -halfHeight, self.progressBarWidth + 2 * radius, 2 * halfHeight)
        self.setProgress(self.progress)

    def play(self):
        ''' toggle playback using the state confirmed by the task panel '''
        if self.playing:
            self.stopSignal.emit()
        else:
            self.playSignal.emit()

    def setPlaying(self, playing):
        self.playing = playing
        icon = "pause.svg" if playing else "play.svg"
        label = "Pause simulation" if playing else "Play simulation"
        self.playButton.setIcon(QtGui.QIcon(os.path.join(path_to_icons, icon)))
        self.playButton.setToolTip(label)
        self.playButton.setAccessibleName(label)

    def setStockVisible(self, visible):
        ''' set the button state without emitting stockVisibilityChanged '''
        blocked = self.stockButton.blockSignals(True)
        self.stockButton.setChecked(visible)
        self.stockButton.blockSignals(blocked)
        self.updateStockButton()

    def onStockToggled(self, visible):
        self.updateStockButton()
        self.stockVisibilityChanged.emit(visible)

    def updateStockButton(self):
        label = "Hide stock" if self.stockButton.isChecked() else "Show stock"
        self.stockButton.setToolTip(label)
        self.stockButton.setAccessibleName(label)

    def jumpToPreviousOperation(self):
        ''' seek to the beginning of the previous operation '''
        if not self.operationRanges:
            return
        current = next((index for index, (start, end, _) in enumerate(self.operationRanges)
                        if start <= self.progress < end), len(self.operationRanges) - 1)
        target = max(0, current - 1)
        self.skip(self.operationRanges[target][0] * self.progressBarWidth)

    def jumpToNextOperation(self):
        ''' seek to the next operation, or the end of the last operation '''
        if not self.operationRanges:
            return
        current = next((index for index, (start, end, _) in enumerate(self.operationRanges)
                        if start <= self.progress < end), len(self.operationRanges) - 1)
        if current + 1 < len(self.operationRanges):
            self.skip(self.operationRanges[current + 1][0] * self.progressBarWidth)
        else:
            self.skip(self.progressBarWidth)

    def skip(self, position):
        ''' handle skip signals '''
        progress = max(0.0, min(1.0, position / self.progressBarWidth))
        self.setProgress(progress)
        self.skipRequested.emit(progress)

    def show(self):
        ''' show the player controls '''
        self.form.show()

    def quit(self, data=None):
        ''' handle the form being closed'''
        self._positionTimer.stop()
        mw.removeEventFilter(self)
        mw.centralWidget().removeEventFilter(self)
        self.form.close()
        self.deleteLater()
