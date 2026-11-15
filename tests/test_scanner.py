import threading
import time
import unittest

from tests import helpers
from sonar.scanner import ScanOptions, Scanner


class ScannerTests(unittest.TestCase):
    def test_loopback_scan(self):
        lst = helpers.Listener()
        try:
            opts = ScanOptions(threads=16, timeout_ms=500, ping_method="tcp",
                               probe_ports=[helpers.free_port()], netbios=False,
                               ports=[lst.port, helpers.free_port()])
            got, prog = [], []
            alive = Scanner(opts).run(["127.0.0.%d" % i for i in range(1, 21)], got.append,
                                      lambda d, t: prog.append((d, t)))
            self.assertEqual(alive, 20)
            self.assertEqual(prog[-1], (20, 20))
            by_ip = {r.ip: r for r in got}
            self.assertEqual(by_ip["127.0.0.1"].open_ports, [lst.port])
            self.assertTrue(all(r.alive and r.rtt_ms is not None for r in got))
        finally:
            lst.close()

    def test_stop(self):
        opts = ScanOptions(threads=4, timeout_ms=300, ping_method="tcp", scan_ports=False,
                           netbios=False, resolve_hostnames=False)
        s = Scanner(opts)
        got = []
        threading.Timer(0.05, s.stop).start()
        t0 = time.monotonic()
        s.run(["127.0.%d.%d" % (i // 250, i % 250 + 1) for i in range(5000)], got.append)
        self.assertLess(time.monotonic() - t0, 10)
        self.assertLess(len(got), 5000)

    def test_show_dead(self):
        # forced icmp/ping on an unreachable-by-design TEST-NET is not used; instead
        # make the pinger report "down" and check dead hosts are listed.
        opts = ScanOptions(threads=2, ping_method="tcp", show_dead=True, scan_ports=False, netbios=False)
        s = Scanner(opts)
        s.pinger.ping = lambda ip, t: None
        got = []
        alive = s.run(["127.0.0.1", "127.0.0.2"], got.append)
        self.assertEqual(alive, 0)
        self.assertEqual(sorted(r.ip for r in got), ["127.0.0.1", "127.0.0.2"])
        self.assertFalse(any(r.alive for r in got))


if __name__ == "__main__":
    unittest.main()
