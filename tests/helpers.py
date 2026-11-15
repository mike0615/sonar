import os
import socket
import sys
import tempfile
import threading

ROOT = os.environ.get("SONAR_ROOT") or os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def isolate_config():
    d = tempfile.mkdtemp(prefix="sonar-test-")
    os.environ["XDG_CONFIG_HOME"] = os.path.join(d, "config")
    os.environ["XDG_CACHE_HOME"] = os.path.join(d, "cache")
    os.environ["SONAR_SYSTEM_CONF"] = os.path.join(d, "etc-sonar.conf")
    return d


class Listener:
    """TCP listener on 127.0.0.1:<free port> that accepts and closes."""

    def __init__(self, host="127.0.0.1"):
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((host, 0))
        self.sock.listen(64)
        self.port = self.sock.getsockname()[1]
        self._stop = False
        self.t = threading.Thread(target=self._run, daemon=True)
        self.t.start()

    def _run(self):
        self.sock.settimeout(0.2)
        while not self._stop:
            try:
                c, _ = self.sock.accept()
                c.close()
            except OSError:
                pass

    def close(self):
        self._stop = True
        self.t.join(1)
        self.sock.close()


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p
