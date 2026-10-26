# DSS Link for QGIS

<img src="dss_link/icon.png" width="72" align="right" alt="DSS Link icon">

**DSS Link** connects HEC-DSS time series to a point station layer in QGIS.
Click a station on the map to see its series as an interactive graph and
table, browse the DSS catalog, export a series to CSV, or write everything to
a temporal GeoPackage for the QGIS Temporal Controller.

HEC-DSS often splits one series into D-part date blocks (for example one per
decade). DSS Link combines them into a single logical series automatically.

![DSS Explorer](docs/explorer.png)

## Features

- **DSS Explorer** dock: one-click station tool, graph with hover values,
  pan/zoom/save, sortable table, summary statistics, CSV export
- **Catalog** filtered by C (parameter), E (interval) and F (version)
- **Linked GeoPackage export** with `stations` and temporal
  `dss_observations` layers, progress and Cancel
- Tolerant station matching (case, spaces, punctuation; any script)
- Read-only DSS access; settings remembered between sessions
- QGIS 3.28+ and QGIS 4 (Qt6)

## Requirements

- QGIS 3.28 or newer
- [`pydsstools`](https://github.com/gyanz/pydsstools) in the Python used by
  QGIS. On Windows, open the **OSGeo4W Shell** of your QGIS installation and
  run `python -m pip install pydsstools`, then restart QGIS.

## Install

1. Download `dss_link-<version>.zip` from
   [Releases](https://github.com/HundesaSiraj/dss-link-qgis/releases).
2. In QGIS: **Plugins › Manage and Install Plugins › Install from ZIP**.
3. Open **Plugins › DSS Link › Open interactive DSS Explorer**.

Full usage instructions: [dss_link/README.md](dss_link/README.md).

## Try it with sample data

`sample_data/` contains a **synthetic** DSS file and a station GeoPackage
(six Ethiopian towns, random but reproducible values; not observations).
Load `sample_stations.gpkg`, then in Setup choose `sample_stations.dss`,
field `Name`, part `B`. It includes multi-block monthly and daily series, a
DSS station without a map point (GAMBELA) and a map point without DSS data
(Jimma). Regenerate it with `scripts/make_sample_data.py` from the QGIS
Python console.

## Development

```text
dss_link/          the QGIS plugin (this folder is what goes in the zip)
tests/             unit tests for the QGIS-independent code
scripts/           build_zip.py, make_sample_data.py
sample_data/       synthetic demo data
```

```text
python -m unittest discover -s tests -v   # run tests
python scripts/build_zip.py               # -> dist/dss_link-<version>.zip
```

## Authors

- **HUNDESA SIRAJ MOHAMMED** — concept originator and lead. Remote Sensing
  Specialist, Climate Data Analyst, Hydrogeologist and WebGIS Expert.
- **MARTA FIKADU SHIKUR** — contributor. Remote Sensing Specialist and Extreme
  Event Modeller (SMEV, GEV and related extreme-value methods).

Issues and suggestions: [GitHub issues](https://github.com/HundesaSiraj/dss-link-qgis/issues).

## Licence

MIT — see [LICENSE](LICENSE). HEC-DSS is software of the US Army Corps of
Engineers Hydrologic Engineering Center; DSS Link is not affiliated with it.
