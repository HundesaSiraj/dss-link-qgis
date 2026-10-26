"""Tests for the QGIS-independent parts of DSS Link.

Run from the repository root:  python -m unittest discover -s tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dss_link.core import (  # noqa: E402
    group_logical_series,
    identity_path,
    normalize_station_id,
    pathname_matches,
    split_pathname,
)
from dss_link.dss_reader import DssReader, _clean_number, _iso_timestamp  # noqa: E402


class SplitPathnameTests(unittest.TestCase):
    def test_six_parts_with_blank_d(self):
        self.assertEqual(
            split_pathname("/ETHIOPIA/ADDIS ABABA/PRECIP//1MON/OBS/"),
            ("ETHIOPIA", "ADDIS ABABA", "PRECIP", "", "1MON", "OBS"),
        )

    def test_rejects_wrong_part_count(self):
        with self.assertRaises(ValueError):
            split_pathname("/A/B/C/")

    def test_rejects_non_text(self):
        with self.assertRaises(ValueError):
            split_pathname(None)


class NormalizeStationIdTests(unittest.TestCase):
    def test_ignores_case_space_and_punctuation(self):
        for raw in ("Addis Ababa", "ADDIS_ABABA", "addis-ababa", " Addis.Ababa "):
            self.assertEqual(normalize_station_id(raw), "ADDISABABA")

    def test_keeps_non_latin_letters(self):
        self.assertEqual(normalize_station_id("አዲስ አበባ"), "አዲስአበባ")
        self.assertEqual(normalize_station_id("الموصل-1"), "الموصل1")

    def test_none_and_numbers(self):
        self.assertEqual(normalize_station_id(None), "")
        self.assertEqual(normalize_station_id(1234), "1234")


class PathnameMatchesTests(unittest.TestCase):
    parts = ("A", "ST01", "PRECIP", "01JAN2000", "1MON", "OBS")

    def test_blank_filters_match_all(self):
        self.assertTrue(pathname_matches(self.parts))

    def test_filters_are_case_insensitive(self):
        self.assertTrue(pathname_matches(self.parts, "precip", "1mon", "obs"))

    def test_mismatch(self):
        self.assertFalse(pathname_matches(self.parts, interval="1DAY"))


class LogicalSeriesTests(unittest.TestCase):
    def test_identity_blanks_d_part(self):
        self.assertEqual(identity_path(("A", "B", "C", "01JAN2000", "1MON", "F")), "/A/B/C//1MON/F/")

    def test_groups_blocks_that_differ_only_by_d(self):
        paths = [
            "/A/ST1/PRECIP/01JAN1990/1MON/OBS/",
            "/A/ST1/PRECIP/01JAN2000/1MON/OBS/",
            "/A/ST2/PRECIP/01JAN1990/1MON/OBS/",
        ]
        groups = group_logical_series([(p, split_pathname(p)) for p in paths])
        self.assertEqual(len(groups), 2)
        logical, _, blocks = groups[0]
        self.assertEqual(logical, "/A/ST1/PRECIP//1MON/OBS/")
        self.assertEqual(blocks, tuple(paths[:2]))


class ReaderHelperTests(unittest.TestCase):
    def test_clean_number(self):
        self.assertEqual(_clean_number(2.0999999046325684), 2.1)
        self.assertIsNone(_clean_number(float("nan")))
        self.assertIsNone(_clean_number(-3.402823466e38))  # DSS missing flag
        self.assertIsNone(_clean_number("x"))

    def test_iso_timestamp(self):
        from datetime import datetime

        self.assertEqual(_iso_timestamp(datetime(2020, 1, 2)), "2020-01-02 00:00:00")
        self.assertEqual(_iso_timestamp("2020-01-02T00:00:00"), "2020-01-02 00:00:00")

    def test_block_merge_sorts_dedupes_and_prefers_values(self):
        blocks = {
            "b2": [("2000-02-01 00:00:00", 2.0, "MM", "PER-CUM"), ("2000-03-01 00:00:00", 3.0, "MM", "PER-CUM")],
            "b1": [("2000-01-01 00:00:00", 1.0, "MM", "PER-CUM"), ("2000-02-01 00:00:00", None, "MM", "PER-CUM")],
        }
        reader = DssReader.__new__(DssReader)  # skip pydsstools; stub the block reader
        reader.read_time_series = lambda path, start=None, end=None: blocks[path]
        rows = reader.read_time_series_blocks(["b2", "b1"], with_source=True)
        self.assertEqual([row[0][:7] for row in rows], ["2000-01", "2000-02", "2000-03"])
        self.assertEqual(rows[1][1], 2.0)  # the valid value wins over the missing one
        self.assertEqual(rows[0][4], "b1")

    def test_block_merge_reports_unreadable_series(self):
        reader = DssReader.__new__(DssReader)

        def fail(path, start=None, end=None):
            raise OSError("broken block")

        reader.read_time_series = fail
        with self.assertRaisesRegex(RuntimeError, "broken block"):
            reader.read_time_series_blocks(["b1"])


if __name__ == "__main__":
    unittest.main()
