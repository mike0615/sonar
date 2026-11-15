import os
import unittest

from tests import helpers
from sonar import about_config
from sonar.help_content import HELP_TOPICS, as_markdown


class HelpTests(unittest.TestCase):
    def test_help_md_in_sync(self):
        path = os.path.join(helpers.ROOT, "HELP.md")
        if not os.path.isfile(path):
            self.skipTest("HELP.md not in this tree")
        self.assertEqual(open(path, encoding="utf-8").read(), as_markdown(),
                         "HELP.md is stale: python3 -m sonar.help_content > HELP.md")

    def test_topics(self):
        heads = [h for h, _ in HELP_TOPICS]
        for need in ("Skiff and MultiSSH Manager", "Master configuration file", "Export", "Not included"):
            self.assertIn(need, heads)

    def test_about(self):
        self.assertEqual(about_config.APP_NAME, "Sonar")
        self.assertTrue(os.path.isfile(about_config.LOGO_FILE))
        self.assertIn("MIT License", about_config.LICENSE_NOTICE)
        svg = open(about_config.LOGO_FILE).read().lower()
        for banned in ("lrn", "softperfect"):
            self.assertNotIn(banned, svg)


if __name__ == "__main__":
    unittest.main()
