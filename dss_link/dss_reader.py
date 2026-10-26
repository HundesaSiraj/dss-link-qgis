"""Adapter around pydsstools, isolated from the QGIS user interface."""

from datetime import datetime
import math


class DssDependencyError(RuntimeError):
    pass


def pydsstools_available():
    try:
        import pydsstools.heclib.dss  # noqa: F401
    except Exception:
        return False
    return True


class DssReader:
    def __init__(self, filename):
        try:
            from pydsstools.heclib.dss import HecDss
        except Exception as exc:
            raise DssDependencyError(
                "Direct DSS access requires 'pydsstools' in the Python environment "
                "used by QGIS. See the plugin README for installation instructions."
            ) from exc

        try:
            self._handle = HecDss.Open(filename, mode="r")
        except TypeError:
            # pydsstools 2.x did not expose the read-only mode argument.
            self._handle = HecDss.Open(filename)

    def close(self):
        if self._handle is not None:
            self._handle.close()
            self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()

    def catalog(self):
        # pydsstools 3.1 replaced getPathnameList with search_path. Keep
        # fallbacks for older releases and short-lived prerelease spellings.
        search_method = getattr(self._handle, "search_path", None)
        if search_method is not None:
            paths = search_method(sort=True)
            return [
                path.decode("utf-8", errors="replace") if isinstance(path, bytes) else str(path)
                for path in paths
            ]

        method = getattr(self._handle, "get_pathname_list", None)
        if method is None:
            method = getattr(self._handle, "getPathnameList", None)
        if method is None:
            raise RuntimeError(
                "This pydsstools version exposes no supported catalog method. "
                "Expected search_path (3.1+) or getPathnameList (2.x)."
            )
        pattern = "/*/*/*/*/*/*/"
        try:
            paths = method(pattern, sort=1)
        except TypeError:
            try:
                paths = method(pattern)
            except TypeError:
                paths = method()
        return [
            path.decode("utf-8", errors="replace") if isinstance(path, bytes) else str(path)
            for path in paths
        ]

    def read_time_series(self, pathname, start_date=None, end_date=None):
        if bool(start_date) != bool(end_date):
            raise ValueError("Provide both start and end dates, or leave both blank.")
        kwargs = {"trim_missing": True}
        if start_date and end_date:
            kwargs["window"] = (start_date, end_date)
        container = self._handle.read_ts(pathname, **kwargs)

        times = getattr(container, "times", None)
        if times is None:
            times = getattr(container, "pytimes", None)
        values = getattr(container, "values", None)
        if times is None or values is None:
            raise RuntimeError("DSS reader returned no timestamps or values for {}".format(pathname))

        units = str(
            getattr(container, "data_units", None)
            or getattr(container, "units", "")
            or ""
        )
        value_type = str(
            getattr(container, "data_type", None)
            or getattr(container, "type", "")
            or ""
        )
        rows = []
        for timestamp, value in zip(times, values):
            number = _clean_number(value)
            rows.append((_iso_timestamp(timestamp), number, units, value_type))
        return rows

    def read_time_series_blocks(self, pathnames, start_date=None, end_date=None, with_source=False):
        """Read and merge the D-part date blocks of one logical DSS series.

        With ``with_source`` each row gains a fifth item: the block pathname
        the value was read from.
        """
        merged = {}
        errors = []
        for pathname in pathnames:
            try:
                rows = self.read_time_series(pathname, start_date, end_date)
            except Exception as exc:
                errors.append("{}: {}".format(pathname, exc))
                continue
            for row in rows:
                if with_source:
                    row = row + (pathname,)
                timestamp = row[0]
                existing = merged.get(timestamp)
                if existing is None or (existing[1] is None and row[1] is not None):
                    merged[timestamp] = row
        if not merged:
            detail = errors[0] if errors else "No readable observations were returned."
            raise RuntimeError("Could not read this logical DSS series. {}".format(detail))
        return [merged[timestamp] for timestamp in sorted(merged)]


def _clean_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or abs(number) >= 1.0e30:
        return None
    # DSS stores single-precision floats; drop the float32 noise
    # (2.0999999046325684 -> 2.1) that would otherwise show in tables and exports.
    return float("{:.7g}".format(number))


def _iso_timestamp(value):
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if hasattr(value, "datetime"):
        converted = value.datetime()
        if converted is not None:
            return converted.isoformat(sep=" ")
    if hasattr(value, "to_pydatetime"):
        return value.to_pydatetime().isoformat(sep=" ")
    text = str(value)
    return text.replace("T", " ")
