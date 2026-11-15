import unittest

from tests import helpers  # noqa: F401
from sonar.iprange import RangeError, parse_ports, parse_range


class RangeTests(unittest.TestCase):
    def test_single(self):
        self.assertEqual(parse_range("127.0.0.1"), ["127.0.0.1"])

    def test_cidr_skips_network_and_broadcast(self):
        r = parse_range("127.0.5.0/29")
        self.assertEqual(r[0], "127.0.5.1")
        self.assertEqual(r[-1], "127.0.5.6")
        self.assertEqual(len(r), 6)
        self.assertEqual(parse_range("127.0.0.8/31"), ["127.0.0.8", "127.0.0.9"])

    def test_dash_forms(self):
        self.assertEqual(len(parse_range("127.0.0.1-127.0.0.10")), 10)
        self.assertEqual(parse_range("127.0.0.250-254")[-1], "127.0.0.254")
        self.assertEqual(len(parse_range("127.0.0.250-127.0.1.5")), 12)

    def test_wildcard(self):
        r = parse_range("127.0.9.*")
        self.assertEqual((r[0], r[-1], len(r)), ("127.0.9.1", "127.0.9.254", 254))

    def test_mixed_and_dedup(self):
        r = parse_range("127.0.0.1, 127.0.0.1-3 ; 127.0.0.2\n127.0.0.10")
        self.assertEqual(r, ["127.0.0.1", "127.0.0.2", "127.0.0.3", "127.0.0.10"])

    def test_errors(self):
        for bad in ("", "hello", "127.0.0.10-5", "127.0.0.0/8", "1.*.0.1", "127.0.0.300"):
            with self.assertRaises(RangeError, msg=bad):
                parse_range(bad)

    def test_ports(self):
        self.assertEqual(parse_ports("80, 22,443 8000-8002"), [22, 80, 443, 8000, 8001, 8002])
        self.assertEqual(parse_ports(""), [])
        with self.assertRaises(RangeError):
            parse_ports("70000")


if __name__ == "__main__":
    unittest.main()
