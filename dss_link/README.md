# DSS Link for QGIS

DSS Link connects HEC-DSS time-series records to a QGIS point station layer.
It provides an interactive DSS Explorer and can also create a GeoPackage
containing stations and temporal point observations.

## Authors and professional contributions

- **Hundesa Siraj Mohammed — concept originator and lead developer.** Remote Sensing
  Specialist, Climate Data Analyst, Hydrogeologist and WebGIS Expert. He
  originated the DSS–QGIS integration concept and leads its climate,
  hydrogeological and WebGIS direction.
- **Marta Fikadu Shikur — contributor.** Remote Sensing Specialist and Extreme
  Event Modeller. She contributed technical input informed by work with SMEV,
  GEV and other extreme-value methods.

## Requirements

- QGIS 3.28 or newer (QGIS 3 and QGIS 4 / Qt6 are both supported)
- A point station layer loaded in QGIS
- The `pydsstools` Python package (Windows and Linux, 64-bit)

### Installing pydsstools — one click

Open **DSS Explorer > Setup**. If pydsstools is missing, a red notice with an
**Install pydsstools** button appears. Click it: DSS Link runs
`pip install --user pydsstools` with the Python that QGIS uses and shows the
progress. No OSGeo4W Shell or command line is needed. An internet connection is
required; restart QGIS if asked.

Manual alternative (Windows): open the **OSGeo4W Shell** of your QGIS
installation and run `python -m pip install pydsstools`, then restart QGIS.

pydsstools publishes no ready-made package for macOS; there it must be built
from source (see the [pydsstools project](https://github.com/gyanz/pydsstools)).

## Install the plugin

1. Open **Plugins > Manage and Install Plugins** in QGIS.
2. Search for **DSS Link** under **All** and click **Install Plugin**.
3. Enable **DSS Link** if QGIS does not enable it automatically.

Offline alternative: download `dss_link-<version>.zip` from the
[GitHub releases](https://github.com/HundesaSiraj/dss-link-qgis/releases) and
use **Install from ZIP**. Do not use GitHub's *Code › Download ZIP*: that is
the source repository, not an installable plugin.

To try the plugin without your own data, use `sample_data/sample_stations.dss`
and `sample_data/sample_stations.gpkg` from the repository (synthetic values,
station ID field `Name`, DSS part B).

## Interactive DSS Explorer

1. Open **Plugins > DSS Link > Open interactive DSS Explorer**.
2. In **Setup**, select a DSS file, click **Connect and scan catalog**, and
   choose the point station layer, identifier field, and matching DSS pathname
   part (usually B).
3. In **Explore**, click **Activate station click tool**, then click a station
   point once on the map. Its series opens automatically.
4. Use the **Graph** and **Table** tabs to inspect the loaded observations.
   Hover close to the plotted line for an exact date and value. Use the graph
   toolbar to pan, zoom, restore the full extent, or save the plot. Use
   **Export series to CSV…** to save the loaded observations.
5. In **Catalog**, optionally filter by C, E, or F and select any pathname to
   graph it and locate its station on the map.

HEC-DSS may store a continuous regular time series as several D-part date
blocks, often one block per decade. DSS Link groups these catalog records and
reads them as one logical series. Duplicate timestamps at block boundaries are
deduplicated automatically. The raw block pathnames remain available in each
catalog item's tooltip.

The dock displays a compact interactive time-series chart, a sortable and
properly sized observation table, units, date range, missing count, minimum,
maximum, and mean. Selecting a map station gives immediate flash feedback;
selecting a catalog series locates and flashes the corresponding map station.
Choosing a different DSS filename clears the old catalog, graph and table. It
reads DSS in read-only mode. Matplotlib is used for the chart when it is
present in the QGIS distribution; the observation table still works without
it.

The DSS file, station layer, ID field and pathname part are remembered
between sessions. Closing the dock releases the DSS file; click **Connect and
scan catalog** again after reopening it.

Removing or replacing the configured station layer safely clears its previous
selection, graph and table state. The layer selector refreshes from the current
project without retaining deleted QGIS layer objects. Clearing the QGIS project
also closes the DSS reader and resets the explorer for a fresh dataset.

## GeoPackage export

1. Load the station shapefile or GeoPackage point layer in QGIS.
2. Open **Plugins > DSS Link > Export DSS to linked GeoPackage**.
3. Select the DSS file, station layer and station identifier field.
4. Click **Scan DSS catalog** and choose actual C/E/F values from the lists.
5. Select the pathname part containing the station ID (usually B).
6. Choose a new output GeoPackage and click **Create linked layers**.

Identifier matching is case-insensitive and ignores whitespace, underscores,
hyphens and other punctuation; letters and digits in any script are kept.
The export shows progress and can be cancelled; a cancelled export writes no file. The plugin refuses duplicate normalized station
IDs because they would create ambiguous matches.

## Output

- `stations`: a copy of the source station layer
- `dss_observations`: point observations with timestamp, value, units, DSS
  pathname identity and pathname components

The observation timestamp is stored both as a native QGIS datetime field
(`obs_time`) for the Temporal Controller and as ISO text (`obs_time_text`) for
traceability. `obs_time` carries the DSS time unchanged, tagged as UTC so that
daylight-saving rules of the computer cannot shift it. Each logical series is
read once with its D-part blocks merged; `dss_identity` is the logical
pathname (blank D part) and `dss_path` the block a value was read from.

HEC-DSS stamps period values (for example monthly totals) at the end of the
period, so a January total appears as `1981-02-01 00:00` (DSS `31JAN1981 24:00`).

## Current limitations

- Reading DSS files depends on `pydsstools` (Windows and Linux; macOS needs a
  source build).
- GeoPackage export creates a new file rather than incrementally syncing.
- Reading runs in the foreground; very large DSS files may temporarily make
  the QGIS interface less responsive (the export can be cancelled).
- Automatic rainfall styling and temporal configuration are planned for a
  subsequent version.
