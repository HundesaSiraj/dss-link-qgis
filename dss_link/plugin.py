"""Main QGIS plugin implementation."""

from datetime import datetime
import os

from qgis.PyQt.QtCore import QCoreApplication, QDate, QDateTime, Qt, QTime, QTimeZone
from qgis.PyQt.QtGui import QAction, QIcon
from qgis.PyQt.QtWidgets import QMessageBox, QProgressDialog
from qgis.core import (
    QgsFeature,
    QgsField,
    QgsFields,
    QgsProject,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsWkbTypes,
)

from .compat import FIELD_DATETIME, FIELD_DOUBLE, FIELD_STRING
from .core import group_logical_series, normalize_station_id, pathname_matches, split_pathname
from .dialog import DssLinkDialog
from .dss_reader import DssDependencyError, DssReader, pydsstools_available
from .dock import DssExplorerDock
from .installer import InstallDialog

PLUGIN_DIR = os.path.dirname(__file__)


def plugin_icon(name):
    return QIcon(os.path.join(PLUGIN_DIR, "icons", name))


class ExportCancelled(Exception):
    pass


class DssLinkPlugin:
    MENU = "&DSS Link"

    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.explorer_action = None
        self.dock = None

    def initGui(self):
        self.explorer_action = QAction(
            plugin_icon("dss_link.svg"), "Open interactive DSS Explorer", self.iface.mainWindow()
        )
        self.explorer_action.setObjectName("DssExplorerAction")
        self.explorer_action.triggered.connect(self.show_explorer)
        self.iface.addPluginToMenu(self.MENU, self.explorer_action)
        self.iface.addToolBarIcon(self.explorer_action)

        self.action = QAction(
            plugin_icon("export_gpkg.svg"), "Export DSS to linked GeoPackage…", self.iface.mainWindow()
        )
        self.action.setObjectName("DssLinkAction")
        self.action.triggered.connect(self.run)
        self.iface.addPluginToMenu(self.MENU, self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        if self.dock:
            self.dock.shutdown()
            self.iface.removeDockWidget(self.dock)
            self.dock.deleteLater()
            self.dock = None
        if self.explorer_action:
            self.iface.removePluginMenu(self.MENU, self.explorer_action)
            self.iface.removeToolBarIcon(self.explorer_action)
        if self.action:
            self.iface.removePluginMenu(self.MENU, self.action)
            self.iface.removeToolBarIcon(self.action)

    def show_explorer(self):
        if self.dock is None:
            self.dock = DssExplorerDock(self.iface, self.iface.mainWindow())
            self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        self.dock.show()
        self.dock.raise_()

    def run(self):
        if not pydsstools_available():
            answer = QMessageBox.question(
                self.iface.mainWindow(),
                "DSS Link dependency",
                "DSS Link needs the pydsstools package to read DSS files, and it is not "
                "installed in the Python used by QGIS.\n\nInstall it now? (internet needed)",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            if not InstallDialog(self.iface.mainWindow()).exec() and not pydsstools_available():
                return
        dialog = DssLinkDialog(self.iface.mainWindow())
        if not dialog.exec():
            return
        try:
            summary = self._create_layers(dialog.settings())
        except ExportCancelled:
            self.iface.messageBar().pushInfo("DSS Link", "Export cancelled — no GeoPackage was written.")
            return
        except DssDependencyError as exc:
            QMessageBox.critical(self.iface.mainWindow(), "DSS Link dependency", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(self.iface.mainWindow(), "DSS Link failed", str(exc))
            return

        unmatched_preview = ", ".join(summary["unmatched"][:20]) or "None"
        if len(summary["unmatched"]) > 20:
            unmatched_preview += " …"
        QMessageBox.information(
            self.iface.mainWindow(),
            "DSS Link complete",
            "Created {:,} observations from {:,} logical series ({:,} DSS date blocks).\n"
            "Matched stations: {:,}\nUnmatched DSS station IDs: {:,}\n"
            "Unmatched: {}\nSkipped unreadable series: {:,}\n\n{}".format(
                summary["observations"],
                summary["series"],
                summary["records"],
                summary["matched_stations"],
                len(summary["unmatched"]),
                unmatched_preview,
                len(summary["skipped"]),
                summary["output"],
            ),
        )

    def _create_layers(self, options):
        output = options["output"]
        if os.path.exists(output):
            raise RuntimeError("Output already exists. Choose a new GeoPackage path: {}".format(output))

        station_layer = options["station_layer"]
        station_lookup = {}
        duplicate_ids = set()
        for feature in station_layer.getFeatures():
            key = normalize_station_id(feature[options["station_field"]])
            if not key:
                continue
            if key in station_lookup:
                duplicate_ids.add(key)
            station_lookup[key] = feature
        if duplicate_ids:
            raise RuntimeError(
                "The station layer contains duplicate normalized IDs: {}".format(
                    ", ".join(sorted(duplicate_ids)[:20])
                )
            )

        selected = []
        invalid = []
        with DssReader(options["dss_file"]) as reader:
            for pathname in reader.catalog():
                try:
                    parts = split_pathname(pathname)
                except ValueError:
                    invalid.append(pathname)
                    continue
                if pathname_matches(parts, options["parameter"], options["interval"], options["version"]):
                    selected.append((pathname, parts))

            if not selected:
                raise RuntimeError("No DSS records matched the supplied C/E/F filters.")

            # Read each logical series once, merging its D-part date blocks
            # exactly as the DSS Explorer does.
            series = group_logical_series(selected)
            observation_layer = self._new_observation_layer(station_layer)
            provider = observation_layer.dataProvider()
            output_features = []
            unmatched = set()
            matched = set()
            skipped = []
            observation_count = 0

            progress = QProgressDialog(
                "Reading DSS series…", "Cancel", 0, len(series) + 1, self.iface.mainWindow()
            )
            progress.setWindowTitle("DSS Link export")
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.setMinimumDuration(0)
            try:
                for index, (logical_path, parts, block_paths) in enumerate(series):
                    progress.setValue(index)
                    progress.setLabelText(
                        "Reading series {:,} of {:,}\n{}".format(index + 1, len(series), logical_path)
                    )
                    QCoreApplication.processEvents()
                    if progress.wasCanceled():
                        raise ExportCancelled()

                    station_text = parts[options["station_part"]]
                    station_key = normalize_station_id(station_text)
                    station_feature = station_lookup.get(station_key)
                    if station_feature is None:
                        unmatched.add(station_text)
                        continue
                    matched.add(station_key)
                    try:
                        rows = reader.read_time_series_blocks(
                            block_paths, options["start_date"], options["end_date"], with_source=True
                        )
                    except Exception as exc:
                        skipped.append((logical_path, str(exc)))
                        continue
                    for timestamp, value, units, value_type, block_path in rows:
                        feature = QgsFeature(observation_layer.fields())
                        feature.setGeometry(station_feature.geometry())
                        feature.setAttributes(
                            [
                                str(station_feature[options["station_field"]]),
                                self._to_qdatetime(timestamp),
                                timestamp,
                                value,
                                units,
                                value_type,
                                logical_path,
                                block_path,
                                parts[0], parts[1], parts[2], parts[4], parts[5],
                            ]
                        )
                        output_features.append(feature)
                        observation_count += 1
                        if len(output_features) >= 5000:
                            provider.addFeatures(output_features)
                            output_features = []
                            QCoreApplication.processEvents()
                if output_features:
                    provider.addFeatures(output_features)

                if observation_count == 0:
                    detail = skipped[0][1] if skipped else "No DSS station IDs matched the point layer."
                    raise RuntimeError(
                        "No observations could be created. First detail: {}".format(detail)
                    )

                progress.setLabelText("Writing GeoPackage…")
                progress.setValue(len(series))
                progress.setCancelButton(None)
                QCoreApplication.processEvents()
                self._write_layer(station_layer, output, "stations", create=True)
                self._write_layer(observation_layer, output, "dss_observations", create=False)
            finally:
                progress.close()

        stations_uri = "{}|layername=stations".format(output)
        observations_uri = "{}|layername=dss_observations".format(output)
        stations_output = QgsVectorLayer(stations_uri, "DSS stations", "ogr")
        observations_output = QgsVectorLayer(observations_uri, "DSS observations", "ogr")
        if stations_output.isValid():
            QgsProject.instance().addMapLayer(stations_output)
        if observations_output.isValid():
            QgsProject.instance().addMapLayer(observations_output)

        return {
            "output": output,
            "records": len(selected),
            "series": len(series),
            "observations": observation_count,
            "matched_stations": len(matched),
            "unmatched": sorted(unmatched),
            "skipped": skipped,
            "invalid_pathnames": invalid,
        }

    @staticmethod
    def _new_observation_layer(station_layer):
        geometry_name = QgsWkbTypes.displayString(station_layer.wkbType())
        uri = geometry_name or "Point"
        layer = QgsVectorLayer(uri, "dss_observations", "memory")
        layer.setCrs(station_layer.crs())
        fields = QgsFields()
        for name, field_type in (
            ("station_id", FIELD_STRING),
            ("obs_time", FIELD_DATETIME),
            ("obs_time_text", FIELD_STRING),
            ("value", FIELD_DOUBLE),
            ("units", FIELD_STRING),
            ("value_type", FIELD_STRING),
            ("dss_identity", FIELD_STRING),
            ("dss_path", FIELD_STRING),
            ("dss_a", FIELD_STRING),
            ("dss_b", FIELD_STRING),
            ("dss_c", FIELD_STRING),
            ("dss_e", FIELD_STRING),
            ("dss_f", FIELD_STRING),
        ):
            fields.append(QgsField(name, field_type))
        layer.dataProvider().addAttributes(fields)
        layer.updateFields()
        return layer

    @staticmethod
    def _to_qdatetime(timestamp):
        """Store DSS times as UTC so daylight-saving rules cannot shift or drop them."""
        try:
            value = datetime.fromisoformat(timestamp)
        except ValueError:
            return None
        return QDateTime(
            QDate(value.year, value.month, value.day),
            QTime(value.hour, value.minute, value.second),
            QTimeZone(b"UTC"),
        )

    @staticmethod
    def _write_layer(layer, output, layer_name, create):
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.layerName = layer_name
        options.fileEncoding = "UTF-8"
        options.actionOnExistingFile = (
            QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteFile
            if create
            else QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer
        )
        result = QgsVectorFileWriter.writeAsVectorFormatV3(
            layer, output, QgsProject.instance().transformContext(), options
        )
        if result[0] != QgsVectorFileWriter.WriterError.NoError:
            raise RuntimeError("Could not write {}: {}".format(layer_name, result[1]))
