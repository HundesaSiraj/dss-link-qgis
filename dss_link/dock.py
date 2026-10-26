"""Interactive DSS explorer dock for QGIS."""

from bisect import bisect_left
import csv
from datetime import datetime
import os
from math import hypot

from qgis.PyQt.QtCore import QSize, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qgis.PyQt.QtGui import QColor, QCursor, QFont
from qgis.core import QgsProject
from qgis.gui import QgsMapToolIdentify

from .compat import is_point_layer, read_setting, write_setting
from .core import group_logical_series, normalize_station_id, pathname_matches, split_pathname
from .dss_reader import DssReader, pydsstools_available
from .installer import InstallDialog

try:
    try:  # backend_qtagg (Matplotlib 3.5+) follows the Qt binding: Qt5 or Qt6
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
        from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
    except ImportError:
        from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
        from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
    from matplotlib.dates import AutoDateLocator, ConciseDateFormatter, date2num
    from matplotlib.figure import Figure
except Exception:  # pragma: no cover - depends on the QGIS distribution
    FigureCanvas = None
    NavigationToolbar = None
    AutoDateLocator = None
    ConciseDateFormatter = None
    date2num = None
    Figure = None


class StationClickTool(QgsMapToolIdentify):
    """Identify a feature only from the configured point-station layer."""

    stationClicked = pyqtSignal(object)
    stationMissed = pyqtSignal()

    def __init__(self, canvas, layer):
        super().__init__(canvas)
        self.layer = layer
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))

    def canvasReleaseEvent(self, event):
        results = self.identify(
            event.x(),
            event.y(),
            [self.layer],
            QgsMapToolIdentify.IdentifyMode.TopDownStopAtFirst,
        )
        if results:
            self.stationClicked.emit(results[0].mFeature)
        else:
            self.stationMissed.emit()


class DssExplorerDock(QDockWidget):
    def __init__(self, iface, parent=None):
        super().__init__("DSS Explorer", parent)
        self.iface = iface
        self.reader = None
        self.paths = []
        self.filtered_paths = []
        self.filtered_series = []
        self._connected_filename = ""
        self._station_layer = None
        self._station_layer_id = None
        self._syncing_selection = False
        self._map_tool = None
        self._previous_map_tool = None
        self._plot_axis = None
        self._hover_annotation = None
        self._hover_marker = None
        self._hover_points = []
        self._hover_x = []
        self._hover_units = ""
        self._current_series = None
        self.setObjectName("DssExplorerDock")
        self.setMinimumWidth(430)
        self._build_ui()
        project = QgsProject.instance()
        project.layersWillBeRemoved.connect(self._layers_will_be_removed)
        project.cleared.connect(self._project_cleared)
        self._refresh_layers()

    def _build_ui(self):
        container = QWidget()
        root = QVBoxLayout(container)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        self.explore_tab = QWidget()
        explore = QVBoxLayout(self.explore_tab)
        instruction = QLabel("Activate the cursor, then click a station once to load its DSS series.")
        instruction.setWordWrap(True)
        explore.addWidget(instruction)
        self.click_button = QPushButton("Activate station click tool")
        self.click_button.setCheckable(True)
        self.click_button.setMinimumHeight(32)
        self.click_button.setStyleSheet(
            "QPushButton:checked { background-color: #2e7d32; color: white; "
            "font-weight: bold; }"
        )
        self.click_button.setToolTip(
            "Activate a map cursor that opens the clicked station's DSS time series"
        )
        self.click_button.toggled.connect(self._toggle_click_tool)
        explore.addWidget(self.click_button)

        self.series_title = QLabel("No series loaded")
        title_font = QFont(self.series_title.font())
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 1)
        self.series_title.setFont(title_font)
        self.series_title.setWordWrap(True)
        self.series_title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        explore.addWidget(self.series_title)
        self.series_details = QLabel("Choose a station from the map or the logical-series catalog.")
        self.series_details.setWordWrap(True)
        self.series_details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        explore.addWidget(self.series_details)

        self.result_tabs = QTabWidget()
        chart_page = QWidget()
        chart_layout = QVBoxLayout(chart_page)
        chart_layout.setContentsMargins(2, 2, 2, 2)
        chart_layout.setSpacing(2)
        if FigureCanvas is not None:
            self.figure = Figure(figsize=(5, 3), constrained_layout=False)
            self.canvas = FigureCanvas(self.figure)
            self.canvas.setMinimumSize(QSize(240, 220))
            self.canvas.setMaximumHeight(440)
            self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self.navigation = NavigationToolbar(self.canvas, chart_page)
            self.navigation.hide()
            graph_controls = QHBoxLayout()
            graph_controls.setSpacing(4)
            for label, tooltip, callback in (
                ("Full extent", "Restore the full time-series extent", self.navigation.home),
                ("Pan", "Drag the plot to pan", self.navigation.pan),
                ("Zoom", "Drag a rectangle to zoom", self.navigation.zoom),
                ("Save image…", "Save the current graph as an image", self.navigation.save_figure),
            ):
                button = QPushButton(label)
                button.setMaximumHeight(26)
                button.setToolTip(tooltip)
                button.clicked.connect(callback)
                graph_controls.addWidget(button)
            graph_controls.addStretch(1)
            chart_layout.addLayout(graph_controls)
            chart_layout.addWidget(self.canvas, 1)
            self.canvas.mpl_connect("motion_notify_event", self._on_plot_hover)
            self.canvas.mpl_connect("figure_leave_event", self._hide_plot_hover)
        else:
            self.figure = None
            self.canvas = None
            self.navigation = None
            chart_note = QLabel("Matplotlib is unavailable; use the Table tab below.")
            chart_note.setWordWrap(True)
            chart_layout.addWidget(chart_note)
        self.result_tabs.addTab(chart_page, "Graph")

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Date/time", "Value", "Units", "Type"])
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.result_tabs.addTab(self.table, "Table")
        explore.addWidget(self.result_tabs, 1)
        csv_row = QHBoxLayout()
        csv_row.addStretch(1)
        self.csv_button = QPushButton("Export series to CSV…")
        self.csv_button.setToolTip("Save the loaded observations (date/time, value, units, type) as CSV")
        self.csv_button.setEnabled(False)
        self.csv_button.clicked.connect(self._export_csv)
        csv_row.addWidget(self.csv_button)
        explore.addLayout(csv_row)
        self.tabs.addTab(self.explore_tab, "Explore")

        self.catalog_tab = QWidget()
        catalog = QVBoxLayout(self.catalog_tab)

        filters = QGroupBox("Catalog filters")
        filters_form = QFormLayout(filters)
        self.c_combo = self._filter_combo()
        self.e_combo = self._filter_combo()
        self.f_combo = self._filter_combo()
        filters_form.addRow("C parameter", self.c_combo)
        filters_form.addRow("E interval", self.e_combo)
        filters_form.addRow("F version", self.f_combo)
        catalog.addWidget(filters)

        self.path_list = QListWidget()
        self.path_list.setAlternatingRowColors(True)
        self.path_list.currentItemChanged.connect(self._pathname_selected)
        self.catalog_summary = QLabel("No DSS catalog loaded")
        catalog.addWidget(self.catalog_summary)
        catalog.addWidget(QLabel("Logical series — date blocks are combined automatically"))
        catalog.addWidget(self.path_list, 1)
        self.tabs.addTab(self.catalog_tab, "Catalog")

        self.setup_tab = QWidget()
        setup = QVBoxLayout(self.setup_tab)

        connection = QGroupBox("DSS connection")
        connection_form = QFormLayout(connection)
        file_row = QHBoxLayout()
        self.dss_edit = QLineEdit(read_setting("dss_file"))
        self.dss_edit.textChanged.connect(self._dss_file_changed)
        file_row.addWidget(self.dss_edit)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_dss)
        file_row.addWidget(browse)
        connection_form.addRow("DSS file", file_row)
        self.connect_button = QPushButton("Connect and scan catalog")
        self.connect_button.clicked.connect(self._connect_dss)
        connection_form.addRow("", self.connect_button)
        self.dependency_panel = QWidget()
        dependency_layout = QVBoxLayout(self.dependency_panel)
        dependency_layout.setContentsMargins(0, 0, 0, 0)
        missing = QLabel(
            "<b>pydsstools is not installed</b> in the Python used by QGIS, so DSS "
            "files cannot be opened yet. Install it with one click (internet needed)."
        )
        missing.setWordWrap(True)
        missing.setStyleSheet("color: #b3261e;")
        dependency_layout.addWidget(missing)
        install_button = QPushButton("Install pydsstools")
        install_button.clicked.connect(self._install_dependency)
        dependency_layout.addWidget(install_button)
        self.dependency_panel.setVisible(not pydsstools_available())
        connection_form.addRow("", self.dependency_panel)
        setup.addWidget(connection)

        mapping = QGroupBox("Map connection")
        mapping_form = QFormLayout(mapping)
        layer_row = QHBoxLayout()
        self.layer_combo = QComboBox()
        self.layer_combo.currentIndexChanged.connect(self._station_layer_changed)
        layer_row.addWidget(self.layer_combo)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self._refresh_layers)
        layer_row.addWidget(refresh)
        mapping_form.addRow("Station layer", layer_row)
        self.field_combo = QComboBox()
        self.field_combo.currentTextChanged.connect(self._field_changed)
        mapping_form.addRow("Station ID field", self.field_combo)
        self.part_combo = QComboBox()
        self.part_combo.addItems(["A", "B", "C", "D", "E", "F"])
        self.part_combo.setCurrentText(read_setting("station_part", "B") or "B")
        self.part_combo.currentIndexChanged.connect(self._part_changed)
        mapping_form.addRow("DSS station part", self.part_combo)
        hint = QLabel("The station field must match the selected DSS pathname part.")
        hint.setWordWrap(True)
        mapping_form.addRow("", hint)
        setup.addWidget(mapping)
        setup.addStretch(1)
        self.tabs.addTab(self.setup_tab, "Setup")
        self.tabs.setCurrentWidget(self.setup_tab)

        self.status = QLabel(
            "Not connected — click Connect and scan catalog in Setup."
            if self.dss_edit.text()
            else "Not connected"
        )
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.setWidget(container)

    def close_reader(self):
        self._deactivate_click_tool()
        if self.reader is not None:
            self.reader.close()
            self.reader = None

    def closeEvent(self, event):
        # Closing releases the DSS file; drop its catalog too so the reopened
        # explorer never shows a session that can no longer read data.
        self._clear_results(
            close_reader=True,
            message="Explorer was closed — click Connect and scan catalog to continue.",
        )
        self.tabs.setCurrentWidget(self.setup_tab)
        super().closeEvent(event)

    def shutdown(self):
        """Release map, layer and project signals before plugin unload."""
        self.close_reader()
        self._disconnect_station_layer()
        project = QgsProject.instance()
        for signal, callback in (
            (project.layersWillBeRemoved, self._layers_will_be_removed),
            (project.cleared, self._project_cleared),
        ):
            try:
                signal.disconnect(callback)
            except (TypeError, RuntimeError):
                pass

    @staticmethod
    def _filter_combo():
        combo = QComboBox()
        combo.addItem("")
        return combo

    def _browse_dss(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select HEC-DSS file", "", "HEC-DSS (*.dss);;All files (*)"
        )
        if path:
            self.dss_edit.setText(path)

    def _install_dependency(self):
        dialog = InstallDialog(self)
        dialog.exec()
        self.dependency_panel.setVisible(not pydsstools_available())

    def _field_changed(self, name):
        if name:
            write_setting("station_field", name)

    def _part_changed(self, *args):
        write_setting("station_part", self.part_combo.currentText())
        self._apply_filters()

    def _export_csv(self):
        if not self._current_series:
            return
        station, logical_path, rows = self._current_series
        safe_name = "".join(char if char.isalnum() else "_" for char in station).strip("_") or "series"
        start = os.path.join(read_setting("csv_dir"), safe_name + ".csv")
        path, _ = QFileDialog.getSaveFileName(self, "Export series to CSV", start, "CSV (*.csv)")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            with open(path, "w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(["station", "datetime", "value", "units", "type", "dss_identity"])
                for timestamp, value, units, value_type in rows:
                    writer.writerow(
                        [station, timestamp, "" if value is None else value, units, value_type, logical_path]
                    )
        except OSError as exc:
            QMessageBox.critical(self, "CSV export failed", str(exc))
            return
        write_setting("csv_dir", os.path.dirname(path))
        self.status.setText("Saved {:,} rows to {}".format(len(rows), path))

    def _dss_file_changed(self, filename):
        """Discard every result belonging to the previous DSS file."""
        if filename.strip() != self._connected_filename:
            self._clear_results(
                close_reader=True,
                message="DSS file changed — click Connect and scan catalog.",
            )

    def _clear_results(self, close_reader=False, message="Not connected"):
        if close_reader:
            self.close_reader()
        self._connected_filename = ""
        self.paths = []
        self.filtered_paths = []
        self.filtered_series = []
        self.path_list.blockSignals(True)
        self.path_list.clear()
        self.path_list.blockSignals(False)
        for combo in (self.c_combo, self.e_combo, self.f_combo):
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("")
            combo.blockSignals(False)
        self.catalog_summary.setText("No DSS catalog loaded")
        self._clear_series_display()
        self.status.setText(message)

    def _clear_series_display(self):
        """Clear outputs tied to a previous station or station layer."""
        self.series_title.setText("No series loaded")
        self.series_title.setToolTip("")
        self.series_details.setText("Choose a station from the map or the logical-series catalog.")
        self._current_series = None
        self.csv_button.setEnabled(False)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self.table.setSortingEnabled(True)
        self._plot_axis = None
        self._hover_annotation = None
        self._hover_marker = None
        self._hover_points = []
        self._hover_x = []
        self._hover_units = ""
        if self.figure is not None:
            self.figure.clear()
            self.canvas.draw_idle()

    def _connect_dss(self):
        filename = self.dss_edit.text().strip()
        if not filename:
            QMessageBox.warning(self, "DSS Explorer", "Select a DSS file first.")
            return
        try:
            self._clear_results(close_reader=True, message="Scanning DSS catalog…")
            self.reader = DssReader(filename)
            paths = self.reader.catalog()
            self.paths = []
            for path in paths:
                try:
                    self.paths.append((path, split_pathname(path)))
                except ValueError:
                    continue
            if not self.paths:
                raise RuntimeError("No valid six-part pathnames were found.")
            self._connected_filename = filename
            write_setting("dss_file", filename)
            self._populate_filters()
            self._apply_filters()
            self.status.setText(
                "Connected — {:,} logical series from {:,} DSS date blocks".format(
                    len(self.filtered_series), len(self.paths)
                )
            )
            self.tabs.setCurrentWidget(self.explore_tab)
        except Exception as exc:
            self.close_reader()
            QMessageBox.critical(self, "DSS connection failed", str(exc))

    def _populate_filters(self):
        for combo, index in ((self.c_combo, 2), (self.e_combo, 4), (self.f_combo, 5)):
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("")
            combo.addItems(sorted({parts[index] for _, parts in self.paths if parts[index]}))
            combo.setCurrentIndex(0)
            combo.blockSignals(False)
            try:
                combo.currentIndexChanged.disconnect(self._apply_filters)
            except TypeError:
                pass
            combo.currentIndexChanged.connect(self._apply_filters)

    def _apply_filters(self, *args):
        self.filtered_paths = [
            (path, parts)
            for path, parts in self.paths
            if pathname_matches(
                parts, self.c_combo.currentText(), self.e_combo.currentText(), self.f_combo.currentText()
            )
        ]
        self.filtered_series = group_logical_series(self.filtered_paths)

        self.path_list.blockSignals(True)
        self.path_list.clear()
        station_part = self.part_combo.currentIndex()
        for logical_path, parts, block_paths in self.filtered_series:
            station = parts[station_part] or "(blank station ID)"
            label = "{}  |  {}  |  {}  |  {}  •  {:,} block{}".format(
                station,
                parts[2] or "(no C part)",
                parts[4] or "(no interval)",
                parts[5] or "(no version)",
                len(block_paths),
                "" if len(block_paths) == 1 else "s",
            )
            item = QListWidgetItem(label)
            item.setToolTip(logical_path + "\nCombined date blocks:\n" + "\n".join(block_paths))
            item.setData(Qt.ItemDataRole.UserRole, (logical_path, parts, block_paths))
            self.path_list.addItem(item)
        self.path_list.blockSignals(False)
        self.catalog_summary.setText(
            "{:,} logical series from {:,} matching DSS date blocks".format(
                len(self.filtered_series), len(self.filtered_paths)
            )
        )
        self.status.setText(
            "Showing {:,} logical series ({:,} DSS date blocks)".format(
                len(self.filtered_series), len(self.filtered_paths)
            )
        )

    def _refresh_layers(self):
        current_id = self.layer_combo.currentData() or read_setting("station_layer")
        self._disconnect_station_layer()
        self.layer_combo.blockSignals(True)
        self.layer_combo.clear()
        for layer in QgsProject.instance().mapLayers().values():
            if is_point_layer(layer):
                self.layer_combo.addItem(layer.name(), layer.id())
        index = self.layer_combo.findData(current_id)
        if index >= 0:
            self.layer_combo.setCurrentIndex(index)
        self.layer_combo.blockSignals(False)
        self._station_layer_changed()

    def _station_layer_changed(self, *args):
        self._deactivate_click_tool()
        previous_id = self._station_layer_id
        self._disconnect_station_layer()
        selected_id = self.layer_combo.currentData()
        self._station_layer = QgsProject.instance().mapLayer(selected_id)
        self._station_layer_id = self._station_layer.id() if self._station_layer is not None else None
        # Refill silently so the saved field is not overwritten by the first item.
        self.field_combo.blockSignals(True)
        self.field_combo.clear()
        if self._station_layer is not None:
            self.field_combo.addItems([field.name() for field in self._station_layer.fields()])
            preferred = self.field_combo.findText(read_setting("station_field"))
            if preferred < 0:
                preferred = self.field_combo.findText("Name", Qt.MatchFlag.MatchFixedString)
            if preferred >= 0:
                self.field_combo.setCurrentIndex(preferred)
        self.field_combo.blockSignals(False)
        if self._station_layer is not None:
            write_setting("station_layer", self._station_layer_id)
            self._field_changed(self.field_combo.currentText())
            self._station_layer.selectionChanged.connect(self._map_selection_changed)

        if previous_id != self._station_layer_id:
            self._clear_series_display()
            if self.reader is not None:
                self.status.setText("Station layer changed — select a station to load its DSS series.")

    def _disconnect_station_layer(self):
        """Disconnect through the live project layer, never a deleted wrapper."""
        layer = (
            QgsProject.instance().mapLayer(self._station_layer_id)
            if self._station_layer_id
            else None
        )
        if layer is not None:
            try:
                layer.selectionChanged.disconnect(self._map_selection_changed)
            except (TypeError, RuntimeError):
                pass
        self._station_layer = None
        self._station_layer_id = None

    def _current_station_layer(self):
        """Return the configured layer only while QGIS still owns it."""
        if not self._station_layer_id:
            return None
        layer = QgsProject.instance().mapLayer(self._station_layer_id)
        if layer is None:
            self._station_layer = None
            self._station_layer_id = None
            return None
        self._station_layer = layer
        return layer

    def _layers_will_be_removed(self, layer_ids):
        """Reset safely before QGIS destroys the configured station layer."""
        if self._station_layer_id not in set(layer_ids):
            return
        self._deactivate_click_tool()
        self._disconnect_station_layer()
        self.field_combo.clear()
        self._clear_series_display()
        self.status.setText("Station layer removed — load a point layer and refresh.")
        QTimer.singleShot(0, self._refresh_layers)

    def _project_cleared(self):
        """Start a clean session after New Project or project close."""
        self._deactivate_click_tool()
        self._disconnect_station_layer()
        self.layer_combo.blockSignals(True)
        self.layer_combo.clear()
        self.layer_combo.blockSignals(False)
        self.field_combo.clear()
        self.dss_edit.blockSignals(True)
        self.dss_edit.clear()
        self.dss_edit.blockSignals(False)
        self._clear_results(
            close_reader=True,
            message="Project cleared — ready for a new DSS and station layer.",
        )

    def _map_selection_changed(self, *args):
        layer = self._current_station_layer()
        if self._syncing_selection or layer is None or not self.reader:
            return
        selected = layer.selectedFeatures()
        if len(selected) != 1 or not self.field_combo.currentText():
            return
        self._open_station_feature(selected[0])

    def _open_station_feature(self, feature):
        key = normalize_station_id(feature[self.field_combo.currentText()])
        part_index = self.part_combo.currentIndex()
        matches = [
            (logical_path, parts, block_paths)
            for logical_path, parts, block_paths in self.filtered_series
            if normalize_station_id(parts[part_index]) == key
        ]
        if not matches:
            self.status.setText("No filtered DSS pathname matches the selected station.")
            return
        logical_path, parts, block_paths = matches[0]
        self._highlight_catalog_item(logical_path)
        try:
            self._load_series(logical_path, parts, block_paths, zoom_to_station=False)
        except Exception as exc:
            self.status.setText("Could not read the DSS series for {}.".format(parts[part_index]))
            self.iface.messageBar().pushWarning("DSS Explorer", str(exc))
            return
        if len(matches) > 1:
            self.status.setText(
                "Loaded the first of {:,} filtered series for {}. Narrow C/E/F in Catalog to choose another.".format(
                    len(matches), parts[part_index]
                )
            )

    def _toggle_click_tool(self, checked):
        if not checked:
            self._deactivate_click_tool(restore_previous=True)
            return
        if self.reader is None:
            QMessageBox.warning(self, "DSS Explorer", "Connect and scan a DSS file first.")
            self.click_button.blockSignals(True)
            self.click_button.setChecked(False)
            self.click_button.blockSignals(False)
            return
        station_layer = self._current_station_layer()
        if station_layer is None or not self.field_combo.currentText():
            QMessageBox.warning(self, "DSS Explorer", "Select a station layer and ID field first.")
            self.click_button.blockSignals(True)
            self.click_button.setChecked(False)
            self.click_button.blockSignals(False)
            return
        canvas = self.iface.mapCanvas()
        self._previous_map_tool = canvas.mapTool()
        self._map_tool = StationClickTool(canvas, station_layer)
        self._map_tool.stationClicked.connect(self._station_clicked)
        self._map_tool.stationMissed.connect(self._station_missed)
        self._map_tool.deactivated.connect(self._map_tool_deactivated)
        canvas.setMapTool(self._map_tool)
        self.click_button.setText("Click tool active — select a station")
        self.tabs.setCurrentWidget(self.explore_tab)
        self.status.setText("Click a station point on the map.")

    def _station_clicked(self, feature):
        layer = self._current_station_layer()
        if layer is None:
            self.status.setText("The station layer was removed. Load a point layer and refresh.")
            return
        self._syncing_selection = True
        try:
            layer.selectByIds([feature.id()])
        finally:
            self._syncing_selection = False
        self._flash_feature(feature.id())
        QApplication.processEvents()
        self._open_station_feature(feature)

    def _station_missed(self):
        self.status.setText(
            "No station found there. Click closer to a point in the configured station layer."
        )

    def _map_tool_deactivated(self):
        self.click_button.blockSignals(True)
        self.click_button.setChecked(False)
        self.click_button.blockSignals(False)
        self.click_button.setText("Activate station click tool")

    def _deactivate_click_tool(self, restore_previous=False):
        tool = self._map_tool
        if tool is None:
            return
        canvas = self.iface.mapCanvas()
        previous = self._previous_map_tool
        self._map_tool = None
        self._previous_map_tool = None
        if restore_previous and canvas.mapTool() is tool and previous is not None:
            canvas.setMapTool(previous)
        elif canvas.mapTool() is tool:
            canvas.unsetMapTool(tool)
        try:
            tool.stationClicked.disconnect(self._station_clicked)
        except TypeError:
            pass
        try:
            tool.stationMissed.disconnect(self._station_missed)
        except TypeError:
            pass
        self.click_button.blockSignals(True)
        self.click_button.setChecked(False)
        self.click_button.blockSignals(False)
        self.click_button.setText("Activate station click tool")

    def _highlight_catalog_item(self, logical_path):
        for row in range(self.path_list.count()):
            item = self.path_list.item(row)
            if item.data(Qt.ItemDataRole.UserRole)[0] == logical_path:
                self.path_list.blockSignals(True)
                self.path_list.setCurrentItem(item)
                self.path_list.scrollToItem(item)
                self.path_list.blockSignals(False)
                return

    def _pathname_selected(self, current, previous):
        if current is None or self.reader is None:
            return
        logical_path, parts, block_paths = current.data(Qt.ItemDataRole.UserRole)
        try:
            self._load_series(logical_path, parts, block_paths, zoom_to_station=True)
        except Exception as exc:
            QMessageBox.critical(self, "DSS series failed", str(exc))

    def _load_series(self, logical_path, parts, block_paths, zoom_to_station):
        self.status.setText(
            "Loading and combining {:,} DSS date block{}…".format(
                len(block_paths), "" if len(block_paths) == 1 else "s"
            )
        )
        QApplication.processEvents()
        self._show_series(logical_path, parts, block_paths)
        self._select_station(
            parts[self.part_combo.currentIndex()],
            zoom_to_station=zoom_to_station,
        )
        self.result_tabs.setCurrentIndex(0)
        self.tabs.setCurrentWidget(self.explore_tab)

    def _select_station(self, dss_station_id, zoom_to_station=True):
        layer = self._current_station_layer()
        field = self.field_combo.currentText()
        if layer is None or not field:
            return
        wanted = normalize_station_id(dss_station_id)
        feature_id = None
        for feature in layer.getFeatures():
            if normalize_station_id(feature[field]) == wanted:
                feature_id = feature.id()
                break
        if feature_id is None:
            self.status.setText("DSS station {!r} has no matching map feature.".format(dss_station_id))
            return
        self._syncing_selection = True
        try:
            layer.selectByIds([feature_id])
            canvas = self.iface.mapCanvas()
            if zoom_to_station:
                canvas.zoomToSelected(layer)
            self._flash_feature(feature_id)
        finally:
            self._syncing_selection = False

    def _flash_feature(self, feature_id):
        layer = self._current_station_layer()
        if layer is None:
            return
        canvas = self.iface.mapCanvas()
        try:
            canvas.flashFeatureIds(
                layer,
                [feature_id],
                QColor("#fff200"),
                QColor("#ff1744"),
                5,
                400,
            )
        except TypeError:  # Compatibility with older QGIS signatures.
            canvas.flashFeatureIds(layer, [feature_id])

    def _show_series(self, logical_path, parts, block_paths):
        rows = self.reader.read_time_series_blocks(block_paths)
        station = parts[self.part_combo.currentIndex()]
        units = next((row[2] for row in rows if row[2]), "")
        valid = [row[1] for row in rows if row[1] is not None]
        dates = []
        values = []
        for timestamp, value, _, _ in rows:
            try:
                dates.append(datetime.fromisoformat(timestamp))
            except ValueError:
                dates.append(None)
            values.append(value)

        period = "No valid dates"
        valid_dates = [date for date in dates if date is not None]
        if valid_dates:
            period = "{} to {}".format(min(valid_dates).date(), max(valid_dates).date())
        stats = "{:,} observations  •  {:,} missing  •  {}".format(
            len(rows), len(rows) - len(valid), period
        )
        if valid:
            stats += "  •  min {:.3g}  •  max {:.3g}  •  mean {:.3g} {}".format(
                min(valid), max(valid), sum(valid) / len(valid), units
            )
        self.series_title.setText(
            "{}  •  {}  •  {}".format(
                station,
                parts[2] or "No C part",
                parts[4] or "No interval",
            )
        )
        self.series_title.setToolTip(logical_path)
        self.series_details.setText(
            stats + "  •  {:,} DSS date block{} combined".format(
                len(block_paths), "" if len(block_paths) == 1 else "s"
            )
        )

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for row_index, (timestamp, value, row_units, value_type) in enumerate(rows):
            self.table.setItem(row_index, 0, QTableWidgetItem(timestamp))
            value_item = QTableWidgetItem()
            if value is not None:
                value_item.setData(Qt.ItemDataRole.EditRole, value)
            self.table.setItem(row_index, 1, value_item)
            self.table.setItem(row_index, 2, QTableWidgetItem(row_units))
            self.table.setItem(row_index, 3, QTableWidgetItem(value_type))
        self.table.setSortingEnabled(True)
        self.table.sortItems(0, Qt.SortOrder.AscendingOrder)

        if self.figure is not None:
            self.figure.clear()
            axis = self.figure.add_subplot(111)
            display_points = []
            plotted = []
            for date, value in zip(dates, values):
                if date is None:
                    continue
                numeric_value = float("nan") if value is None else float(value)
                display_points.append((date, numeric_value))
                if value is not None:
                    plotted.append((date, float(value)))
            display_points.sort(key=lambda item: item[0])
            plotted.sort(key=lambda item: item[0])
            plotted_dates = [item[0] for item in display_points]
            plotted_values = [item[1] for item in display_points]
            axis.plot(
                plotted_dates,
                plotted_values,
                color="#00796b",
                linewidth=1.35,
                marker="o" if len(plotted) <= 60 else None,
                markersize=3,
            )
            if plotted:
                axis.fill_between(plotted_dates, plotted_values, alpha=0.08, color="#00796b")
            axis.set_title(station, fontsize=11, fontweight="bold")
            axis.set_xlabel("Date")
            axis.set_ylabel(units or "Value")
            axis.grid(True, alpha=0.25)
            axis.margins(x=0.015)
            self.figure.subplots_adjust(left=0.12, right=0.98, bottom=0.18, top=0.88)
            locator = AutoDateLocator(minticks=3, maxticks=8)
            axis.xaxis.set_major_locator(locator)
            axis.xaxis.set_major_formatter(ConciseDateFormatter(locator))

            self._plot_axis = axis
            self._hover_points = plotted
            self._hover_x = [date2num(item[0]) for item in plotted]
            self._hover_units = units
            self._hover_annotation = axis.annotate(
                "",
                xy=(0, 0),
                xytext=(12, 12),
                textcoords="offset points",
                bbox={"boxstyle": "round,pad=0.4", "fc": "#fffde7", "ec": "#00796b"},
                arrowprops={"arrowstyle": "->", "color": "#00796b"},
                zorder=10,
            )
            self._hover_annotation.set_visible(False)
            (self._hover_marker,) = axis.plot(
                [], [], "o", color="#ff6f00", markersize=6, zorder=11
            )
            self.canvas.draw_idle()
        self._current_series = (station, logical_path, rows)
        self.csv_button.setEnabled(bool(rows))
        self.status.setText("Loaded {:,} observations for {}".format(len(rows), station))

    def _on_plot_hover(self, event):
        """Show the nearest observation when the pointer is close to the line."""
        if (
            self._plot_axis is None
            or self._hover_annotation is None
            or event.inaxes is not self._plot_axis
            or event.xdata is None
            or not self._hover_points
        ):
            self._hide_plot_hover()
            return

        insertion = bisect_left(self._hover_x, event.xdata)
        candidates = [index for index in (insertion - 1, insertion) if 0 <= index < len(self._hover_x)]
        nearest = min(
            candidates,
            key=lambda index: abs(self._hover_x[index] - event.xdata),
        )
        date, value = self._hover_points[nearest]
        point_x, point_y = self._plot_axis.transData.transform((self._hover_x[nearest], value))
        if event.x is None or event.y is None or hypot(point_x - event.x, point_y - event.y) > 18:
            self._hide_plot_hover()
            return

        self._hover_annotation.xy = (self._hover_x[nearest], value)
        value_text = "{:,.4g} {}".format(value, self._hover_units).strip()
        self._hover_annotation.set_text("{}\n{}".format(date.isoformat(sep=" "), value_text))
        self._hover_annotation.set_visible(True)
        self._hover_marker.set_data([date], [value])
        self.canvas.draw_idle()

    def _hide_plot_hover(self, *args):
        if self._hover_annotation is not None and self._hover_annotation.get_visible():
            self._hover_annotation.set_visible(False)
            if self._hover_marker is not None:
                self._hover_marker.set_data([], [])
            self.canvas.draw_idle()
