"""Launcher tests with stub skiff / multissh-manager scripts that record argv."""
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest

from tests import helpers

STUB = """#!/bin/sh
out="$SONAR_STUB_LOG"
printf '%s' "$0" > "$out.tmp"
for a in "$@"; do printf '\\n%s' "$a" >> "$out.tmp"; done
mv "$out.tmp" "$out"
"""


def make_stub(folder, name):
    path = os.path.join(folder, name)
    with open(path, "w") as fh:
        fh.write(STUB)
    os.chmod(path, 0o755)
    return path


def wait_log(path, timeout=5.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if os.path.exists(path):
            with open(path) as fh:
                return fh.read().split("\n")
        time.sleep(0.05)
    raise AssertionError("stub never ran: %s" % path)


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.d = helpers.isolate_config()
        self.bin = os.path.join(self.d, "bin")
        os.makedirs(self.bin)
        self.skiff = make_stub(self.bin, "skiff")
        self.mssh = make_stub(self.bin, "multissh-manager")
        with open(os.environ["SONAR_SYSTEM_CONF"], "w") as fh:
            fh.write("[launchers]\nskiff_path = %s\nmultissh_path = %s\ndefault_user = admin\nssh_port = 2222\n"
                     % (self.skiff, self.mssh))
        from sonar.config import Config
        from sonar.launchers import Launcher
        self.Config, self.Launcher = Config, Launcher
        self.log = os.path.join(self.d, "argv.log")
        os.environ["SONAR_STUB_LOG"] = self.log

    def test_skiff_real_exec(self):
        L = self.Launcher(self.Config())
        msg = L.open_skiff("127.0.0.5", name="web5")
        argv = wait_log(self.log)
        print("\n  skiff argv:", argv)
        self.assertEqual(argv, [self.skiff])
        self.assertIn("Sonar: web5", msg)
        sites = json.load(open(L.skiff_sites_path()))["sites"]
        self.assertEqual(len(sites), 1)
        s = sites[0]
        self.assertEqual((s["host"], s["port"], s["username"], s["auth"]), ("127.0.0.5", 2222, "admin", "agent"))
        self.assertNotIn("password", s)
        src = os.environ.get("SKIFF_SRC")
        if src and os.path.isdir(src):
            # Load it with Skiff's own sites.json reader.
            code = ("import sys; sys.path.insert(0, %r); from skiff import config;"
                    "s = [x for x in config.load_sites() if x['host'] == '127.0.0.5'][0];"
                    "print(s['name'], s['host'], s['port'], s['username'], s['auth'], s.get('sudo'))" % src)
            out = subprocess.run([sys.executable, "-B", "-c", code], stdout=subprocess.PIPE, check=True,
                                 env=dict(os.environ)).stdout.decode()
            print("  skiff parsed:", out.strip())
            self.assertIn("Sonar: web5 127.0.0.5 2222 admin agent", out)
        # second time: no duplicate site
        os.unlink(self.log)
        msg2 = L.open_skiff("127.0.0.5")
        wait_log(self.log)
        with open(L.skiff_sites_path()) as fh:
            self.assertEqual(len(json.load(fh)["sites"]), 1)
        self.assertIn("saved site", msg2)

    def test_skiff_keeps_existing_sites(self):
        L = self.Launcher(self.Config())
        p = L.skiff_sites_path()
        os.makedirs(os.path.dirname(p))
        json.dump({"version": 2, "sites": [{"id": "a", "name": "mine", "host": "10.9.9.9", "port": 22}]}, open(p, "w"))
        L.open_skiff("127.0.0.9")
        wait_log(self.log)
        names = [s["name"] for s in json.load(open(p))["sites"]]
        self.assertEqual(names, ["mine", "Sonar: 127.0.0.9"])

    def test_skiff_args_template_and_no_site(self):
        cfg = self.Config()
        cfg.set_user("launchers", "skiff_args", "--host {host} --user {user} --port {port}")
        cfg.set_user("launchers", "skiff_add_site", "no")
        argv = self.Launcher(cfg).skiff_argv("127.0.0.3")
        self.assertEqual(argv, [self.skiff, "--host", "127.0.0.3", "--user", "admin", "--port", "2222"])

    def test_multissh_real_exec(self):
        L = self.Launcher(self.Config())
        L.open_multissh("127.0.0.6", name="db6")
        argv = wait_log(self.log)
        print("\n  multissh argv:", argv)
        self.assertEqual(len(argv), 2)
        self.assertEqual(argv[0], self.mssh)
        sess = argv[1]
        self.assertTrue(sess.endswith("/sonar/multissh/sonar-127.0.0.6.json"), sess)
        data = json.load(open(sess))
        self.assertEqual(data["format"], "multissh-manager")
        host = data["root"]["folders"][0]["hosts"][0]
        self.assertEqual((host["hostname"], host["port"], host["username"], host["name"]),
                         ("127.0.0.6", 2222, "admin", "db6"))
        self.assertEqual(oct(os.stat(sess).st_mode & 0o777), "0o600")
        src = os.environ.get("MULTISSH_SRC")
        if src and os.path.isdir(src):
            # Load it with MultiSSH Manager's own parser.
            code = ("import sys; sys.path.insert(0, %r); from multissh_manager.models import SessionStore;"
                    "s = SessionStore.load(%r); h = list(s.root.walk_hosts())[0];"
                    "print(h.hostname, h.port, h.username, ' '.join(h.build_argv()))" % (src, sess))
            out = subprocess.run([sys.executable, "-c", code], stdout=subprocess.PIPE, check=True).stdout.decode()
            print("  multissh parsed:", out.strip())
            self.assertIn("ssh -p 2222 admin@127.0.0.6", out)

    def test_path_fallback_and_missing(self):
        cfg = self.Config()
        cfg.set_user("launchers", "skiff_path", "/nonexistent/skiff")
        cfg.set_user("launchers", "multissh_path", "/nonexistent/multissh-manager")
        old = os.environ["PATH"]
        try:
            os.environ["PATH"] = self.bin + os.pathsep + old
            L = self.Launcher(cfg)
            self.assertEqual(L.skiff_exe(), self.skiff)       # found on PATH
            os.environ["PATH"] = "/nonexistent"
            self.assertIsNone(L.skiff_exe())
            self.assertIsNone(L.multissh_exe())
            with self.assertRaises(FileNotFoundError):
                L.skiff_argv("127.0.0.1")
        finally:
            os.environ["PATH"] = old


if __name__ == "__main__":
    unittest.main()
