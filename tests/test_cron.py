from datetime import datetime
import unittest

from hiclaw.cron import CronError, CronExpression


class CronTest(unittest.TestCase):
    def test_parse_and_match(self) -> None:
        expr = CronExpression.parse("*/15 9-18 * * 1-5")
        dt = datetime(2026, 4, 6, 9, 30)  # Monday
        self.assertTrue(expr.matches(dt))

    def test_not_match_wrong_weekday(self) -> None:
        expr = CronExpression.parse("0 10 * * 1-5")
        dt = datetime(2026, 4, 5, 10, 0)  # Sunday
        self.assertFalse(expr.matches(dt))

    def test_invalid(self) -> None:
        with self.assertRaises(CronError):
            CronExpression.parse("bad expr")


if __name__ == "__main__":
    unittest.main()
