"""Minimal NBNS node-status responder for tests: python3 nbns_responder.py IP NAME GROUP"""
import socket, struct, sys
ip, name, group = sys.argv[1], sys.argv[2], sys.argv[3]
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.bind((ip, 137))
mac = open("/sys/class/net/v2-n/address").read().strip()
while True:
    data, addr = s.recvfrom(1024)
    if len(data) < 50:
        continue
    names = [(name, 0x00, 0x0400), (name, 0x20, 0x0400), (group, 0x00, 0x8400)]
    rd = bytes([len(names)]) + b"".join(n.encode().ljust(15) + bytes([sfx]) + struct.pack("!H", fl) for n, sfx, fl in names)
    rd += bytes.fromhex(mac.replace(":", "")) + b"\0" * 40
    resp = data[:2] + struct.pack("!HHHHH", 0x8400, 0, 1, 0, 0) + data[12:46] + struct.pack("!HHIH", 0x21, 1, 0, len(rd)) + rd
    s.sendto(resp, addr)
