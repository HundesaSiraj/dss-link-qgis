"""Build the installable plugin zip: dist/dss_link-<version>.zip

Run from anywhere:  python scripts/build_zip.py
The zip contains a single top-level dss_link/ folder, as QGIS expects.
"""

import configparser
import os
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(REPO, "dss_link")
SKIP_DIRS = {"__pycache__"}
SKIP_SUFFIXES = (".pyc", ".pyo")


def main():
    metadata = configparser.ConfigParser()
    metadata.read(os.path.join(PLUGIN, "metadata.txt"), encoding="utf-8")
    version = metadata["general"]["version"]
    dist = os.path.join(REPO, "dist")
    os.makedirs(dist, exist_ok=True)
    target = os.path.join(dist, "dss_link-{}.zip".format(version))
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for folder, dirs, files in os.walk(PLUGIN):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
            for name in sorted(files):
                if name.endswith(SKIP_SUFFIXES):
                    continue
                path = os.path.join(folder, name)
                archive.write(path, os.path.relpath(path, REPO))
    print(target)


if __name__ == "__main__":
    main()
