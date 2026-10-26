"""DSS Link configuration dialog."""

import os

from qgis.PyQt.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)
from qgis.core import QgsProject

from .compat import is_point_layer, read_setting, write_setting
from .core import split_pathname
from .dss_reader import DssReader


class DssLinkDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("DSS Link")
        self.setMinimumWidth(620)

        root = QVBoxLayout(self)
        description = QLabel(
            "Match DSS time-series pathnames to a point station layer and create "
            "a QGIS-ready GeoPackage. Filters are optional and case-insensitive."
        )
        description.setWordWrap(True)
        root.addWidget(description)

        inputs = QGroupBox("Inputs")
        form = QFormLayout(inputs)
        self.dss_edit = QLineEdit(read_setting("dss_file"))
        form.addRow("DSS file", self._file_row(self.dss_edit, self._choose_dss))

        self.layer_combo = QComboBox()
        self.layer_combo.currentIndexChanged.connect(self._refresh_fields)
        form.addRow("Station point layer", self.layer_combo)
        self.field_combo = QComboBox()
        form.addRow("Station ID field", self.field_combo)
        root.addWidget(inputs)

        mapping = QGroupBox("DSS pathname mapping")
        mapping_form = QFormLayout(mapping)
        self.part_combo = QComboBox()
        self.part_combo.addItems(["A", "B", "C", "D", "E", "F"])
        self.part_combo.setCurrentText(read_setting("station_part", "B") or "B")
        mapping_form.addRow("Part containing station ID", self.part_combo)
        self.parameter_combo = self._filter_combo("Optional — blank means all C-parts")
        mapping_form.addRow("C-part parameter", self.parameter_combo)
        self.interval_combo = self._filter_combo("Optional — blank means all E-parts")
        mapping_form.addRow("E-part interval", self.interval_combo)
        self.version_combo = self._filter_combo("Optional — blank means all F-parts")
        mapping_form.addRow("F-part version", self.version_combo)
        self.scan_button = QPushButton("Scan DSS catalog")
        self.scan_button.clicked.connect(self._scan_catalog)
        mapping_form.addRow("", self.scan_button)
        self.start_edit = QLineEdit()
        self.start_edit.setPlaceholderText("Optional DSS date, e.g. 01JAN2000")
        mapping_form.addRow("Start date", self.start_edit)
        self.end_edit = QLineEdit()
        self.end_edit.setPlaceholderText("Optional DSS date, e.g. 31DEC2025")
        mapping_form.addRow("End date", self.end_edit)
        root.addWidget(mapping)

        output = QGroupBox("Output")
        output_form = QFormLayout(output)
        self.output_edit = QLineEdit()
        output_form.addRow("GeoPackage", self._file_row(self.output_edit, self._choose_output))
        root.addWidget(output)

        note = QLabel(
            "The comparison ignores case, spaces, hyphens and underscores. "
            "Existing output files are not overwritten."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #555;")
        root.addWidget(note)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Create linked layers")
        self.buttons.accepted.connect(self._validate)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)

        self._refresh_layers()

    @staticmethod
    def _filter_combo(placeholder):
        combo = QComboBox()
        combo.setEditable(True)
        combo.addItem("")
        combo.lineEdit().setPlaceholderText(placeholder)
        return combo

    def _file_row(self, edit, callback):
        widget = QHBoxLayout()
        widget.addWidget(edit)
        button = QPushButton("Browse…")
        button.clicked.connect(callback)
        widget.addWidget(button)
        return widget

    def _refresh_layers(self):
        self.layer_combo.clear()
        for layer in QgsProject.instance().mapLayers().values():
            if is_point_layer(layer):
                self.layer_combo.addItem(layer.name(), layer.id())
        index = self.layer_combo.findData(read_setting("station_layer"))
        if index >= 0:
            self.layer_combo.setCurrentIndex(index)
        self._refresh_fields()

    def _refresh_fields(self):
        self.field_combo.clear()
        layer = self.station_layer()
        if layer:
            self.field_combo.addItems([field.name() for field in layer.fields()])
            index = self.field_combo.findText(read_setting("station_field"))
            if index >= 0:
                self.field_combo.setCurrentIndex(index)

    def station_layer(self):
        return QgsProject.instance().mapLayer(self.layer_combo.currentData())

    def _choose_dss(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select HEC-DSS file", self.dss_edit.text(), "HEC-DSS (*.dss);;All files (*)"
        )
        if path:
            self.dss_edit.setText(path)

    def _choose_output(self):
        start = os.path.join(read_setting("output_dir"), "dss_link.gpkg")
        path, _ = QFileDialog.getSaveFileName(self, "Create GeoPackage", start, "GeoPackage (*.gpkg)")
        if path:
            self.output_edit.setText(path if path.lower().endswith(".gpkg") else path + ".gpkg")

    def _scan_catalog(self):
        filename = self.dss_edit.text().strip()
        if not filename:
            QMessageBox.warning(self, "DSS Link", "Select a DSS file first.")
            return
        try:
            with DssReader(filename) as reader:
                paths = reader.catalog()
            parsed = []
            for path in paths:
                try:
                    parsed.append(split_pathname(path))
                except ValueError:
                    continue
            if not parsed:
                raise RuntimeError("The DSS catalog did not contain valid six-part pathnames.")
            for combo, index in (
                (self.parameter_combo, 2),
                (self.interval_combo, 4),
                (self.version_combo, 5),
            ):
                values = sorted({parts[index] for parts in parsed if parts[index]})
                combo.clear()
                combo.addItem("")
                combo.addItems(values)
                combo.setCurrentIndex(0)
            QMessageBox.information(
                self,
                "DSS catalog scanned",
                "Found {:,} pathnames. Choose values from the C/E/F lists, or "
                "leave a list blank to include all values.".format(len(parsed)),
            )
        except Exception as exc:
            QMessageBox.critical(self, "DSS catalog scan failed", str(exc))

    def _validate(self):
        missing = []
        if not self.dss_edit.text().strip():
            missing.append("DSS file")
        if not self.station_layer():
            missing.append("station point layer")
        if not self.field_combo.currentText():
            missing.append("station ID field")
        if not self.output_edit.text().strip():
            missing.append("output GeoPackage")
        if missing:
            QMessageBox.warning(self, "DSS Link", "Please provide: " + ", ".join(missing))
            return
        if bool(self.start_edit.text().strip()) != bool(self.end_edit.text().strip()):
            QMessageBox.warning(
                self,
                "DSS Link",
                "Provide both start and end dates, or leave both date fields blank.",
            )
            return
        write_setting("dss_file", self.dss_edit.text().strip())
        write_setting("station_layer", self.layer_combo.currentData())
        write_setting("station_field", self.field_combo.currentText())
        write_setting("station_part", self.part_combo.currentText())
        write_setting("output_dir", os.path.dirname(self.output_edit.text().strip()))
        self.accept()

    def settings(self):
        return {
            "dss_file": self.dss_edit.text().strip(),
            "station_layer": self.station_layer(),
            "station_field": self.field_combo.currentText(),
            "station_part": self.part_combo.currentIndex(),
            "parameter": self.parameter_combo.currentText().strip(),
            "interval": self.interval_combo.currentText().strip(),
            "version": self.version_combo.currentText().strip(),
            "start_date": self.start_edit.text().strip() or None,
            "end_date": self.end_edit.text().strip() or None,
            "output": self.output_edit.text().strip(),
        }
