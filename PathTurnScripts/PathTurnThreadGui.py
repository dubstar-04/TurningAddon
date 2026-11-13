"""FreeCAD task panel and command for external threading."""

from pathlib import Path

import FreeCAD
import FreeCADGui
import Path.Base.Gui.Util as PathGuiUtil
import Path.Op.Gui.Base as PathOpGui
from PySide import QtCore

from . import PathTurnBaseGui
from . import PathTurnThread


_icon = Path(__file__).parent.parent / "Gui/Resources/Icons/CAM-TurnThread.svg"


class TaskPanelOpPage(PathTurnBaseGui.TaskPanelTurnBase):
    def getIcon(self, obj):
        return str(_icon)

    def getForm(self):
        form = super().getForm()
        form.threadStandard.currentIndexChanged.connect(self._standard_changed)
        form.threadSize.currentIndexChanged.connect(self._size_changed)
        form.threadPitch.currentIndexChanged.connect(self._pitch_changed)
        form.threadClass.currentIndexChanged.connect(self._update_thread_visibility)
        return form

    def _fill_combo(self, combo, choices, selected=None):
        blocked = combo.blockSignals(True)
        combo.clear()
        for label, value in choices:
            combo.addItem(label, value)
        index = combo.findData(selected)
        combo.setCurrentIndex(index if index >= 0 else (0 if choices else -1))
        combo.blockSignals(blocked)

    def _populate_sizes(self, selected=None):
        standard = self.form.threadStandard.currentData()
        choices = ([(size, size) for size in PathTurnThread.ThreadData.sizes(standard)]
                   if standard != "Custom" else [])
        self._fill_combo(self.form.threadSize, choices, selected)

    def _populate_pitches(self, selected=None):
        standard = self.form.threadStandard.currentData()
        size = self.form.threadSize.currentData()
        choices = []
        if standard != "Custom" and size:
            for name, record in PathTurnThread.ThreadData.pitches(standard, size).items():
                label = (f'{record["tpi"]:g} TPI' if "tpi" in record
                         else self._format_length(record["pitch_mm"]))
                choices.append((label, name))
        self._fill_combo(self.form.threadPitch, choices, selected)

    def _populate_classes(self, selected=None):
        standard = self.form.threadStandard.currentData()
        name = self.form.threadPitch.currentData()
        choices = ([(PathTurnThread.ThreadData.fit_name(standard, value), value)
                    for value in PathTurnThread.ThreadData.fits(standard, name)]
                   if standard != "Custom" and name else [])
        values = [value for _, value in choices]
        if selected not in values and standard != "Custom":
            selected = PathTurnThread.ThreadData.default_fit(standard)
        self._fill_combo(self.form.threadClass, choices, selected)

    def _standard_changed(self, *args):
        previous_class = self.form.threadClass.currentData()
        previous_size = self.form.threadSize.currentData()
        previous_pitch = self.form.threadPitch.currentData()
        self._populate_sizes(previous_size)
        self._populate_pitches(previous_pitch)
        self._populate_classes(previous_class)
        self._update_thread_visibility()

    def _size_changed(self, *args):
        previous_class = self.form.threadClass.currentData()
        self._populate_pitches(self.form.threadPitch.currentData())
        self._populate_classes(previous_class)
        self._update_thread_visibility()

    def _pitch_changed(self, *args):
        self._populate_classes(self.form.threadClass.currentData())
        self._update_thread_visibility()

    @staticmethod
    def _format_length(value):
        return FreeCAD.Units.Quantity(value, FreeCAD.Units.Length).UserString

    def _update_thread_visibility(self, *args):
        is_preset = self.form.threadStandard.currentData() != "Custom"
        for name in ("threadSizeLabel", "threadSize", "threadPitchLabel", "threadPitch",
                     "threadClassLabel", "threadClass"):
            getattr(self.form, name).setVisible(is_preset)
        self.form.pitchLabel.setVisible(not is_preset)
        self.form.pitch.setVisible(not is_preset)
        self.form.pitch.setEnabled(not is_preset)
        if not is_preset:
            return

        standard = self.form.threadStandard.currentData()
        thread_class = self.form.threadClass.currentData()
        name = self.form.threadPitch.currentData()
        if thread_class and name:
            targets = PathTurnThread.ThreadData.midpoint_targets(standard, thread_class, name)
            self.form.pitch.setText(self._format_length(targets["pitch_mm"]))

    def getFields(self, obj):
        super().getFields(obj)
        standard = self.form.threadStandard.currentData()
        if standard == "Custom":
            obj.Proxy.setThreadPreset(obj, standard)
            PathGuiUtil.updateInputField(obj, "Pitch", self.form.pitch)
        else:
            thread_class = self.form.threadClass.currentData()
            name = self.form.threadPitch.currentData()
            try:
                obj.Proxy.setThreadPreset(obj, standard, thread_class, name)
            except ValueError as error:
                self.show_error_message(
                    FreeCAD.Qt.translate("PathTurn", "Cannot apply standard thread data"),
                    str(error))
                self.setOpFields(obj)
                return
        obj.SpringPasses = self.form.springPasses.value()

    def setOpFields(self, obj):
        standard = str(getattr(obj, "ThreadStandard", "Custom"))
        thread_class = str(getattr(obj, "ThreadClass", ""))
        thread_size = str(getattr(obj, "ThreadSize", ""))
        removed_selection = False
        if standard != "Custom":
            try:
                if thread_class not in PathTurnThread.ThreadData.fits(standard, thread_size):
                    raise ValueError(thread_class)
            except ValueError:
                removed_selection = True
                standard = "Custom"

        self.form.threadStandardLabel.show()
        self.form.threadStandard.show()
        choices = [("Custom", "Custom")]
        choices.extend((standard, standard) for standard in PathTurnThread.ThreadData.standards())
        self._fill_combo(
            self.form.threadStandard, choices, standard)
        selected_size = (PathTurnThread.ThreadData.size_of(standard, thread_size)
                         if standard != "Custom" else None)
        self._populate_sizes(selected_size)
        self._populate_pitches(thread_size)
        self._populate_classes(thread_class)
        self._update_thread_visibility()
        if removed_selection:
            FreeCAD.Console.PrintWarning(FreeCAD.Qt.translate(
                "PathTurn", "{label}: the saved thread size is no longer in the standard list. "
                "Its saved pitch and diameter values are retained in Custom mode.\n").format(
                    label=obj.Label))

        self.form.threadClass.setToolTip(FreeCAD.Qt.translate(
            "PathTurn", "Loose (8g / 1A): easier assembly.\n"
            "Standard (6g / 2A): general purpose.\n"
            "Close (4g6g / 3A): tighter fit."))
        self.form.pitch.setText(obj.Pitch.UserString)
        self.form.pitch.setToolTip(FreeCAD.Qt.translate(
            "PathTurn", "Thread advance per spindle revolution."))
        self.form.springPassesLabel.show()
        self.form.springPasses.show()
        self.form.passOffset.setToolTip(FreeCAD.Qt.translate(
            "PathTurn", "Maximum radial depth per pass."))
        self.form.springPasses.setValue(obj.SpringPasses)
        self.form.setToolTip(FreeCAD.Qt.translate(
            "PathTurn", "External single-start thread. Requires spindle synchronization "
            "and run-in/run-out clearance."))

    def getSignalsForUpdate(self, obj):
        return (super().getSignalsForUpdate(obj)
                + [self.form.threadStandard.currentIndexChanged,
                   self.form.threadSize.currentIndexChanged,
                   self.form.threadPitch.currentIndexChanged,
                   self.form.threadClass.currentIndexChanged,
                   self.form.pitch.editingFinished, self.form.springPasses.valueChanged])


Command = PathOpGui.SetupOperation(
    "TurnThread", PathTurnThread.Create, TaskPanelOpPage, "CAM-TurnThread",
    QtCore.QT_TRANSLATE_NOOP("PathTurnThread", "Turn Thread"),
    QtCore.QT_TRANSLATE_NOOP(
        "PathTurnThread", "Create straight single-start external threads using spindle-synchronized G33"),
    PathTurnThread.SetupProperties)
