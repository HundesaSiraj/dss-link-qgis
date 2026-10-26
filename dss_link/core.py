"""Pure-Python pathname and station matching helpers."""


PART_NAMES = ("A", "B", "C", "D", "E", "F")


def split_pathname(pathname):
    """Return the six HEC-DSS pathname parts, preserving empty parts."""
    if not isinstance(pathname, str):
        raise ValueError("DSS pathname must be text")
    parts = pathname.strip().strip("/").split("/")
    if len(parts) != 6:
        raise ValueError(
            "Expected /A/B/C/D/E/F/ but found {} parts in {!r}".format(
                len(parts), pathname
            )
        )
    return tuple(parts)


def normalize_station_id(value):
    """Normalize station identifiers for tolerant, case-insensitive matching.

    Letters and digits of any script are kept, so non-Latin IDs still match;
    spaces, underscores, hyphens and other punctuation are ignored.
    """
    if value is None:
        return ""
    return "".join(char for char in str(value).upper() if char.isalnum())


def pathname_matches(parts, parameter="", interval="", version=""):
    """Apply optional exact, case-insensitive C/E/F filters."""
    filters = ((2, parameter), (4, interval), (5, version))
    return all(
        not wanted.strip() or parts[index].strip().upper() == wanted.strip().upper()
        for index, wanted in filters
    )


def identity_path(parts):
    """Return a DSS record identity with a blank D (date-block) part."""
    values = list(parts)
    values[3] = ""
    return "/" + "/".join(values) + "/"


def group_logical_series(path_entries):
    """Combine catalog entries that differ only by the D date-block part."""
    grouped = {}
    for path, parts in path_entries:
        logical_path = identity_path(parts)
        if logical_path not in grouped:
            grouped[logical_path] = [parts, []]
        grouped[logical_path][1].append(path)
    return [
        (logical_path, value[0], tuple(value[1]))
        for logical_path, value in grouped.items()
    ]
