"""Native file-defined turning ToolBit types and creation."""

from base64 import b64decode, b64encode
import math
from pathlib import Path
from tempfile import TemporaryDirectory

import FreeCAD
import Path.Tool.Bit as PathToolBit


TOOL_POSTS = ("Front", "Rear")


def is_drill_tool(tool):
    return (str(getattr(tool, "ShapeType", "")).lower() == "drill"
            or getattr(tool, "ToolKind", None) == "Drill")


def post_from_parameters(parameters):
    """Read and validate the physical tool post."""
    post = parameters.get("ToolPost")
    if post not in TOOL_POSTS:
        raise ValueError("Tool post must be Front or Rear.")
    return post


def validate_native_parameters(bag):
    """Apply optional parameter checks authored in the native ToolShape."""
    for name in bag.PropertiesList:
        if bag.getGroupOfProperty(name) != "Validation":
            continue
        if bag.getTypeIdOfProperty(name) != "App::PropertyBool":
            raise ValueError("Native Validation properties must be Boolean checks.")
        if not bag.getPropertyByName(name):
            raise ValueError(bag.getDocumentationOfProperty(name) or f"Tool parameter check failed: {name}.")


if not hasattr(PathToolBit, "Factory"):
    class ToolBitShapeTurningCustom(PathToolBit.ToolBitShape):
        """Use the schema and enum choices supplied by each native file."""

        name = "TurningCustom"
        aliases = ("turningcustom",)

        @classmethod
        def schema(cls):
            return {}

        def set_parameter(self, name, value):
            fields = getattr(self, "fields", {})
            if name not in fields:
                raise ValueError(f"The native shape does not define {name}.")
            field = fields[name]
            kind = field["type"]
            if kind == "App::PropertyEnumeration":
                if value not in field["choices"]:
                    raise ValueError(f"Unsupported choice for {name}.")
            elif kind == "App::PropertyBool":
                if type(value) is not bool:
                    raise ValueError(f"{name} must be a boolean.")
            elif kind == "App::PropertyString":
                if not isinstance(value, str):
                    raise ValueError(f"{name} must be text.")
            else:
                if isinstance(value, bool):
                    raise ValueError(f"{name} must be a number.")
                quantity = FreeCAD.Units.Quantity(value)
                default = FreeCAD.Units.Quantity(self._defaults[name])
                if quantity.Unit not in (default.Unit, FreeCAD.Units.Quantity(1).Unit):
                    raise ValueError(f"Unexpected units for {name}.")
                if not math.isfinite(quantity.Value):
                    raise ValueError(f"{name} must be finite.")
                if name == "Diameter" and quantity.Value <= 0:
                    raise ValueError("CAM Diameter must be positive.")
                if kind == "App::PropertyInteger":
                    if quantity.Value != int(quantity.Value):
                        raise ValueError(f"{name} must be an integer.")
                    value = int(quantity.Value)
                elif kind == "App::PropertyFloat":
                    value = quantity.Value
                else:
                    value = quantity if quantity.Unit == default.Unit else FreeCAD.Units.Quantity(
                        quantity.Value, default.Unit)
            self._params[name] = value

        def get_parameter(self, name):
            return self._params[name]

        def get_parameters(self):
            return dict(self._params)

        @property
        def label(self):
            return FreeCAD.Qt.translate("CAM", "Custom turning tool")

    class ToolBitTurningCustom(PathToolBit.ToolBit):
        """Preserve file-defined custom parameters and embedded native geometry."""

        SHAPE_CLASS = ToolBitShapeTurningCustom

        def _update_visual_representation(self):
            shape = self._tool_bit_shape
            readonly = [name for name, field in getattr(shape, "fields", {}).items() if field["readonly"]]
            if (readonly or getattr(shape, "_has_validation", False)) and isinstance(self.obj, FreeCAD.DocumentObject):
                active = FreeCAD.ActiveDocument
                document = FreeCAD.newDocument("TurningCustomCalculated", hidden=True)
                updating = getattr(self, "_in_update", False)
                self._in_update = True
                try:
                    with TemporaryDirectory() as directory:
                        path = Path(directory) / "shape.fcstd"
                        path.write_bytes(shape._data)
                        document.load(str(path))
                    bag = document.getObjectsByLabel("Attributes")[0]
                    for name, field in shape.fields.items():
                        if not field["readonly"]:
                            setattr(bag, name, shape.get_parameter(name))
                    document.recompute()
                    validate_native_parameters(bag)
                    for name in readonly:
                        value = bag.getPropertyByName(name)
                        shape._params[name] = value
                        setattr(self.obj, name, value)
                finally:
                    self._in_update = updating
                    FreeCAD.closeDocument(document.Name)
                    FreeCAD.setActiveDocument(active.Name if active else "")
            super()._update_visual_representation()

        def _update_tool_properties(self):
            updating = getattr(self, "_in_update", False)
            self._in_update = True
            try:
                fields = getattr(self._tool_bit_shape, "fields", {})
                for name, field in fields.items():
                    if not hasattr(self.obj, name):
                        self.obj.addProperty(field["type"], name, "Shape", field["description"])
                    if field["type"] == "App::PropertyEnumeration":
                        setattr(self.obj, name, list(field["choices"]))
                super()._update_tool_properties()
                for name, field in fields.items():
                    self.obj.setEditorMode(name, 2 if field["hidden"] else 1 if field["readonly"] else 0)
            finally:
                self._in_update = updating

        def __getstate__(self):
            state = super().__getstate__()
            state["_custom_template"] = b64encode(self._tool_bit_shape._data).decode("ascii")
            return state

        def onDocumentRestored(self, obj):
            shape = custom_shape_from_bytes(b64decode(self._custom_template, validate=True), obj.ShapeID)
            for name, field in shape.fields.items():
                if name in obj.PropertiesList:
                    if field["readonly"]:
                        shape._params[name] = obj.getPropertyByName(name)
                    else:
                        shape.set_parameter(name, obj.getPropertyByName(name))
            foreign_body = obj.BitBody and obj.BitBody.Document != obj.Document
            if foreign_body:
                obj.BitBody = None
            super().onDocumentRestored(obj)
            self._tool_bit_shape = shape
            self._update_tool_properties()
            if foreign_body:
                self._update_visual_representation()


def custom_shape_from_bytes(data, identity):
    """Discover custom properties from native Attributes, independent of the Body label."""
    active = FreeCAD.ActiveDocument
    document = FreeCAD.newDocument("TurningCustomSchema", hidden=True)
    try:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "shape.fcstd"
            path.write_bytes(data)
            document.load(str(path))
        bags = document.getObjectsByLabel("Attributes")
        if len(bags) != 1 or document.getObject("Body") is None:
            raise ValueError("A custom ToolShape needs a Body and one Attributes object.")
        bag = bags[0]
        validate_native_parameters(bag)
        expressions = dict(bag.ExpressionEngine)
        shape = ToolBitShapeTurningCustom(id=identity)
        shape._data = data
        shape._has_validation = any(bag.getGroupOfProperty(name) == "Validation" for name in bag.PropertiesList)
        shape.fields = {}
        shape._params = {}
        shape._defaults = {}
        shape._param_types = {}
        supported = {"App::Property" + kind for kind in (
            "Length", "Distance", "Angle", "Float", "Integer", "Bool", "String", "Enumeration")}
        for name in bag.PropertiesList:
            if bag.getGroupOfProperty(name) != "Shape":
                continue
            if name in {"name", "Label", "Label2", "Proxy", "Shape", "Placement", "BitBody",
                        "ShapeID", "ShapeType", "ToolBitID", "ExpressionEngine", "Visibility"}:
                raise ValueError(f"{name} is reserved for native ToolBit identity or geometry.")
            kind = bag.getTypeIdOfProperty(name)
            if kind not in supported:
                raise ValueError(f"Unsupported native property type for {name}: {kind}.")
            mode = bag.getEditorMode(name)
            shape.fields[name] = {
                "type": kind, "description": bag.getDocumentationOfProperty(name),
                "choices": tuple(bag.getEnumerationsOfProperty(name)) if kind == "App::PropertyEnumeration" else (),
                "readonly": "ReadOnly" in mode or name in expressions, "hidden": "Hidden" in mode,
            }
            shape._defaults[name] = bag.getPropertyByName(name)
            shape._params[name] = shape._defaults[name]
            shape._param_types[name] = kind
        if ("Diameter" not in shape.fields
                or shape.fields["Diameter"]["type"] != "App::PropertyLength"):
            raise ValueError("Attributes must define Diameter as App::PropertyLength in Shape for FreeCAD CAM.")
        diameter = float(shape._params["Diameter"])
        if not math.isfinite(diameter) or diameter <= 0:
            raise ValueError("CAM Diameter must be positive and finite.")
        if shape._params.get("ToolKind") == "Drill":
            required = {"Diameter": "App::PropertyLength", "Length": "App::PropertyLength",
                        "TipAngle": "App::PropertyAngle"}
            if any(name not in shape.fields or shape.fields[name]["type"] != kind
                   for name, kind in required.items()):
                raise ValueError("A drill must define Diameter, Length and TipAngle with length/angle units.")
            if not shape.fields["ToolKind"]["readonly"]:
                raise ValueError("The drill ToolKind must be read-only.")
        elif "ToolPost" not in shape.fields or set(shape.fields["ToolPost"]["choices"]) != set(TOOL_POSTS):
            raise ValueError("Attributes must define a ToolPost (Front/Rear) enumeration in Shape.")
        if "Compensation" in shape.fields and not shape.fields["Compensation"]["choices"]:
            raise ValueError("An optional Compensation property must be an enumeration with choices.")
        return shape
    finally:
        FreeCAD.closeDocument(document.Name)
        FreeCAD.setActiveDocument(active.Name if active else "")


def create_tool(shape_path, attributes, document):
    """Create a native ToolBit in the supplied active staging document."""
    if FreeCAD.ActiveDocument != document:
        raise ValueError("The ToolBit staging document must be active.")
    if attributes.get("shape-type") == "TurningCustom":
        if hasattr(PathToolBit, "Factory"):
            raise ValueError("Custom turning tools require the native FreeCAD asset ToolBit API.")
        shape = custom_shape_from_bytes(Path(shape_path).read_bytes(), Path(shape_path).stem)
        for name, value in attributes["parameter"].items():
            if name in shape.fields and not shape.fields[name]["readonly"]:
                shape.set_parameter(name, value)
        bit = PathToolBit.ToolBit.from_shape(
            shape, dict(attributes, parameter=shape.get_parameters(), attribute={}), id=None)
        return bit.attach_to_doc(document)
    raise ValueError("Only file-defined TurningCustom tools are supported.")
