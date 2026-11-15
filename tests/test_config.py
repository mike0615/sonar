import os
import unittest

from tests import helpers


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.d = helpers.isolate_config()
        from sonar import config
        self.config = config

    def test_defaults_system_user_layers(self):
        with open(os.environ["SONAR_SYSTEM_CONF"], "w") as fh:
            fh.write("[launchers]\nskiff_path = /opt/x/skiff\nmultissh_path = /opt/x/mssh\n[scan]\nthreads = 10\n")
        c = self.config.Config()
        self.assertEqual(c.get("launchers", "skiff_path"), "/opt/x/skiff")
        self.assertEqual(c.getint("scan", "threads"), 10)
        self.assertEqual(c.getint("scan", "timeout_ms"), 1000)  # built-in default
        self.assertEqual(c.origin("scan", "threads"), "system")
        c.set_user("launchers", "skiff_path", "/home/me/bin/skiff")
        c.set_user("scan", "threads", "10")  # same as system -> no override
        c.save_user()
        c2 = self.config.Config()
        self.assertEqual(c2.get("launchers", "skiff_path"), "/home/me/bin/skiff")
        self.assertEqual(c2.origin("launchers", "skiff_path"), "user")
        self.assertEqual(c2.origin("scan", "threads"), "system")
        self.assertEqual(oct(os.stat(c2.user_path).st_mode & 0o777), "0o600")
        text = open(c2.user_path).read()
        self.assertIn("skiff_path = /home/me/bin/skiff", text)
        self.assertNotIn("threads", text)

    def test_shipped_conf_matches_defaults(self):
        path = os.path.join(helpers.ROOT, "packaging", "sonar.conf")
        if not os.path.isfile(path):
            self.skipTest("packaging/sonar.conf not in this tree")
        c = self.config.Config(system_path=path)
        for sec, keys in self.config.DEFAULTS.items():
            for k, v in keys.items():
                self.assertEqual(c.get(sec, k), v, "%s.%s" % (sec, k))
                self.assertEqual(c.origin(sec, k), "system", "%s.%s missing from sonar.conf" % (sec, k))

    def test_ranges_and_favorites(self):
        self.config.save_ranges([{"name": "lab", "range": "127.0.0.1-9"}])
        self.config.save_favorites([{"ip": "127.0.0.5", "name": "five"}])
        self.assertEqual(self.config.load_ranges()[0]["range"], "127.0.0.1-9")
        self.assertEqual(self.config.load_favorites()[0]["name"], "five")
        self.config.save_state({"last_range": "x"})
        self.assertEqual(self.config.load_state()["last_range"], "x")


if __name__ == "__main__":
    unittest.main()
