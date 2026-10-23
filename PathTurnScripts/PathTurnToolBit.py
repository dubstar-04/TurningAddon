"""Native ISO ToolBit types and creation across supported FreeCAD tool APIs."""

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
                }

            @property
            def label(self):
                """Return the insert type's translated display name."""
                return FreeCAD.Qt.translate("CAM", "ISO insert")

    class ToolBitIso(PathToolBit.ToolBit):
        """Persist ISO tools on FreeCAD releases without a built-in ISO ToolBit."""

        SHAPE_CLASS = ToolBitShapeIso


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
