import csv
import io
import os
import tempfile
import unittest
from xml.etree import ElementTree as ET

from tests import helpers  # noqa: F401
from sonar.export import COLUMNS, export, to_csv, to_html, to_txt, to_xml
from sonar.scanner import HostResult

ROWS = [HostResult(ip="127.0.0.1", alive=True, rtt_ms=0.4, hostname="localhost", mac="00:50:56:AA:BB:CC",
                   vendor="VMware, Inc.", netbios="BOX<&>", workgroup="WG", open_ports=[22, 80]),
        HostResult(ip="127.0.0.2", alive=False)]


class ExportTests(unittest.TestCase):
    def test_csv(self):
        rows = list(csv.reader(io.StringIO(to_csv(ROWS))))
        self.assertEqual(rows[0], [c[1] for c in COLUMNS])
        self.assertEqual(rows[1][0], "127.0.0.1")
        self.assertEqual(rows[1][7], "22,80")
        self.assertEqual(rows[2][-1], "no response")

    def test_txt(self):
        t = to_txt(ROWS)
        self.assertIn("localhost", t)
        self.assertIn("2 host(s)", t)

    def test_html_escapes(self):
        h = to_html(ROWS)
        self.assertIn("BOX&lt;&amp;&gt;", h)
        self.assertNotIn("BOX<&>", h)

    def test_xml(self):
        root = ET.fromstring(to_xml(ROWS).split("\n", 1)[1])
        hosts = root.findall("host")
        self.assertEqual(hosts[0].get("ip"), "127.0.0.1")
        self.assertEqual([p.get("number") for p in hosts[0].find("ports")], ["22", "80"])
        self.assertEqual(hosts[0].findtext("netbios"), "BOX<&>")
        self.assertEqual(hosts[1].get("status"), "down")

    def test_export_by_extension(self):
        d = tempfile.mkdtemp()
        for ext in ("csv", "txt", "html", "htm", "xml"):
            p = os.path.join(d, "r." + ext)
            export(ROWS, p)
            self.assertGreater(os.path.getsize(p), 50)
        with self.assertRaises(ValueError):
            export(ROWS, os.path.join(d, "r.pdf"))


if __name__ == "__main__":
    unittest.main()
