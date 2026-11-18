# -*- coding: utf-8 -*-

# SPDX-License-Identifier: LGPL-2.0-or-later
# See LICENSE for terms. This software is provided WITHOUT ANY WARRANTY.

from pivy import coin

RAPID_COLOUR = (0.85, 0.15, 0.15)
RAPID_PATTERN = 0x0F0F


class ToolpathOverlay:
	''' unpickable 3D view overlay of the G-code moves around the tool '''

	def __init__(self, root):
		self.root = root
		self.move = None
		self.switch = coin.SoSwitch()
		self.switch.whichChild = coin.SO_SWITCH_ALL
		node = coin.SoSeparator()
		pick = coin.SoPickStyle()
		pick.style = coin.SoPickStyle.UNPICKABLE
		node.addChild(pick)
		# Draw over the stock so the path stays visible inside the material.
		depth = coin.SoDepthBuffer()
		depth.test = False
		node.addChild(depth)
		light = coin.SoLightModel()
		light.model = coin.SoLightModel.BASE_COLOR
		node.addChild(light)
		self.feeds = self._addLines(node, 2, 0xFFFF)
		self.rapids = self._addLines(node, 1, RAPID_PATTERN)
		self.rapids[0].diffuseColor = RAPID_COLOUR
		self.switch.addChild(node)
		self.root.addChild(self.switch)

	@staticmethod
	def _addLines(parent, width, pattern):
		group = coin.SoSeparator()
		material = coin.SoMaterial()
		style = coin.SoDrawStyle()
		style.lineWidth = width
		style.linePattern = pattern
		coordinates = coin.SoCoordinate3()
		lines = coin.SoLineSet()
		for child in (material, style, coordinates, lines):
			group.addChild(child)
		parent.addChild(group)
		return material, coordinates, lines

	def setVisible(self, visible):
		self.switch.whichChild = coin.SO_SWITCH_ALL if visible else coin.SO_SWITCH_NONE

	def show(self, move, polylines, colour):
		self.clear()
		self.move = move
		self.feeds[0].diffuseColor = colour
		for (_, coordinates, lines), rapid in ((self.feeds, False), (self.rapids, True)):
			runs = [points for isRapid, points in polylines if isRapid == rapid]
			if runs:
				coordinates.point.setValues(
					[(point.x, point.y, point.z) for points in runs for point in points])
				lines.numVertices.setValues([len(points) for points in runs])

	def clear(self):
		self.move = None
		for _, coordinates, lines in (self.feeds, self.rapids):
			coordinates.point.deleteValues(0)
			lines.numVertices.deleteValues(0)

	def close(self):
		if self.root is not None:
			self.root.removeChild(self.switch)
			self.root = None
