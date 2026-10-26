# Contributing to DSS Link

Bug reports, ideas and pull requests are welcome. Please use the
[issue templates](https://github.com/HundesaSiraj/dss-link-qgis/issues/new/choose).

## Developing

1. Clone the repository and link or copy `dss_link/` into your QGIS profile's
   `python/plugins/` folder (Settings › User Profiles › Open Active Profile Folder).
2. Use the *Plugin Reloader* plugin to reload after each change.
3. Keep the code working on **QGIS 3.28+ and QGIS 4 (Qt6)**: use fully scoped
   Qt enums (`Qt.ItemDataRole.UserRole`), `exec()` rather than `exec_()`, and
   the helpers in `dss_link/compat.py`.
4. Keep `core.py` free of QGIS imports so it stays unit-testable.
5. Run the tests: `python -m unittest discover -s tests -v`.

## Releasing

1. Update `version` and `changelog` in `dss_link/metadata.txt`, plus
   `dss_link/CHANGELOG.md` and `CITATION.cff`.
2. Commit, then tag and push: `git tag v0.6.0 && git push origin v0.6.0`.
3. The *release* workflow tests, builds `dss_link-<version>.zip` and publishes
   it as a GitHub release.
