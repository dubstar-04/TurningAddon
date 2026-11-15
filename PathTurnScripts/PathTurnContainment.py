"""Turning containment section view with drag handles."""

import math
from functools import partial

import FreeCAD
import FreeCADGui
import Part
import Path.Log as PathLog
from pivy import coin
from PathScripts import PathUtils
from liblathe.op.base import MachiningMode

from .PathTurnAddonHelpers import getContainment


class ContainmentPreview:
    # Handle half-length in screen pixels, independent of zoom and containment size.
    HANDLE_PIXELS = 16
    # Half-length of the hover/drag arrow, in handle units.
    ARROW_REACH = 2.5
    PREVIEW_COLOR = (0.0, 1.0, 0.6)
    HANDLE_COLOR = (1.0, 0.0, 0.0)

    def __init__(self, root, set_limit, enabled):
        self.root = root
        self.set_limit = set_limit
        self.enabled = enabled
        self.dragging = False
        self.camera_sensor = None
        self.camera = None
        self.event_callback = None
        self.dragger_callbacks = []
        self.handle_positions = []
        self.handle_arrows = []
        self.clip_planes = {}
        self.section_key = None
        self.node = coin.SoSeparator()
        # Keep the limits readable through the model without changing its display.
        depth = coin.SoDepthBuffer()
        depth.test = False
        depth.getField("write").setValue(False)
        self.node.addChild(depth)
        light = coin.SoLightModel()
        light.model = coin.SoLightModel.BASE_COLOR
        self.node.addChild(light)
        self.section_caps = coin.SoSeparator()
        caps_pick = coin.SoPickStyle()
        caps_pick.style = coin.SoPickStyle.UNPICKABLE
        self.section_caps.addChild(caps_pick)
        self.node.addChild(self.section_caps)
        # Keep the stock guide separate so redrawing limits during a drag leaves it intact.
        self.stock_graphics = coin.SoSeparator()
        stock_pick = coin.SoPickStyle()
        stock_pick.style = coin.SoPickStyle.UNPICKABLE
        self.stock_graphics.addChild(stock_pick)
        self.node.addChild(self.stock_graphics)
        self.graphics = coin.SoSeparator()
        pick = coin.SoPickStyle()
        pick.style = coin.SoPickStyle.UNPICKABLE
        self.graphics.addChild(pick)
        self.node.addChild(self.graphics)
        self.snap_highlight = coin.SoSeparator()
        highlight_pick = coin.SoPickStyle()
        highlight_pick.style = coin.SoPickStyle.UNPICKABLE
        self.snap_highlight.addChild(highlight_pick)
        self.node.addChild(self.snap_highlight)
        self.handles = coin.SoSeparator()
        handle_pick = coin.SoPickStyle()
        handle_pick.style = coin.SoPickStyle.SHAPE
        self.handles.addChild(handle_pick)
        self.node.addChild(self.handles)
        self.visibility = coin.SoSwitch()
        self.visibility.whichChild = coin.SO_SWITCH_ALL
        self.visibility.addChild(self.node)
        self.root.addChild(self.visibility)

    def set_visible(self, visible):
        self.visibility.whichChild = coin.SO_SWITCH_ALL if visible else coin.SO_SWITCH_NONE

    def clear(self):
        if not self.dragging:
            self._remove_dragger_callbacks()
            self._stop_camera_tracking()
            self.handle_positions.clear()
            self.handle_arrows.clear()
            self._clear_graphics()
            while self.stock_graphics.getNumChildren() > 1:
                self.stock_graphics.removeChild(1)
            self._clear_snap_highlight()
            while self.handles.getNumChildren() > 1:
                self.handles.removeChild(1)

    def _remove_dragger_callbacks(self):
        for view, dragger, kind, callback in self.dragger_callbacks:
            view.removeDraggerCallback(dragger, kind, callback)
        self.dragger_callbacks.clear()

    def _clear_graphics(self):
        # Preserve the unpickable style as the first child.
        while self.graphics.getNumChildren() > 1:
            self.graphics.removeChild(1)

    def _clear_snap_highlight(self):
        while self.snap_highlight.getNumChildren() > 1:
            self.snap_highlight.removeChild(1)

    def show_stock(self, edges, rear=False, *, polygons=()):
        sign = -1 if rear else 1
        fill = coin.SoSeparator()
        material = coin.SoMaterial()
        material.diffuseColor = (0.95, 0.6, 0.12)
        material.transparency = 0.65
        fill.addChild(material)
        hints = coin.SoShapeHints()
        hints.vertexOrdering = coin.SoShapeHints.UNKNOWN_ORDERING
        hints.shapeType = coin.SoShapeHints.UNKNOWN_SHAPE_TYPE
        hints.faceType = coin.SoShapeHints.CONVEX
        fill.addChild(hints)
        coordinates = coin.SoCoordinate3()
        coordinates.point.setValues([
            (sign * x, 0, z) for polygon in polygons for x, z in polygon])
        fill.addChild(coordinates)
        faces = coin.SoFaceSet()
        faces.numVertices.setValues([len(polygon) for polygon in polygons])
        fill.addChild(faces)
        # Draw the fill first so the limit and stock outlines remain legible.
        self.stock_graphics.addChild(fill)
        group = coin.SoSeparator()
        material = coin.SoMaterial()
        material.diffuseColor = (0.95, 0.6, 0.12)
        group.addChild(material)
        style = coin.SoDrawStyle()
        style.lineWidth = 2
        group.addChild(style)
        coordinates = coin.SoCoordinate3()
        coordinates.point.setValues([
            (sign * x, 0, z) for edge in edges
            for x, z in ((edge[0], edge[1]), (edge[2], edge[3]))])
        group.addChild(coordinates)
        lines = coin.SoLineSet()
        lines.numVertices.setValues([2] * len(edges))
        group.addChild(lines)
        self.stock_graphics.addChild(group)

    def close(self):
        if self.root is not None:
            self.exit_section()
            self._remove_dragger_callbacks()
            self._stop_camera_tracking()
            self.root.removeChild(self.visibility)
            self.root = None

    def update(self, obj):
        bounds = getContainment(obj)
        values = (bounds.XMin, bounds.XMax, bounds.ZMin, bounds.ZMax)
        if (not all(math.isfinite(value) for value in values)
                or values[0] >= values[1] or values[2] >= values[3]
                or (not getattr(obj.Proxy, "centreline_drilling", False)
                    and obj.MinDiameter.Value < 0)):
            raise ValueError(FreeCAD.Qt.translate(
                "PathTurn", "Containment requires 0 <= Radial Min < Radial Max "
                "and Axial Min < Axial Max."))

        job = PathUtils.findParentJob(obj)
        if job is None:
            raise ValueError(FreeCAD.Qt.translate(
                "PathTurn", "Containment clearance requires a parent CAM job."))
        offset = job.SetupSheet.SafeHeightOffset
        if not math.isfinite(offset.Value) or offset.Value < 0:
            raise ValueError(FreeCAD.Qt.translate(
                "PathTurn", "Clearance must be finite and non-negative."))
        clearance = max(offset.Value, 0.01)
        self.obj = obj
        self.job = job
        self.clearance = clearance
        self.bounds = (bounds.XMin, bounds.XMax, bounds.ZMin, bounds.ZMax)
        # OCC sectioning can process repaint events, so finish it before removing the old preview.
        self._enter_section()
        self.clear()
        self._draw(self.bounds)
        self._make_handles()

    def _enter_section(self):
        # Cut away the half facing the front view without changing the document.
        for obj in self._geometry_objects():
            if obj.ViewObject is None:
                continue
            node = obj.ViewObject.RootNode
            previous = self.clip_planes.get(obj.Name)
            if previous is not None:
                previous_node, plane = previous
                if previous_node == node and node.findChild(plane) >= 0:
                    continue
                index = previous_node.findChild(plane)
                if index >= 0:
                    previous_node.removeChild(index)
            else:
                plane = coin.SoClipPlane()
                plane.plane.setValue(coin.SbPlane(coin.SbVec3f(0, 1, 0), 0))
            node.insertChild(plane, 0)
            self.clip_planes[obj.Name] = (node, plane)
        self._draw_section_caps()

    def exit_section(self):
        for node, plane in self.clip_planes.values():
            index = node.findChild(plane)
            if index >= 0:
                node.removeChild(index)
        self.clip_planes.clear()
        self.section_key = None
        while self.section_caps.getNumChildren() > 1:
            self.section_caps.removeChild(1)

    def _draw_section_caps(self):
        # Limit changes leave the model unchanged, so skip the slow OCC section.
        key = tuple((obj.Name, obj.Shape.hashCode(), str(obj.Shape.Placement))
                    for obj in self.job.Model.Group)
        if key == self.section_key:
            return
        # Keep the current section visible until its replacement is ready.
        caps = coin.SoSeparator()
        caps.addChild(self.section_caps.getChild(0))
        points, indices = [], []
        for obj in self.job.Model.Group:
            shape = obj.Shape
            if shape.isNull() or not shape.Solids:
                continue
            box = shape.BoundBox
            margin = max(box.XLength, box.ZLength, 1)
            x0, x1 = box.XMin - margin, box.XMax + margin
            z0, z1 = box.ZMin - margin, box.ZMax + margin
            plane = Part.Face(Part.makePolygon([
                FreeCAD.Vector(x0, 0, z0), FreeCAD.Vector(x1, 0, z0),
                FreeCAD.Vector(x1, 0, z1), FreeCAD.Vector(x0, 0, z1),
                FreeCAD.Vector(x0, 0, z0)]))
            try:
                section = shape.common(plane)
            except Part.OCCError as error:
                PathLog.warning(FreeCAD.Qt.translate(
                    "PathTurn", "Cannot section {label}: {error}").format(
                        label=obj.Label, error=str(error)))
                continue
            for face in section.Faces:
                vertices, triangles = face.tessellate(max(margin * 1e-3, 0.01))
                base = len(points)
                points.extend((vertex.x, 0, vertex.z) for vertex in vertices)
                for triangle in triangles:
                    indices.extend((*(base + index for index in triangle), -1))
            for edge in section.Edges:
                self._boundary([(point.x, 0, point.z) for point in edge.discretize(Deflection=0.01)],
                               (0.2, 0.22, 0.28), parent=caps, halo=False)
        if indices:
            fill = coin.SoSeparator()
            material = coin.SoMaterial()
            material.diffuseColor = (0.62, 0.64, 0.7)
            fill.addChild(material)
            hints = coin.SoShapeHints()
            hints.vertexOrdering = coin.SoShapeHints.UNKNOWN_ORDERING
            fill.addChild(hints)
            coordinates = coin.SoCoordinate3()
            coordinates.point.setValues(points)
            fill.addChild(coordinates)
            faces = coin.SoIndexedFaceSet()
            faces.coordIndex.setValues(indices)
            fill.addChild(faces)
            # Draw the cap beneath its outline.
            caps.insertChild(fill, 1)
        self.node.replaceChild(self.section_caps, caps)
        self.section_caps = caps
        self.section_key = key

    def _draw(self, bounds, active=None, snapped=False):
        self._clear_graphics()
        x0, x1, z0, z1 = bounds
        rear = x1 <= 0
        inner, outer = (x1, x0) if rear else (x0, x1)
        sign = -1 if rear else 1
        self._fill(x0, x1, z0, z1)

        def draw_limit(name, points):
            dragging = active == name and not snapped
            self._boundary(
                points, self.HANDLE_COLOR if dragging else self.PREVIEW_COLOR,
                dotted=dragging)

        draw_limit("radialMax", [(outer, 0, z0), (outer, 0, z1)])
        draw_limit("radialMin", [(inner, 0, z0), (inner, 0, z1)])
        draw_limit("axialMax", [(x0, 0, z1), (x1, 0, z1)])
        draw_limit("axialMin", [(x0, 0, z0), (x1, 0, z0)])
        if getattr(self.obj.Proxy, "centreline_drilling", False):
            self._boundary(
                [(x0, 0, z1 + self.clearance), (x1, 0, z1 + self.clearance)], self.PREVIEW_COLOR,
                dashed=True)
        elif not (getattr(self.obj.Proxy, "supports_internal_mode", False)
                  and str(getattr(self.obj, "Mode", "")) == MachiningMode.INTERNAL.value):
            clearance_x = outer + sign * self.clearance
            self._boundary(
                [(clearance_x, 0, z0), (clearance_x, 0, z1)], self.PREVIEW_COLOR,
                dashed=True)

    def _fill(self, x0, x1, z0, z1):
        fill = coin.SoSeparator()
        material = coin.SoMaterial()
        material.diffuseColor = self.PREVIEW_COLOR
        material.transparency = 0.75
        fill.addChild(material)
        hints = coin.SoShapeHints()
        hints.vertexOrdering = coin.SoShapeHints.UNKNOWN_ORDERING
        fill.addChild(hints)
        coordinates = coin.SoCoordinate3()
        coordinates.point.setValues([(x0, 0, z0), (x1, 0, z0), (x1, 0, z1), (x0, 0, z1)])
        fill.addChild(coordinates)
        face = coin.SoFaceSet()
        face.numVertices.setValue(4)
        fill.addChild(face)
        self.graphics.addChild(fill)

    @classmethod
    def _handle_shape(cls, color, arrow_visible):
        shape = coin.SoSeparator()
        light = coin.SoLightModel()
        light.model = coin.SoLightModel.BASE_COLOR
        shape.addChild(light)
        # Retain the cube-sized pick area around the smaller visible handle.
        hit_area = coin.SoSeparator()
        hidden = coin.SoDrawStyle()
        hidden.style = coin.SoDrawStyle.INVISIBLE
        hit_area.addChild(hidden)
        hit_area.addChild(coin.SoCube())
        shape.addChild(hit_area)
        material = coin.SoMaterial()
        material.diffuseColor = color
        shape.addChild(material)
        dot = coin.SoSphere()
        dot.radius = 0.5
        shape.addChild(dot)
        arrow_switch = coin.SoSwitch()
        arrow_switch.whichChild = coin.SO_SWITCH_ALL if arrow_visible else coin.SO_SWITCH_NONE
        arrows = coin.SoSeparator()
        shaft = coin.SoSeparator()
        rotation = coin.SoRotationXYZ()
        rotation.axis = coin.SoRotationXYZ.Z
        rotation.angle = -math.pi / 2
        shaft.addChild(rotation)
        cylinder = coin.SoCylinder()
        cylinder.radius = 0.1
        cylinder.height = 2 * (cls.ARROW_REACH - 0.7)
        shaft.addChild(cylinder)
        arrows.addChild(shaft)
        for direction in (-1, 1):
            arrow = coin.SoSeparator()
            transform = coin.SoTransform()
            transform.translation.setValue(direction * (cls.ARROW_REACH - 0.35), 0, 0)
            transform.rotation.setValue(coin.SbVec3f(0, 0, 1), -direction * math.pi / 2)
            arrow.addChild(transform)
            cone = coin.SoCone()
            cone.bottomRadius = 0.35
            cone.height = 0.7
            arrow.addChild(cone)
            arrows.addChild(arrow)
        arrow_switch.addChild(arrows)
        shape.addChild(arrow_switch)
        return shape, arrow_switch

    def _make_handles(self):
        view = FreeCADGui.ActiveDocument.activeView()
        x0, x1, z0, z1 = self.bounds
        rear = x1 <= 0
        inner, outer = (x1, x0) if rear else (x0, x1)
        zmid = (z0 + z1) / 2
        xend = inner + (outer - inner) * 0.5
        positions = {
            "radialMax": (outer, 0, zmid),
            "radialMin": (inner, 0, zmid),
            "axialMax": (xend, 0, z1),
            "axialMin": (xend, 0, z0),
        }
        for name, position in positions.items():
            if not self.enabled(name):
                continue
            group = coin.SoSeparator()
            transform = coin.SoTransform()
            transform.translation.setValue(*position)
            if name.startswith("axial"):
                transform.rotation.setValue(coin.SbVec3f(0, 1, 0), -math.pi / 2)
            group.addChild(transform)
            dragger = coin.SoTranslate1Dragger()
            idle, arrow_switch = self._handle_shape(self.HANDLE_COLOR, False)
            dragger.setPart("translator", idle)
            dragger.setPart("translatorActive", self._handle_shape(self.HANDLE_COLOR, True)[0])
            axis = FreeCAD.Vector(0, 0, 1) if name.startswith("axial") else FreeCAD.Vector(1, 0, 0)
            # The world size is updated with the camera, so share it with the callbacks.
            size = [1.0]
            data = (name, position, size, transform)
            # FreeCAD acquires the GIL when native mouse events invoke these callbacks.
            for kind, method in (("addStartCallback", self._start_drag),
                                 ("addValueChangedCallback", self._move_drag),
                                 ("addFinishCallback", self._finish_drag)):
                callback = partial(self._dispatch_drag, method, data, dragger)
                callback = view.addDraggerCallback(dragger, kind, callback)
                self.dragger_callbacks.append((view, dragger, kind, callback))
            group.addChild(dragger)
            self.handles.addChild(group)
            self.handle_positions.append((transform, position, size))
            self.handle_arrows.append((arrow_switch, transform, axis, size))
        self.camera_sensor = coin.SoNodeSensor(self._camera_changed, None)
        self._track_camera(view)
        # Changing the camera type replaces the camera node, so check it on view events.
        self.event_callback = (view, view.addEventCallback("SoEvent", self._view_event))

    def _track_camera(self, view):
        self.camera = view.getCameraNode()
        self.camera_sensor.detach()
        # Node sensors cover orientation, position, orthographic height and perspective angle.
        self.camera_sensor.attach(self.camera)
        self._place_handles()

    def _view_event(self, event):
        view = FreeCADGui.ActiveDocument.activeView()
        if self.dragging:
            return
        if view.getCameraNode() != self.camera:
            self._track_camera(view)
        if event.get("Type") == "SoLocation2Event":
            self._update_hover(view, event["Position"])

    def _update_hover(self, view, mouse):
        hovered = None
        best = None
        for arrow_switch, transform, axis, size in self.handle_arrows:
            point = FreeCAD.Vector(*transform.translation.getValue().getValue())
            centre = view.getPointOnScreen(point)
            tip = view.getPointOnScreen(point + axis * size[0])
            dx, dy = tip[0] - centre[0], tip[1] - centre[1]
            unit = math.hypot(dx, dy)
            mx, my = mouse[0] - centre[0], mouse[1] - centre[1]
            # Once shown, the arrow extends the hover area along its drag axis.
            reach = (self.ARROW_REACH if arrow_switch.whichChild.getValue() == coin.SO_SWITCH_ALL
                     else 1)
            if unit < 1:
                along, across = 0, math.hypot(mx, my) / self.HANDLE_PIXELS
            else:
                along = (mx * dx + my * dy) / (unit * unit)
                across = abs(mx * dy - my * dx) / (unit * self.HANDLE_PIXELS)
            if abs(along) <= reach and across <= 1:
                rank = math.hypot(mx, my)
                if best is None or rank < best:
                    best, hovered = rank, arrow_switch
        for arrow_switch, *_rest in self.handle_arrows:
            state = coin.SO_SWITCH_ALL if arrow_switch is hovered else coin.SO_SWITCH_NONE
            if arrow_switch.whichChild.getValue() != state:
                arrow_switch.whichChild = state

    def _stop_camera_tracking(self):
        if self.camera_sensor is not None:
            self.camera_sensor.detach()
            self.camera_sensor = None
        self.camera = None
        if self.event_callback is not None:
            view, callback = self.event_callback
            view.removeEventCallback("SoEvent", callback)
            self.event_callback = None

    @staticmethod
    def _dispatch_drag(method, data, dragger, _callback_dragger):
        method(data, dragger)

    def _camera_changed(self, data, sensor):
        if not self.dragging:
            self._place_handles()

    def _geometry_objects(self):
        objects = list(self.job.Model.Group)
        if getattr(self.job, "Stock", None):
            objects.append(self.job.Stock)
        return objects

    def _place_handles(self):
        view = FreeCADGui.ActiveDocument.activeView()
        direction = view.getCameraOrientation().multVec(FreeCAD.Vector(0, 0, 1))
        camera = FreeCAD.Vector(*view.getCameraNode().position.getValue().getValue())
        boxes = [obj.Shape.BoundBox for obj in self._geometry_objects() if not obj.Shape.isNull()]
        if not boxes:
            return
        near = max(
            direction.x * (box.XMax if direction.x >= 0 else box.XMin)
            + direction.y * (box.YMax if direction.y >= 0 else box.YMin)
            + direction.z * (box.ZMax if direction.z >= 0 else box.ZMin)
            for box in boxes)
        right = view.getCameraOrientation().multVec(FreeCAD.Vector(1, 0, 0))
        step = max(max(box.DiagonalLength for box in boxes), 1)
        def world_size(point):
            start = view.getPointOnScreen(point)
            end = view.getPointOnScreen(point + right * step)
            pixels = math.hypot(end[0] - start[0], end[1] - start[1])
            return self.HANDLE_PIXELS * step / pixels if pixels > 0 else None

        for transform, position, size in self.handle_positions:
            point = FreeCAD.Vector(*position)
            # The clearance uses the size at the original depth, which is never smaller.
            clearance = 2 * (world_size(point) or size[0])
            # Move handles toward the camera so the model cannot intercept their picks.
            offset = max(0, near - direction.dot(point) + clearance)
            offset = min(offset, max(0, direction.dot(camera - point) - clearance))
            point += direction * offset
            # Size at the final depth so perspective views keep the same on-screen size.
            size[0] = world_size(point) or size[0]
            transform.scaleFactor.setValue(size[0], size[0], size[0])
            transform.translation.setValue(point.x, point.y, point.z)

    def _start_drag(self, data, dragger):
        self.dragging = True
        self.drag_value = None
        self.snap_values = (set(), set())
        self.snap_sources = ({}, {})
        self.snap_edge_points = {}
        self._clear_snap_highlight()
        self.snap_values, self.snap_sources, unsupported = self._snap_candidates()
        if unsupported:
            PathLog.warning(FreeCAD.Qt.translate(
                "PathTurn", "Some model or stock geometry cannot be queried for snapping; "
                "their vertices remain available as snap targets."))

    def _snap_candidates(self):
        radial = {0.0}
        axial = set()
        radial_sources, axial_sources = {}, {}
        unsupported = 0
        for obj in self._geometry_objects():
            shape = obj.Shape
            for vertex in shape.Vertexes:
                point = vertex.Point
                radius = math.hypot(point.x, point.y)
                radial.add(radius)
                axial.add(point.z)
                radial_sources.setdefault(radius, []).append((None, point))
                axial_sources.setdefault(point.z, []).append((None, point))
            edges = shape.Edges
            for edge in edges:
                if edge.Degenerated:
                    continue
                vertices = edge.Vertexes
                # Only highlight edges that lie entirely on the snapped radius or depth.
                if edge.BoundBox.ZLength < 1e-6:
                    # Key by a vertex value so it matches the vertex snap candidates exactly.
                    depth = vertices[0].Point.z if vertices else edge.BoundBox.ZMin
                    axial.add(depth)
                    axial_sources.setdefault(depth, []).append((edge, None))
                    for vertex in vertices:
                        axial_sources.setdefault(vertex.Point.z, []).append((edge, vertex.Point))
                radius = self._constant_radius(edge)
                if radius is not None:
                    radial.add(radius)
                # Circles at one depth appear edge-on as axial lines in the section view.
                if radius is not None and edge.BoundBox.ZLength >= 1e-6:
                    radial_sources.setdefault(radius, []).append((edge, None))
                    for vertex in vertices:
                        point = vertex.Point
                        radial_sources.setdefault(
                            math.hypot(point.x, point.y), []).append((edge, point))
            for face in shape.Faces:
                try:
                    surface = face.Surface
                except TypeError as error:
                    if "undefined surface type" not in str(error):
                        raise
                    unsupported += 1
                    continue
                if isinstance(surface, Part.Cylinder):
                    axis, center = surface.Axis, surface.Center
                    if abs(abs(axis.z) - 1) < 1e-7 and math.hypot(center.x, center.y) < 1e-7:
                        radial.add(surface.Radius)
        return (radial, axial), (radial_sources, axial_sources), unsupported

    @staticmethod
    def _constant_radius(edge):
        """Return the edge's distance from the spindle axis if it is constant, else None."""
        vertices = edge.Vertexes
        try:
            points = edge.discretize(Number=9)
        except Part.OCCError:
            return None
        radii = [math.hypot(point.x, point.y) for point in points]
        if max(radii) - min(radii) > 1e-6:
            return None
        if vertices:
            # Key by a vertex value so it matches the vertex snap candidates exactly.
            point = vertices[0].Point
            return math.hypot(point.x, point.y)
        return radii[0]

    def _radial_sign(self, axis):
        """Return the section side for radial highlights, or 0 to keep axial highlights in 3D."""
        if axis != 0:
            return 0
        return -1 if self.bounds[1] <= 0 else 1

    @staticmethod
    def _to_section(point, sign):
        if not sign:
            return point
        # Revolve onto the section plane so off-plane seams line up with the section outline.
        return FreeCAD.Vector(sign * math.hypot(point.x, point.y), 0, point.z)

    def _snap_edge_points(self, edge, sign=0):
        key = (id(edge), sign)
        if key not in self.snap_edge_points:
            try:
                points = edge.discretize(Number=65)
                if len(points) < 2:
                    raise ValueError("edge has fewer than two points")
            except (Part.OCCError, ValueError) as error:
                PathLog.warning(FreeCAD.Qt.translate(
                    "PathTurn", "Cannot highlight a snap edge: {error}").format(error=str(error)))
                points = ()
            self.snap_edge_points[key] = [self._to_section(point, sign) for point in points]
        return self.snap_edge_points[key]

    def _nearest_snap_source(self, axis, value, screen, view):
        direction = view.getCameraOrientation().multVec(FreeCAD.Vector(0, 0, 1))
        sign = self._radial_sign(axis)
        best = None
        for edge, anchor in self.snap_sources[axis].get(value, ()):
            if anchor is not None:
                anchor = self._to_section(anchor, sign)
                x, y = view.getPointOnScreen(anchor)
                distance = (x - screen[0]) ** 2 + (y - screen[1]) ** 2
                rank = (distance, edge is None, -direction.dot(anchor))
                if best is None or rank < best[0]:
                    best = (rank, edge, anchor)
                continue
            points = self._snap_edge_points(edge, sign)
            if not points:
                continue
            projected = [view.getPointOnScreen(point) for point in points]
            for index, (a, b) in enumerate(zip(projected, projected[1:])):
                dx, dy = b[0] - a[0], b[1] - a[1]
                length = dx * dx + dy * dy
                fraction = (max(0, min(1, ((screen[0] - a[0]) * dx
                                            + (screen[1] - a[1]) * dy) / length))
                            if length else 0)
                x, y = a[0] + fraction * dx, a[1] + fraction * dy
                distance = (x - screen[0]) ** 2 + (y - screen[1]) ** 2
                point = points[index] + (points[index + 1] - points[index]) * fraction
                rank = (distance, False, -direction.dot(point))
                if best is None or rank < best[0]:
                    best = (rank, edge, None)
        return None if best is None else best[1:]

    def _highlight_snap(self, axis, value, screen, view, size):
        self._clear_snap_highlight()
        source = self._nearest_snap_source(axis, value, screen, view)
        if source is None:
            return
        edge, anchor = source
        color = (0.0, 0.55, 1.0)
        if edge is not None:
            points = self._snap_edge_points(edge, self._radial_sign(axis))
            if points:
                self._boundary([(point.x, point.y, point.z) for point in points],
                               color, parent=self.snap_highlight)
        if anchor is not None:
            marker = coin.SoSeparator()
            translation = coin.SoTranslation()
            translation.translation.setValue(anchor.x, anchor.y, anchor.z)
            marker.addChild(translation)
            for tint, radius in (((1, 1, 1), size * 0.3), (color, size * 0.2)):
                material = coin.SoMaterial()
                material.diffuseColor = tint
                marker.addChild(material)
                sphere = coin.SoSphere()
                sphere.radius = radius
                marker.addChild(sphere)
            self.snap_highlight.addChild(marker)

    def _move_drag(self, data, dragger):
        if not self.dragging:
            return
        name, position, size, transform = data
        size = size[0]
        axis = 0 if name.startswith("radial") else 2
        value = position[axis] + dragger.translation.getValue().getValue()[0] * size
        x0, x1, z0, z1 = self.bounds
        gap = 1e-5
        index = self._bound_index(name)
        opposite = {"radialMin": "radialMax", "radialMax": "radialMin",
                    "axialMin": "axialMax", "axialMax": "axialMin"}[name]
        # Operation-controlled limits move together, preserving their derived spacing.
        follows = not self.enabled(opposite)
        minimum, maximum = -math.inf, math.inf
        if index == 1:
            minimum = -math.inf if follows else x0 + gap
            if x1 <= 0:
                maximum = 0
            elif follows:
                minimum = x1 - x0
        elif index == 0:
            maximum = math.inf if follows else x1 - gap
            if x1 > 0:
                minimum = 0
            elif follows:
                maximum = x0 - x1
        elif index == 3:
            minimum = -math.inf if follows else z0 + gap
        else:
            maximum = math.inf if follows else z1 - gap
        value = max(minimum, min(maximum, value))
        view = FreeCADGui.ActiveDocument.activeView()
        point = list(transform.translation.getValue().getValue())
        point[axis] += value - position[axis]
        screen = view.getPointOnScreen(FreeCAD.Vector(*point))
        candidates = self.snap_values[0 if axis == 0 else 1]
        point[axis] += max(size, 1)
        probe = view.getPointOnScreen(FreeCAD.Vector(*point))
        if math.hypot(probe[0] - screen[0], probe[1] - screen[1]) < 2:
            candidates = ()
        sign = -1 if x1 <= 0 else 1
        best = None
        for candidate in candidates:
            candidate = candidate * sign if axis == 0 else candidate
            if not minimum <= candidate <= maximum:
                continue
            point[axis] = transform.translation.getValue().getValue()[axis] + candidate - position[axis]
            target = view.getPointOnScreen(FreeCAD.Vector(*point))
            distance = math.hypot(target[0] - screen[0], target[1] - screen[1])
            rank = (distance, abs(candidate - value), candidate)
            if distance <= 10 and (best is None or rank < best):
                best = rank
        if best is not None:
            value = best[2]
        values = list(self.bounds)
        if follows:
            values[self._bound_index(opposite)] += value - values[index]
        values[index] = value
        self.drag_value = value
        self._draw(values, name, best is not None)
        if best is None:
            self._clear_snap_highlight()
        else:
            index = 0 if axis == 0 else 1
            self._highlight_snap(index, abs(value) if axis == 0 else value, screen, view, size)
        label = (FreeCAD.Qt.translate("PathTurn", "Snap") if best is not None
                 else FreeCAD.Qt.translate("PathTurn", "Limit"))
        FreeCADGui.getMainWindow().statusBar().showMessage(f"{label}: {value:.3f} mm")

    def _finish_drag(self, data, dragger):
        name = data[0]
        value = self.drag_value
        self.dragging = False
        self._clear_snap_highlight()
        self.snap_edge_points.clear()
        self.snap_sources = ({}, {})
        FreeCADGui.getMainWindow().statusBar().clearMessage()
        # Radial limits are radii, so drop the rear-post sign.
        self.set_limit(name, abs(value) if value is not None and name.startswith("radial") else value)

    def _bound_index(self, name):
        """Return the index in (XMin, XMax, ZMin, ZMax) that a named limit moves."""
        rear = self.bounds[1] <= 0
        return {"radialMin": 1 if rear else 0, "radialMax": 0 if rear else 1,
                "axialMin": 2, "axialMax": 3}[name]

    def _boundary(self, points, color, dashed=False, dotted=False, parent=None, halo=True):
        group = coin.SoSeparator()
        coordinates = coin.SoCoordinate3()
        coordinates.point.setValues(points)
        line = coin.SoLineSet()
        line.numVertices.setValues([len(points)])
        halo_enabled = halo
        halo = coin.SoSeparator()
        white = coin.SoMaterial()
        white.diffuseColor = (1, 1, 1)
        halo.addChild(white)
        halo_style = coin.SoDrawStyle()
        halo_style.lineWidth = 6 if dashed else 7
        if dashed or dotted:
            halo_style.linePattern = 0xF0F0 if dashed else 0x1111
        halo.addChild(halo_style)
        halo.addChild(coordinates)
        halo.addChild(line)
        if halo_enabled:
            group.addChild(halo)
        material = coin.SoMaterial()
        material.diffuseColor = color
        group.addChild(material)
        style = coin.SoDrawStyle()
        style.lineWidth = 2 if dashed else 3
        if dashed or dotted:
            style.linePattern = 0xF0F0 if dashed else 0x1111
        group.addChild(style)
        group.addChild(coordinates)
        group.addChild(line)
        (self.graphics if parent is None else parent).addChild(group)
