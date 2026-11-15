import os
import socket
import struct
import tempfile
import threading
import unittest

from tests import helpers
from sonar import probe


def nbstat_reply(tid, names, mac=b"\x52\x54\x00\x12\x34\x56"):
    body = struct.pack("!HHHHHH", tid, 0x8400, 0, 1, 0, 0)
    body += probe._nb_encode(b"*") + struct.pack("!HHIH", 0x21, 1, 0, 1 + 18 * len(names) + 46)
    body += bytes([len(names)])
    for name, suffix, group in names:
        body += name.encode().ljust(15, b" ") + bytes([suffix]) + struct.pack("!H", 0x8400 if group else 0x0400)
    body += mac + b"\0" * 40
    return body


class ProbeTests(unittest.TestCase):
    def test_checksum(self):
        # RFC 1071 example: 0x0001 + 0xf203 + 0xf4f5 + 0xf6f7 -> ~0xddf2
        self.assertEqual(probe._checksum(bytes.fromhex("0001f203f4f5f6f7")), 0x220D)

    def test_nbstat_request_layout(self):
        pkt = probe.nbstat_request(0x1234)
        self.assertEqual(len(pkt), 50)
        self.assertEqual(pkt[:2], b"\x12\x34")
        self.assertEqual(pkt[12], 32)
        self.assertEqual(pkt[13:15], b"CK")  # '*' = 0x2A -> 'C','K'
        self.assertEqual(pkt[-4:], b"\x00\x21\x00\x01")

    def test_parse_nbstat(self):
        r = probe.parse_nbstat(nbstat_reply(7, [("FILESRV", 0x00, False), ("FILESRV", 0x20, False),
                                                ("LABGROUP", 0x00, True)]))
        self.assertEqual((r["name"], r["group"], r["mac"]), ("FILESRV", "LABGROUP", "52:54:00:12:34:56"))

    def test_netbios_query_against_local_responder(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        srv.bind(("127.0.0.1", 0))
        port = srv.getsockname()[1]

        def serve():
            data, addr = srv.recvfrom(1024)
            tid = struct.unpack("!H", data[:2])[0]
            srv.sendto(nbstat_reply(tid, [("TESTBOX", 0, False), ("WORKGROUP", 0, True)]), addr)
        t = threading.Thread(target=serve, daemon=True)
        t.start()
        r = probe.netbios_query("127.0.0.1", 2.0, port=port)
        t.join(2)
        srv.close()
        self.assertEqual(r.get("name"), "TESTBOX")
        self.assertEqual(r.get("group"), "WORKGROUP")

    def test_netbios_no_answer(self):
        self.assertEqual(probe.netbios_query("127.0.0.1", 0.3, port=helpers.free_port()), {})

    def test_tcp_ping_and_port_scan(self):
        lst = helpers.Listener()
        closed = helpers.free_port()
        try:
            self.assertIsNotNone(probe.tcp_ping("127.0.0.1", 1.0, [closed]))  # RST = up
            self.assertEqual(probe.scan_ports("127.0.0.1", [closed, lst.port], 1.0), [lst.port])
        finally:
            lst.close()

    def test_many_ports_batches(self):
        lst = helpers.Listener()
        try:
            ports = list(range(40000, 40100)) + [lst.port]
            self.assertIn(lst.port, probe.scan_ports("127.0.0.1", ports, 1.0))
        finally:
            lst.close()

    def test_pinger_forced_tcp(self):
        p = probe.Pinger("tcp", [helpers.free_port()])
        self.assertEqual(p.method, "tcp")
        self.assertIsNotNone(p.ping("127.0.0.7", 1.0))

    def test_pinger_auto_never_needs_root(self):
        p = probe.Pinger("auto")
        self.assertIn(p.method, ("icmp", "ping", "tcp"))
        self.assertIsNotNone(p.ping("127.0.0.1", 1.0))

    @unittest.skipUnless(probe.icmp_socket_allowed(), "unprivileged ICMP not allowed here")
    def test_icmp_loopback(self):
        self.assertIsNotNone(probe.icmp_ping("127.0.0.1", 1.0))

    def test_read_neighbours(self):
        f = tempfile.NamedTemporaryFile("w", delete=False)
        f.write("IP address       HW type     Flags       HW address            Mask     Device\n"
                "198.18.99.2      0x1         0x2         00:50:56:aa:bb:cc     *        veth0\n"
                "198.18.99.3      0x1         0x0         00:00:00:00:00:00     *        veth0\n")
        f.close()
        self.assertEqual(probe.read_neighbours(f.name), {"198.18.99.2": "00:50:56:AA:BB:CC"})
        os.unlink(f.name)

    def test_oui(self):
        f = tempfile.NamedTemporaryFile("w", delete=False)
        f.write("OUI/MA-L   Organization\n\n00-50-56   (hex)\t\tVMware, Inc.\n005056     (base 16)\t\tVMware, Inc.\n")
        f.close()
        db = probe.OuiDb([f.name])
        self.assertEqual(db.lookup("00:50:56:01:02:03"), "VMware, Inc.")
        self.assertEqual(db.lookup("02:11:22:33:44:55"), "(locally administered)")
        self.assertEqual(db.lookup(""), "")
        os.unlink(f.name)

    @unittest.skipUnless(os.path.isfile("/usr/share/hwdata/oui.txt"), "hwdata not installed")
    def test_system_oui(self):
        db = probe.OuiDb()
        self.assertGreater(len(db), 10000)
        self.assertIn("VMware", db.lookup("00:50:56:00:00:01"))


if __name__ == "__main__":
    unittest.main()
