"""Create the synthetic DSS file and station GeoPackage in sample_data/.

Run from the QGIS Python console (pydsstools must be installed for QGIS):

    exec(open(r"<repo>/scripts/make_sample_data.py").read())

The values are random but reproducible (fixed seed); they are NOT observations.
Station locations are approximate town coordinates, for demonstration only.
"""

import math
import os
import random

from pydsstools.heclib.dss import HecDss

try:
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
except NameError:  # exec() from the QGIS console has no __file__
    REPO = r"E:/PERSONAL/AI-COURSE/DSS_developing/dss-link-qgis"
OUT = os.path.join(REPO, "sample_data")
DSS = os.path.join(OUT, "sample_stations.dss")
GPKG = os.path.join(OUT, "sample_stations.gpkg")

# DSS B-part name, station layer "Name" value, lon, lat, mean annual rainfall (mm)
STATIONS = [
    ("ADDIS ABABA", "Addis_Ababa", 38.75, 9.03, 1100),
    ("BAHIR DAR", "Bahir-Dar", 37.39, 11.59, 1400),
    ("HAWASSA", "Hawassa", 38.48, 7.06, 950),
    ("MEKELLE", "Mekelle", 39.47, 13.50, 600),
    ("DIRE DAWA", "Dire Dawa", 41.87, 9.60, 620),
    ("GAMBELA", None, 34.58, 8.25, 1300),  # in DSS only: tests "no map feature"
    (None, "Jimma", 36.83, 7.67, 1500),  # on the map only: tests "no DSS series"
]
MONTHLY_SHARE = [0.02, 0.03, 0.07, 0.09, 0.08, 0.11, 0.22, 0.21, 0.11, 0.04, 0.01, 0.01]


def _put(fid, pathname, values, start, units, kind):
    fid.put_ts(pathname, values=values, start_time=start, data_units=units, data_type=kind)


def make_dss(path):
    if os.path.exists(path):
        os.remove(path)
    rnd = random.Random(42)
    fid = HecDss.Open(path, mode="rw")
    try:
        for dss_name, _, _, _, annual in STATIONS:
            if dss_name is None:
                continue
            values = [
                round(max(0.0, annual * share * rnd.uniform(0.5, 1.6)), 1)
                for _ in range(1981, 2026)
                for share in MONTHLY_SHARE
            ]
            for index in rnd.sample(range(len(values)), 4):
                values[index] = float("nan")  # stored as DSS missing
            # 45 years of monthly data -> five decade D-part blocks per station
            _put(fid, "/ETHIOPIA/{}/PRECIP//1MON/SYNTHETIC/".format(dss_name),
                 values, "31JAN1981 24:00", "MM", "PER-CUM")
        for dss_name in ("ADDIS ABABA", "BAHIR DAR"):
            values = [round(max(0.0, rnd.gauss(2, 6)), 1) for _ in range(366 + 365 + 365)]
            # three years of daily data -> three yearly D-part blocks
            _put(fid, "/ETHIOPIA/{}/PRECIP//1DAY/SYNTHETIC/".format(dss_name),
                 values, "01JAN2020 24:00", "MM", "PER-CUM")
        values = [
            round(16 + 3 * math.sin(month / 12 * 2 * math.pi) + rnd.uniform(-1, 1), 2)
            for _ in range(30)
            for month in range(12)
        ]
        _put(fid, "/ETHIOPIA/ADDIS ABABA/TEMP-AIR//1MON/SYNTHETIC/",
             values, "31JAN1996 24:00", "DEG C", "PER-AVER")
    finally:
        fid.close()


def make_gpkg(path):
    from qgis.core import QgsFeature, QgsField, QgsGeometry, QgsPointXY, QgsVectorFileWriter, QgsVectorLayer
    from qgis.PyQt.QtCore import QVariant

    layer = QgsVectorLayer("Point?crs=EPSG:4326", "stations", "memory")
    layer.dataProvider().addAttributes([QgsField("Name", QVariant.String), QgsField("Region", QVariant.String)])
    layer.updateFields()
    features = []
    for _, map_name, lon, lat, _ in STATIONS:
        if map_name is None:
            continue
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(lon, lat)))
        feature.setAttributes([map_name, "Synthetic demo"])
        features.append(feature)
    layer.dataProvider().addFeatures(features)
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = "stations"
    result = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer, path, layer.transformContext(), options
    )
    if result[0] != QgsVectorFileWriter.NoError:
        raise RuntimeError(result[1])


os.makedirs(OUT, exist_ok=True)
make_dss(DSS)
make_gpkg(GPKG)
print("Wrote", DSS, "and", GPKG)
