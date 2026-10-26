"""Helpers that keep DSS Link working on QGIS 3 (Qt5) and QGIS 4 (Qt6)."""

from qgis.core import Qgis, QgsSettings, QgsVectorLayer, QgsWkbTypes

try:
    POINT_GEOMETRY = Qgis.GeometryType.Point  # QGIS 3.30+
except AttributeError:
    POINT_GEOMETRY = QgsWkbTypes.PointGeometry

if Qgis.QGIS_VERSION_INT >= 33800:
    from qgis.PyQt.QtCore import QMetaType

    FIELD_STRING = QMetaType.Type.QString
    FIELD_DOUBLE = QMetaType.Type.Double
    FIELD_DATETIME = QMetaType.Type.QDateTime
else:
    from qgis.PyQt.QtCore import QVariant

    FIELD_STRING = QVariant.String
    FIELD_DOUBLE = QVariant.Double
    FIELD_DATETIME = QVariant.DateTime


def is_point_layer(layer):
    return isinstance(layer, QgsVectorLayer) and layer.geometryType() == POINT_GEOMETRY


SETTINGS_PREFIX = "dss_link/"


def read_setting(key, default=""):
    value = QgsSettings().value(SETTINGS_PREFIX + key, default)
    return default if value is None else str(value)


def write_setting(key, value):
    QgsSettings().setValue(SETTINGS_PREFIX + key, value)
