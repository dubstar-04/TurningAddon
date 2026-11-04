"""Native ISO ToolBit types and creation across supported FreeCAD tool APIs."""

from base64 import b64decode, b64encode

import FreeCAD
import Path.Tool.Bit as PathToolBit


TOOL_REFERENCES = ("Tip Tangent", "Tip", "Tip centre", "Insert centre")


def reference_from_parameters(parameters):
    """Read and validate the native compensation selection."""
    reference = parameters.get("Compensation")
    if reference not in TOOL_REFERENCES:
        raise ValueError("Compensation must select a supported turning tool reference.")
    return reference


if not hasattr(PathToolBit, "Factory"):
    ToolBitShapeIso = PathToolBit.ToolBitShape.get_subclass_by_name("IsoShape")
    if ToolBitShapeIso is None:
        class ToolBitShapeIso(PathToolBit.ToolBitShape):
            """Describe the parameters exposed by the bundled ISO insert shapes."""

            name = "IsoShape"
            aliases = ("isoshape",)

            @classmethod
            def schema(cls):
                """Return the ISO dimensions without unrelated milling parameters."""
                return {
                    "EdgeLength": (
                        FreeCAD.Qt.translate("CAM", "Cutting edge length"),
                        "App::PropertyLength"),
                    "Rotation": (
                        FreeCAD.Qt.translate("CAM", "Rotation angle"),
                        "App::PropertyAngle"),
                    "TipAngle": (
                        FreeCAD.Qt.translate("CAM", "Tip angle"),
                        "App::PropertyAngle"),
                    "TipRadius": (
                        FreeCAD.Qt.translate("CAM", "Tip radius"),
                        "App::PropertyLength"),
                    "Compensation": (
                        FreeCAD.Qt.translate("CAM", "Tool coordinate origin"),
                        "App::PropertyEnumeration"),
                    "ToolSide": (
                        FreeCAD.Qt.translate("CAM", "Spindle side: Near (+X) or Far (-X)"),
                        "App::PropertyString"),
                }

            @classmethod
            def get_expected_shape_parameters(cls):
                return [name for name in super().get_expected_shape_parameters()
                        if name != "ToolSide"]

            def get_parameter(self, name):
                if name == "ToolSide":
                    return self._params.get(name, "Near")
                if name == "Compensation":
                    return reference_from_parameters(self._params)
                return super().get_parameter(name)

            def set_parameter(self, name, value):
                if name == "ToolSide" and value not in ("Near", "Far"):
                    raise ValueError("Tool side must be Near or Far")
                if name == "Compensation":
                    reference_from_parameters({name: value})
                super().set_parameter(name, value)

            @property
            def label(self):
                """Return the insert type's translated display name."""
                return FreeCAD.Qt.translate("CAM", "ISO insert")

    class ToolBitIso(PathToolBit.ToolBit):
        """Persist ISO tools on FreeCAD releases without a built-in ISO ToolBit."""

        SHAPE_CLASS = ToolBitShapeIso

        def _update_tool_properties(self):
            updating = getattr(self, "_in_update", False)
            self._in_update = True
            try:
                if not hasattr(self.obj, "ToolSide"):
                    self.obj.addProperty(
                        "App::PropertyString", "ToolSide", "Attributes",
                        FreeCAD.Qt.translate("CAM", "Spindle side: Near (+X) or Far (-X)"))
                if not hasattr(self.obj, "Compensation"):
                    self.obj.addProperty(
                        "App::PropertyEnumeration", "Compensation", "Shape",
                        FreeCAD.Qt.translate("CAM", "Tool coordinate origin"))
                self.obj.Compensation = list(TOOL_REFERENCES)
                super()._update_tool_properties()
            finally:
                self._in_update = updating

        def __getstate__(self):
            state = super().__getstate__()
            data = self._tool_bit_shape._data
            if data is not None:
                state["_iso_template"] = b64encode(data).decode("ascii")
            return state

        def onDocumentRestored(self, obj):
            from Path.Tool.assets import AssetUri, DummyAssetSerializer
            from Path.Tool.camassets import cam_assets

            shape_id = obj.ShapeID
            encoded = getattr(self, "_iso_template", None)
            data = (b64decode(encoded, validate=True) if encoded is not None else
                    cam_assets.get_raw(
                        AssetUri.build(asset_type="toolbitshape", asset_id=shape_id),
                        store=("local", "builtin")))
            shape = PathToolBit.ToolBitShape.from_bytes(
                data, shape_id, dependencies=None, serializer=DummyAssetSerializer)
            parameters = {
                name: obj.getPropertyByName(name)
                for name in set(self.SHAPE_CLASS.schema()) | set(shape.get_parameters())
                if name in obj.PropertiesList
            }
            reference_from_parameters(parameters)
            for name, value in parameters.items():
                shape.set_parameter(name, value)
            foreign_body = obj.BitBody and obj.BitBody.Document != obj.Document
            if foreign_body:
                obj.BitBody = None
            super().onDocumentRestored(obj)
            self._tool_bit_shape = shape
            self._update_tool_properties()
            if foreign_body:
                self._update_visual_representation()


def create_tool(shape_path, attributes, document):
    """Create a native ToolBit in the supplied active staging document."""
    if FreeCAD.ActiveDocument != document:
        raise ValueError("The ToolBit staging document must be active.")
    reference_from_parameters(attributes["parameter"])
    if hasattr(PathToolBit, "Factory"):
        attributes = dict(attributes, shape=str(shape_path))
        return PathToolBit.Factory.CreateFromAttrs(attributes)
    shape = PathToolBit.ToolBitShape.from_file(
        shape_path, **attributes["parameter"])
    bit = PathToolBit.ToolBit.from_shape(shape, attributes, id=None)
    return bit.attach_to_doc(document)
