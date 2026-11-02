from PySide import QtGui, QtCore

import FreeCAD, FreeCADGui
import Part
import Path.Main.Job as PathJob
import Path.Tool.Controller as PathToolController
import PathScripts.PathUtils as PathUtils

import PathTurnScripts.PathTurnAddonHelpers as PathTurnHelpers
import PathTurnScripts.PathTurnToolBit as PathTurnToolBit
from ToolLibrary import freecad as library_assets
from ToolLibrary.iso_gui import IsoToolPanel


translate = FreeCAD.Qt.translate


class TurnToolHelperPanel(IsoToolPanel):
    def __init__(self):
        """Initialize the ISO lookup and creation controls for the active document."""

        self.document = FreeCAD.ActiveDocument
        super().__init__(self.getForm())
        self.job_cb = self.form.job_cb
        self.status_label = self.form.status_label
        self.add_button = self.form.buttonBox.addButton(
            translate("CAM", "Add to job"), QtGui.QDialogButtonBox.ActionRole)
        self.add_button.clicked.connect(self.add_tool)
        self.selection_changed.connect(self.update_add_state)
        self.job_cb.currentIndexChanged.connect(self.update_add_state)

        self.load_jobs()
        self.update_add_state()
		
    def getForm(self):
        """getForm() ... return UI"""
        # return FreeCADGui.PySideUic.loadUi(":/panels/DlgTurnToolHelper.ui")
        turnUi = PathTurnHelpers.getResourcePath("DlgTurnToolHelper.ui")
        return FreeCADGui.PySideUic.loadUi(turnUi)

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
        problem = self.definition_problem()
        if problem:
            return problem
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
        return library_assets.iso_tool_definition(
            self.shape_cb.currentText(), self.size_cb.currentText(),
            self.radius_cb.currentText(), self.direction_cb.currentText())

    def validate_template(self, shape_path, parameters):
        """Reject failed template recomputes before cached solids can hide errors."""
        library_assets.validate_iso_template(shape_path, parameters)

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
        """Describe the tool library command in the CAM menu."""
        return {'Pixmap': 'CAM-TurnToolHelper',
                'MenuText': QtCore.QT_TRANSLATE_NOOP("CAM", "Turning Tool Library"),
                'ToolTip': QtCore.QT_TRANSLATE_NOOP("CAM", "Manage native turning tool library membership")}
	
    def Activated(self):
        """Open the library editor with access to the existing ISO helper."""
        from ToolLibrary.gui import LibraryDialog

        dialog = LibraryDialog(
            FreeCADGui.getMainWindow(), iso_helper=lambda: TurnToolHelperPanel().show())
        dialog.exec_()


if FreeCAD.GuiUp:
    # register the FreeCAD command
    FreeCADGui.addCommand('CAM_TurnToolHelper', CommandPathTurnToolHelper())
