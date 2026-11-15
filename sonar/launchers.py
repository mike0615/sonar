"""Open a discovered host in Skiff or MultiSSH Manager.

Neither program takes a host name on its command line (checked against
Skiff 1.2 skiff/app.py _parse_cli and MultiSSH Manager 2.2 app.main), so:

  Skiff            Sonar adds a site named "Sonar: <ip>" to Skiff's
                   ~/.config/skiff/sites.json (only when no saved site has
                   that host already) and runs:  <skiff_path> [skiff_args]
  MultiSSH Manager Sonar writes a one-host session file to
                   ~/.cache/sonar/multissh/sonar-<ip>.json and runs:
                   <multissh_path> <session_file>
"""

from __future__ import annotations

import getpass
import json
import os
import shlex
import shutil
import subprocess
import uuid
from typing import Dict, List, Optional, Tuple

from .config import Config, atomic_write, cache_dir


def resolve(path: str, fallback_name: str) -> Optional[str]:
    """Configured path if executable; otherwise the program name on PATH."""
    path = os.path.expanduser((path or "").strip())
    if path and os.path.isfile(path) and os.access(path, os.X_OK):
        return path
    for name in filter(None, [os.path.basename(path) if path else "", fallback_name]):
        found = shutil.which(name)
        if found:
            return found
    return None


def _fill(template: str, values: Dict[str, str]) -> List[str]:
    out = []
    for arg in shlex.split(template or ""):
        for k, v in values.items():
            arg = arg.replace("{%s}" % k, v)
        out.append(arg)
    return out


def _user(cfg: Config) -> str:
    u = cfg.get("launchers", "default_user")
    if u:
        return u
    try:
        return getpass.getuser()
    except Exception:
        return os.environ.get("USER", "")


def _values(cfg: Config, host: str, user: Optional[str]) -> Dict[str, str]:
    return {"host": host, "user": user if user is not None else _user(cfg),
            "port": str(cfg.getint("launchers", "ssh_port", 22))}


class Launcher:
    def __init__(self, cfg: Config, popen=subprocess.Popen):
        self.cfg = cfg
        self.popen = popen

    # ---- availability -------------------------------------------------
    def skiff_exe(self) -> Optional[str]:
        return resolve(self.cfg.get("launchers", "skiff_path"), "skiff")

    def multissh_exe(self) -> Optional[str]:
        return resolve(self.cfg.get("launchers", "multissh_path"), "multissh-manager")

    # ---- Skiff --------------------------------------------------------
    @staticmethod
    def skiff_sites_path() -> str:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
        return os.path.join(base, "skiff", "sites.json")

    def add_skiff_site(self, host: str, user: str, port: int, name: str = "") -> Tuple[str, bool]:
        """Add a Skiff site for host unless one exists. Returns (site name, added)."""
        path = self.skiff_sites_path()
        data = {"version": 2, "sites": []}
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict) or not isinstance(data.get("sites"), list):
                raise ValueError("%s is not a Skiff sites file" % path)
        for site in data["sites"]:
            if isinstance(site, dict) and site.get("host") == host and int(site.get("port") or 22) == port:
                return str(site.get("name") or host), False
        site_name = "Sonar: %s" % (name or host)
        data["sites"].append({
            "id": str(uuid.uuid4()), "name": site_name, "host": host, "port": port,
            "username": user, "save_password": False, "key_file": "", "auth": "agent",
            "protocol": "sftp", "remote_dir": "", "local_dir": os.path.expanduser("~"),
            "timeout": 20, "strict_host": True,
        })
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        atomic_write(path, json.dumps(data, indent=2) + "\n")
        return site_name, True

    def skiff_argv(self, host: str, user: Optional[str] = None) -> List[str]:
        exe = self.skiff_exe()
        if not exe:
            raise FileNotFoundError("Skiff is not installed (set skiff_path in Preferences)")
        return [exe] + _fill(self.cfg.get("launchers", "skiff_args"), _values(self.cfg, host, user))

    def open_skiff(self, host: str, user: Optional[str] = None, name: str = "") -> str:
        argv = self.skiff_argv(host, user)
        v = _values(self.cfg, host, user)
        msg = "Started Skiff"
        if self.cfg.getbool("launchers", "skiff_add_site", True):
            site, added = self.add_skiff_site(host, v["user"], int(v["port"]), name)
            msg = ("Started Skiff; site '%s' added - open it from the Site Manager (Ctrl+S)" % site
                   if added else "Started Skiff; use the saved site '%s' (Ctrl+S)" % site)
        self.popen(argv, start_new_session=True, stdin=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
        return msg

    # ---- MultiSSH Manager --------------------------------------------
    def write_multissh_session(self, host: str, user: str, port: int, name: str = "") -> str:
        folder = os.path.join(cache_dir(), "multissh")
        os.makedirs(folder, mode=0o700, exist_ok=True)
        path = os.path.join(folder, "sonar-%s.json" % host.replace(":", "_"))
        session = {
            "format": "multissh-manager", "version": 2,
            "root": {"id": "root", "name": "Sessions", "folders": [{
                "id": uuid.uuid4().hex[:12], "name": "Sonar", "folders": [],
                "hosts": [{
                    "id": uuid.uuid4().hex[:12], "name": name or host, "hostname": host,
                    "port": port, "username": user, "protocol": "ssh",
                    "auth_method": "default", "private_key_path": "", "jump_host": "",
                    "post_login_command": "", "extra_ssh_args": "",
                    "notes": "Added by Sonar", "save_password": False}]}],
                "hosts": []}}
        atomic_write(path, json.dumps(session, indent=2) + "\n")
        return path

    def multissh_argv(self, host: str, user: Optional[str] = None, name: str = "") -> List[str]:
        exe = self.multissh_exe()
        if not exe:
            raise FileNotFoundError("MultiSSH Manager is not installed (set multissh_path in Preferences)")
        v = _values(self.cfg, host, user)
        tmpl = self.cfg.get("launchers", "multissh_args")
        if "{session_file}" in tmpl:
            v["session_file"] = self.write_multissh_session(host, v["user"], int(v["port"]), name)
        return [exe] + _fill(tmpl, v)

    def open_multissh(self, host: str, user: Optional[str] = None, name: str = "") -> str:
        argv = self.multissh_argv(host, user, name)
        self.popen(argv, start_new_session=True, stdin=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
        return "Started MultiSSH Manager with a session for %s - double-click it to connect" % host

    # ---- browser ------------------------------------------------------
    def browser_argv(self, url: str) -> Optional[List[str]]:
        tmpl = self.cfg.get("launchers", "browser_command")
        if not tmpl:
            return None
        args = _fill(tmpl, {"url": url})
        if not any(url in a for a in args):
            args.append(url)
        return args
