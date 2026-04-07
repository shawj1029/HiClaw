import unittest

from hiclaw.utils import parse_at_times, parse_every


class UtilsTest(unittest.TestCase):
    def test_parse_every(self) -> None:
        self.assertEqual(parse_every("30m"), 1800)
        self.assertEqual(parse_every("2h"), 7200)

    def test_parse_every_invalid(self) -> None:
        with self.assertRaises(ValueError):
            parse_every("abc")

    def test_parse_at_times(self) -> None:
        self.assertEqual(parse_at_times("09:00,14:30,09:00"), ["09:00", "14:30"])

    def test_parse_at_times_invalid(self) -> None:
        with self.assertRaises(ValueError):
            parse_at_times("24:00")


if __name__ == "__main__":
    unittest.main()
