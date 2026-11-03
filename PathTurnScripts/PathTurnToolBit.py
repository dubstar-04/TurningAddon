"""Native ISO ToolBit types and creation across supported FreeCAD tool APIs."""

from base64 import b64decode, b64encode

import FreeCAD
import Path.Tool.Bit as PathToolBit


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
                    "NoseCentre": (
                        FreeCAD.Qt.translate("CAM", "Use nose centre as tool origin"),
                        "App::PropertyBool"),
                    "InsertCentre": (
                        FreeCAD.Qt.translate("CAM", "Use insert centre as tool origin"),
                        "App::PropertyBool"),
                    "TipTangent": (
                        FreeCAD.Qt.translate("CAM", "Use tip tangent as tool origin"),
                        "App::PropertyBool"),
                    "ToolSide": (
                        FreeCAD.Qt.translate("CAM", "Spindle side: Near (+X) or Far (-X)"),
                        "App::PropertyString"),
                }

            @classmethod
            def get_expected_shape_parameters(cls):
                return [name for name in super().get_expected_shape_parameters()
                        if name not in ("NoseCentre", "InsertCentre", "TipTangent", "ToolSide")]

            @property
            def supports_nose_centre(self):
                return "NoseCentre" in self._param_types

            @property
            def supports_insert_centre(self):
                return "InsertCentre" in self._param_types

            @property
            def supports_tip_tangent(self):
                return "TipTangent" in self._param_types

            def get_parameter(self, name):
                if name == "ToolSide":
                    return self._params.get(name, "Near")
                if name == "NoseCentre" and not self.supports_nose_centre:
                    return False
                if name == "InsertCentre" and not self.supports_insert_centre:
                    return False
                if name == "TipTangent" and not self.supports_tip_tangent:
                    return False
                return super().get_parameter(name)

            def set_parameter(self, name, value):
                if name == "ToolSide" and value not in ("Near", "Far"):
                    raise ValueError("Tool side must be Near or Far")
                if (name == "TipTangent" and self._data is not None
                        and not self.supports_tip_tangent):
                    if value:
                        raise ValueError("This ToolShape does not support tip-tangent geometry. Update its template before changing the reference.")
                    return
                if (name == "InsertCentre" and self._data is not None
                        and not self.supports_insert_centre):
                    if value:
                        raise ValueError("This ToolShape does not support insert-centred geometry. Update its template before changing the reference.")
                    return
                if (name == "NoseCentre" and self._data is not None
                        and not self.supports_nose_centre):
                    if value:
                        raise ValueError(FreeCAD.Qt.translate(
                            "CAM", "This ToolShape does not support nose-centred geometry. Update its template before changing the reference."))
                    return
                super().set_parameter(name, value)

            @property
            def label(self):
                """Return the insert type's translated display name."""
                return FreeCAD.Qt.translate("CAM", "ISO insert")

    class ToolBitIso(PathToolBit.ToolBit):
        """Persist ISO tools on FreeCAD releases without a built-in ISO ToolBit."""

        SHAPE_CLASS = ToolBitShapeIso

        def _update_tool_properties(self):
            if not hasattr(self.obj, "ToolSide"):
                self.obj.addProperty(
                    "App::PropertyString", "ToolSide", "Attributes",
                    FreeCAD.Qt.translate("CAM", "Spindle side: Near (+X) or Far (-X)"))
            super()._update_tool_properties()
            if not self._tool_bit_shape.supports_nose_centre:
                self.obj.setEditorMode("NoseCentre", 1)
            if not self._tool_bit_shape.supports_insert_centre:
                self.obj.setEditorMode("InsertCentre", 1)
            if not self._tool_bit_shape.supports_tip_tangent:
                self.obj.setEditorMode("TipTangent", 1)

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
    if hasattr(PathToolBit, "Factory"):
        attributes = dict(attributes, shape=str(shape_path))
        return PathToolBit.Factory.CreateFromAttrs(attributes)
    shape = PathToolBit.ToolBitShape.from_file(
        shape_path, **attributes["parameter"])
    bit = PathToolBit.ToolBit.from_shape(shape, attributes, id=None)
    return bit.attach_to_doc(document)
