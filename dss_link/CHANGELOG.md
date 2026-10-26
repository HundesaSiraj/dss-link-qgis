# DSS Link changelog

## 0.6.0

- Support QGIS 4 / Qt6 alongside QGIS 3.28+ (scoped Qt enums, `exec()`,
  Qt-agnostic Matplotlib backend, `QMetaType` field types on QGIS 3.38+).
- Add plugin and toolbar icons.
- Export: read each logical series once with its D-part blocks merged, exactly
  as the Explorer does; `dss_path` records the block each value came from.
- Export: progress dialog with Cancel; a cancelled export writes no file.
- Export: store `obs_time` as UTC so daylight-saving rules cannot shift or
  invalidate timestamps.
- Explorer: add **Export series to CSV…** for the loaded series.
- Explorer: show a warning instead of a Python error when a map click or map
  selection cannot read its series.
- Explorer: closing the dock now resets the session, so a reopened explorer
  never shows a catalog it can no longer read.
- Explorer: warn in Setup when pydsstools is missing.
- Remember the last DSS file, station layer, ID field, pathname part and
  output folders between sessions.
- Station matching keeps letters and digits of every script, so non-Latin
  station IDs are no longer dropped.
- Round values to single precision (DSS storage), removing float32 noise such
  as `2.0999999046325684`.

## 0.5.1

- Clear stale station-layer references before QGIS destroys a removed layer.
- Refresh the station selector safely after layer removal.
- Reset graph, table, selection and map-tool state when the station layer
  changes.
- Reset the complete DSS Explorer session when the QGIS project is cleared.
- Disconnect project and layer signals cleanly when the plugin unloads.

## 0.5.0

- Group DSS catalog records that differ only by the D date-block part into one
  logical time series instead of exposing decade blocks as separate choices.
- Read every block explicitly, sort observations, and deduplicate overlapping
  timestamps.
- Make map clicks load directly even when the matching catalog item is already
  selected.
- Restore strong yellow-to-red five-pulse map feedback, including an immediate
  flash before a multi-block series is read.
- Replace the oversized Matplotlib toolbar with compact Full extent, Pan,
  Zoom, and Save image controls.
- Use stable plot margins and a bounded responsive canvas so the complete graph
  remains visible.
- Rebuild the observation table with aligned Date/time, Value, Units and Type
  columns plus sorting.
- Clear the previous catalog, graph and table whenever a new DSS file is
  selected.

## 0.4.0

- Make the graph resize to the available QGIS dock area so all axes remain
  visible.
- Add hover annotations showing the nearest observation date and value.
- Add Matplotlib navigation controls for pan, zoom, reset, configuration and
  image export.
- Improve date-axis formatting and graph styling.
- Expand the QGIS Plugin Manager description with setup and usage guidance.
- Credit HUNDESA SIRAJ MOHAMMED as concept originator and lead, and MARTA
  FIKADU SHIKUR as an extreme-event-modelling contributor.

## 0.3.0

- Redesign the explorer into **Explore**, **Catalog**, and **Setup** tabs so
  the graph and table remain visible at normal QGIS dock sizes.
- Automatically open the Explore tab when a map station or catalog pathname
  loads a series.
- Replace the station cursor with a layer-specific identify tool and report
  clicks that miss a station point.
- Make the active station cursor visually obvious.
- Attribute the plugin authorship and original concept to
  **HUNDESA SIRAJ MOHAMMED**.

## 0.2.1

- Add a dedicated **Click DSS Station** QGIS map tool.
- Open a station's DSS series with one map click without first activating the
  standard QGIS selection tool.
- Restore the previous map tool when the DSS click tool is switched off.

## 0.2.0

- Add an interactive right-side DSS Explorer dock.
- Click a map station to load its DSS series and chart.
- Select a DSS pathname to select, zoom to, and flash its map station.
- Add catalog filters, observation table, summary statistics, and live chart.
- Correct pydsstools 3.1 HecTime conversion using `HecTime.datetime()`.
- Read the pydsstools 3.x `data_units` and `data_type` metadata fields, with
  legacy fallbacks.

## 0.1.3

- Remove assumed `PRECIP`/`1MON` filter defaults.
- Add a DSS catalog scanner that populates C/E/F filter lists from the file.
- Open supported DSS files read-only and skip non-time-series records safely.

## 0.1.2

- Use the documented `search_path(sort=True)` catalog API in `pydsstools`
  3.1, with fallbacks for earlier releases.

## 0.1.1

- Support the snake-case `get_pathname_list` catalog API introduced by
  `pydsstools` 3.1 while retaining compatibility with the older camel-case API.

## 0.1.0

- Initial installable QGIS plugin.
- Configurable station ID pathname part and C/E/F filters.
- Tolerant station identifier matching with duplicate detection.
- DSS time-series extraction through `pydsstools`.
- GeoPackage station and temporal observation layers.
