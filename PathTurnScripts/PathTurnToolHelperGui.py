import json
from pathlib import Path

from PySide import QtGui, QtCore

import FreeCAD, FreeCADGui
import Part
import Path.Main.Job as PathJob
import Path.Tool.Controller as PathToolController
import PathScripts.PathUtils as PathUtils

import PathTurnScripts.PathTurnAddonHelpers as PathTurnHelpers
import PathTurnScripts.PathTurnToolBit as PathTurnToolBit


translate = FreeCAD.Qt.translate


class TurnToolHelperPanel():
    def __init__(self):
        """Initialize the ISO lookup and creation controls for the active document."""

        self.document = FreeCAD.ActiveDocument
        self.form = self.getForm()

        self.tip_angle = {
            "A": 85,  # Parallelogram (85 degree)
            "B": 82,  # Parallelogram (82 degree)
            "C": 80,    # Rhombic (80 degree)
            "D": 55,    # Rhombic (55 degree)
            "E": 75,  # Rhombic (75 degree)
            "F": 50,  # Rhombic (50 degree)
            "H": 120,  # Hexagonal
            "K": 55,  # Parallelogram (55 degree)
            "L": 90, 	# Rectangular
            "M": 86, 	# Rhombic (86 degree)
            "O": 135, 	# Octagonal
            "P": 108, 	# Pentagonal
            "R": 90, 	# Round
            "S": 90, 	# Square
            "T": 60, 	# Triangular
            "V": 35,    # Rhombic (35 degree)
            "W": 60, 	# Trigon
            "X": None   # Special Shape
        }

        self.shape_size = {
            "C": {"03": 3.97, "04": 4.76, "05": 5.56, "06": 6.35, "08": 7.94, \
            "09": 9.525, "12": 12.7, "16": 15.875, "19": 19.05, "22": 22.225, \
            "25": 25.4},
            "D": {"04": 3.97, "05": 4.76, "06": 5.56, "07": 6.35, "09": 7.94, \
            "11": 9.525, "15": 12.7, "19": 15.875, "23": 19.05},
            "R": {"06": 6.0, "08": 8.0, "09": 9.525, "10": 10, "12": 12.0, \
            "16": 16, "20": 20, "25": 25},
            "S": {"03": 3.97, "04": 4.76, "05": 5.56, "06": 6.35, "08": 7.94, \
            "09": 9.525, "12": 12.7, "16": 15.875, "19": 19.05, "22": 22.225, \
            "25": 25.4},
            "T": {"08": 4.76, "09": 5.56, "11": 6.35, "13": 7.94, "16": 9.525, \
            "22": 12.7, "27": 15.875, "33": 19.05, "38": 22.225, "44": 25.4},
            "V": {"08": 4.76, "09": 5.56, "11": 6.35, "13": 7.94, "16": 9.525, \
            "22": 12.7},
            "W": {"02": 3.97, "L3": 4.76, "03": 5.56, "04": 6.35, "05": 7.94, \
            "06": 9.525, "08": 12.7, "10": 15.875, "13": 19.05},
            "X" : {}
        }

        self.nose_radius = {
            "00": 0,  # sharp
            "V3": 0.03,
            "V5": 0.05,
            "01": 0.1,
            "02": 0.2,
            "04": 0.4,
            "08": 0.8,
            "12": 1.2,
            "16": 1.6,
            "20": 2.0,
            "24": 2.4,
            "28": 2.8,
            "32": 3.2
        }

        #Load UI Components
        self.shape_cb = self.form.shape_cb
        self.size_cb = self.form.size_cb
        self.radius_cb = self.form.radius_cb
        self.direction_cb = self.form.direction_cb

        # self.shape_val = self.form.shape_val
        self.size_val = self.form.size_val
        # self.rotation_val = self.form.rotation_val
        self.tipangle_val = self.form.tipangle_val
        self.radius_val = self.form.radius_val
        # self.direction_val = self.form.direction_val
        self.result_val = self.form.result_val
        self.job_cb = self.form.job_cb
        self.status_label = self.form.status_label
        self.add_button = self.form.buttonBox.addButton(
            translate("CAM", "Add to job"), QtGui.QDialogButtonBox.ActionRole)
        self.add_button.clicked.connect(self.add_tool)
        self.radius_cb.setCurrentText("04")
        self.direction_cb.setCurrentText("R")

        #connect
        self.shape_cb.currentIndexChanged.connect(self.load_shape_size)

        self.shape_cb.currentIndexChanged.connect(self.load_tool_data)
        self.size_cb.currentIndexChanged.connect(self.load_tool_data)
        self.radius_cb.currentIndexChanged.connect(self.load_tool_data)
        self.direction_cb.currentIndexChanged.connect(self.load_tool_data)
        self.job_cb.currentIndexChanged.connect(self.update_add_state)

        self.load_jobs()
        self.load_shape_size(0)
		
    def getForm(self):
        """getForm() ... return UI"""
        # return FreeCADGui.PySideUic.loadUi(":/panels/DlgTurnToolHelper.ui")
        turnUi = PathTurnHelpers.getResourcePath("DlgTurnToolHelper.ui")
        return FreeCADGui.PySideUic.loadUi(turnUi)

    def load_tool_data(self):
        """ 
        Load all tool data and create a tool string
        """
        if self.size_cb.currentText():
            _shape = self.shape_cb.currentText()
            _size = self.size_cb.currentText()
            _radius = self.radius_cb.currentText()
            _direction = self.direction_cb.currentText()
            _size_val = self.get_edge_length(_shape, _size)
            _radius_val = self.get_radius_value(_radius)
            _tip_angle = self.get_tip_angle(_shape)

            # print('tool data', _shape, _size, _radius, _direction)
            # self.shape_val.setText(_shape)
            self.size_val.setText(str(_size_val))
            self.tipangle_val.setText(str(_tip_angle))

            if _shape == "X":
                _radius = "-"
                _direction = "-"
                self.radius_val.setText("-")
                # self.direction_val.setText("-")
            else:
                self.radius_val.setText(str(_radius_val))
                # self.direction_val.setText(_direction)

            tool_string = "{shape}---{size}--{radius}--{direction}".format(shape = _shape, size = _size, \
                                                                radius = _radius, direction = _direction)
            self.result_val.setText(tool_string)
        self.update_add_state()

    def load_jobs(self):
        """List jobs, preferring the selected job or its selected child object."""
        self.job_cb.addItem(translate("CAM", "Select a CAM job"), None)
        jobs = PathJob.Instances()
        selected_jobs = {
            job.Name
            for obj in FreeCADGui.Selection.getSelection()
            if obj.Document == self.document
            for job in [PathUtils.findParentJob(obj)]
            if job in jobs
        }
        for job in jobs:
            self.job_cb.addItem("{} ({})".format(job.Label, job.Name), job.Name)
        if len(selected_jobs) == 1:
            self.job_cb.setCurrentIndex(self.job_cb.findData(selected_jobs.pop()))
        elif len(jobs) == 1:
            self.job_cb.setCurrentIndex(1)

    def get_job(self):
        """Return the chosen job only while its original document remains active."""
        if self.document is None or FreeCAD.ActiveDocument != self.document:
            return None
        name = self.job_cb.currentData()
        job = self.document.getObject(name) if name else None
        if job is not None and hasattr(job, "Proxy") and isinstance(job.Proxy, PathJob.ObjectJob):
            return job
        return None

    def creation_problem(self):
        """Explain why the current selection cannot create a turning tool."""
        if self.shape_cb.currentText() not in ("C", "D", "S", "T"):
            return translate("CAM", "Tool creation supports C, D, S and T shapes. Other shapes are reference-only.")
        if not self.size_cb.currentText():
            return translate("CAM", "Choose an insert size.")
        if self.get_radius_value(self.radius_cb.currentText()) <= 0:
            return translate("CAM", "Sharp noses (00) are reference-only. Choose a non-zero nose radius.")
        if self.get_job() is None:
            return translate("CAM", "Choose a CAM job in the active document.")
        if self.document.HasPendingTransaction:
            return translate("CAM", "Finish the current document edit before adding a turning tool.")
        return None

    def update_add_state(self):
        """Enable creation only for a supported selection and an available job."""
        problem = self.creation_problem()
        self.add_button.setEnabled(problem is None)
        self.status_label.setText(problem or translate(
            "CAM", "Add the insert and a new tool controller to the selected job."))

    def get_tool_attributes(self):
        """Apply the selected ISO dimensions and handedness to a bundled tool."""
        shape = self.shape_cb.currentText()
        tools = Path(__file__).resolve().parent.parent / "Tools"
        with (tools / "Bit" / "iso_shape_{}.fctb".format(shape.lower())).open() as source:
            attributes = json.load(source)
        parameters = attributes["parameter"]
        parameters["EdgeLength"] = "{} mm".format(
            self.get_edge_length(shape, self.size_cb.currentText()))
        parameters["TipAngle"] = "{} deg".format(self.get_tip_angle(shape))
        parameters["TipRadius"] = "{} mm".format(
            self.get_radius_value(self.radius_cb.currentText()))
        rotation = FreeCAD.Units.Quantity(parameters["Rotation"]).Value
        direction = self.direction_cb.currentText()
        if direction == "L":
            rotation = -rotation
        elif direction == "N":
            rotation = 0
        parameters["Rotation"] = "{} deg".format(rotation)
        attributes["name"] = self.result_val.text()
        return attributes, tools / "Shape" / attributes["shape"]

    def validate_template(self, shape_path, parameters):
        """Reject failed template recomputes before cached solids can hide errors."""
        if FreeCAD.Units.Quantity(parameters["TipRadius"]).Value <= 0:
            raise ValueError(translate("CAM", "Tool creation requires a non-zero nose radius."))
        template = FreeCAD.newDocument("TurningToolTemplate", hidden=True)
        try:
            template.load(str(shape_path))
            bags = template.getObjectsByLabel("Attributes")
            if len(bags) != 1:
                raise ValueError(translate("CAM", "The insert template must have one Attributes object."))
            for name, value in parameters.items():
                setattr(bags[0], name, FreeCAD.Units.Quantity(value))
            template.recompute()
            errors = [
                obj.getStatusString() for obj in template.Objects
                if "Invalid" in obj.State
            ]
            if errors:
                raise ValueError(translate(
                    "CAM", "The selected insert dimensions cannot form a valid tool: ") + "; ".join(errors))
            shape = template.Body.Shape
            if shape.isNull() or not shape.isValid() or len(shape.Solids) != 1:
                raise ValueError(translate("CAM", "The selected insert dimensions cannot form a valid solid."))
            PathTurnHelpers.getToolSegments(shape)
        finally:
            FreeCAD.closeDocument(template.Name)
            FreeCAD.setActiveDocument(self.document.Name)

    def create_tool_controller(self, job):
        """Create and attach a ToolBit and numbered controller in one undo step."""
        if job.Document != FreeCAD.ActiveDocument:
            raise ValueError(translate("CAM", "The target job must be in the active document."))
        if job.Document.HasPendingTransaction:
            raise ValueError(translate("CAM", "Finish the current document edit before adding a turning tool."))
        attributes, shape_path = self.get_tool_attributes()
        self.validate_template(shape_path, attributes["parameter"])
        number = job.Proxy.nextToolNumber()
        if number > 10000:
            raise ValueError(translate("CAM", "The job has reached the maximum tool number (10000)."))
        document = job.Document
        # Native ToolBit body loading can commit transactions in the destination.
        staging = FreeCAD.newDocument("TurningToolStaging", hidden=True)
        staging.UndoMode = 0
        try:
            staged_tool = PathTurnToolBit.create_tool(shape_path, attributes, staging)
            staging.recompute()
            if staged_tool.Shape.isNull() or not staged_tool.Shape.isValid() or len(staged_tool.Shape.Solids) != 1:
                raise ValueError(translate("CAM", "FreeCAD could not create a valid insert ToolBit."))
            PathTurnHelpers.getToolSegments(staged_tool.Shape)
            FreeCAD.setActiveDocument(document.Name)
            document.openTransaction(translate("CAM", "Add turning tool"))
            committed = False
            try:
                tool = document.copyObject(staged_tool, True)
                if tool.ViewObject:
                    tool.ViewObject.Visibility = False
                controller = PathToolController.Create(
                    name="TC: " + tool.Label, tool=tool, toolNumber=number)
                job.Proxy.addToolController(controller)
                document.recompute()
                document.commitTransaction()
                committed = True
            finally:
                if not committed:
                    document.abortTransaction()
        finally:
            FreeCAD.closeDocument(staging.Name)
            FreeCAD.setActiveDocument(document.Name)
        return controller

    def add_tool(self):
        """Add the selected tool, reporting failures without leaving partial objects."""
        try:
            problem = self.creation_problem()
            if problem:
                raise ValueError(problem)
            job = self.get_job()
            controller = self.create_tool_controller(job)
        except (OSError, ValueError, RuntimeError, Part.OCCError) as error:
            message = str(error)
            FreeCAD.Console.PrintError("Turning tool helper: {}\n".format(message))
            self.status_label.setText(message)
            QtGui.QMessageBox.warning(
                self.form, translate("CAM", "Cannot add turning tool"), message)
            return
        FreeCADGui.Selection.clearSelection()
        FreeCADGui.Selection.addSelection(controller)
        self.status_label.setText(translate(
            "CAM", "Added tool {number} to {job}. Set feeds and spindle speed in its controller before use.").format(
                number=controller.ToolNumber, job=job.Label))

    def get_edge_length(self, _shape, _length ):
        """
        Return the edge length for the tool
        """

        try:
            edgeLength = self.shape_size[_shape][_length]
            return edgeLength
        except(KeyError):
            return "-"

    def get_radius_value(self, radius):
        """
        Return the nose radius for the tool
        """

        try:
            _radius = self.nose_radius[radius]
            return _radius
        except(KeyError):
            return "-"

    def get_tip_angle(self, shape):
        """
        Return the tip angle for the tool
        """

        try:
            _tip_angle = self.tip_angle[shape]
            return _tip_angle
        except(KeyError):
            return "-"

    def load_shape_size(self, index):
        """
        Load the sizes for the selected tool shape
        """
        shape = self.shape_cb.itemText(index)
        shape_size = self.shape_size[shape]
        self.size_cb.clear()

        if shape == "X":
            self.size_cb.addItem("-")
        else:
            for key in shape_size: 
                self.size_cb.addItem(key)

    def setup_ui(self):
        pass

    def show(self):
        self.form.show()
        self.form.exec_()

    def reject(self):
        FreeCAD.Console.PrintMessage("Reject Signal")
        self.quit()

    def accept(self):
        self.quit()
        
    def quit(self):
        FreeCADGui.Control.closeDialog(self)

    def reset(self):
        pass
		
		
class CommandPathTurnToolHelper:
		
    def GetResources(self):
        """Describe the tool helper command in the CAM menu."""
        return {'Pixmap': 'CAM-TurnToolHelper',
                'MenuText': QtCore.QT_TRANSLATE_NOOP("CAM", "Turn Tool Helper"),
                'ToolTip': QtCore.QT_TRANSLATE_NOOP("CAM", "Derive ISO insert parameters and add turning tools to a CAM job")}
	
    def Activated(self):
        """Open the modal ISO lookup and tool creation dialog."""
        panel = TurnToolHelperPanel()
        panel.show()


if FreeCAD.GuiUp:
    # register the FreeCAD command
    FreeCADGui.addCommand('CAM_TurnToolHelper', CommandPathTurnToolHelper())
