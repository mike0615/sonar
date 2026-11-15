"""Master configuration (INI) plus saved ranges and favourites.

  /etc/sonar/sonar.conf          system defaults (root edits; shipped by the RPM)
  ~/.config/sonar/sonar.conf     per-user overrides (Edit > Preferences writes this)

The user file only needs the keys you want to change; everything else falls
back to the system file, then to the built-in defaults below.
SONAR_SYSTEM_CONF overrides the system path (used by the tests).
"""

from __future__ import annotations

import configparser
import json
import os
import tempfile
from typing import Dict, List, Optional

SYSTEM_CONF = "/etc/sonar/sonar.conf"

DEFAULTS: Dict[str, Dict[str, str]] = {
    "scan": {
        "threads": "64",
        "timeout_ms": "1000",
        "ping_method": "auto",
        "probe_ports": "80,443,22,445,139,3389,8080,53,21,23",
        "ports": "21,22,23,25,53,80,110,135,139,143,443,445,3389,5900,8080,8443",
        "scan_ports": "yes",
        "resolve_hostnames": "yes",
        "netbios": "yes",
        "show_dead": "no",
    },
    "launchers": {
        "skiff_path": "/usr/bin/skiff",
        "multissh_path": "/usr/bin/multissh-manager",
        "default_user": "",
        "ssh_port": "22",
        "skiff_args": "",
        "skiff_add_site": "yes",
        "multissh_args": "{session_file}",
        "browser_command": "",
    },
}

KEY_HELP = {
    "threads": "Hosts probed in parallel (1-512)",
    "timeout_ms": "Ping / connect timeout per host in milliseconds",
    "ping_method": "auto, icmp, ping or tcp",
    "probe_ports": "Ports tried by the TCP ping fallback",
    "ports": "Ports checked on live hosts (e.g. 22,80,443,8000-8010)",
    "skiff_path": "Skiff executable",
    "multissh_path": "MultiSSH Manager executable",
    "default_user": "User name passed to Skiff / MultiSSH Manager (blank = your login)",
    "ssh_port": "SSH port used for Skiff / MultiSSH Manager entries",
    "skiff_args": "Extra Skiff arguments; {host} {user} {port} are replaced",
    "skiff_add_site": "yes = add a 'Sonar: <ip>' site to Skiff's Site Manager first",
    "multissh_args": "MultiSSH Manager arguments; {session_file} {host} {user} {port}",
    "browser_command": "Command for Open in browser (blank = desktop default); {url}",
}


def config_dir() -> str:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    path = os.path.join(base, "sonar")
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def cache_dir() -> str:
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    path = os.path.join(base, "sonar")
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def system_conf_path() -> str:
    return os.environ.get("SONAR_SYSTEM_CONF", SYSTEM_CONF)


def user_conf_path() -> str:
    return os.path.join(config_dir(), "sonar.conf")


def atomic_write(path: str, text: str) -> None:
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _parser() -> configparser.ConfigParser:
    return configparser.ConfigParser(interpolation=None)


class Config:
    """Merged view: defaults < system file < user file."""

    def __init__(self, system_path: Optional[str] = None, user_path: Optional[str] = None):
        self.system_path = system_path or system_conf_path()
        self.user_path = user_path or user_conf_path()
        self.reload()

    def reload(self):
        self.merged = _parser()
        self.merged.read_dict(DEFAULTS)
        self.system = _parser()
        self.system.read(self.system_path, encoding="utf-8")
        self.user = _parser()
        self.user.read(self.user_path, encoding="utf-8")
        for src in (self.system, self.user):
            for sec in src.sections():
                if not self.merged.has_section(sec):
                    self.merged.add_section(sec)
                for k, v in src.items(sec):
                    self.merged.set(sec, k, v)

    def get(self, section: str, key: str, fallback: str = "") -> str:
        return self.merged.get(section, key, fallback=fallback).strip()

    def getint(self, section: str, key: str, fallback: int = 0) -> int:
        try:
            return int(self.get(section, key, str(fallback)))
        except ValueError:
            return fallback

    def getbool(self, section: str, key: str, fallback: bool = False) -> bool:
        v = self.get(section, key, "yes" if fallback else "no").lower()
        return v in ("1", "yes", "true", "on")

    def origin(self, section: str, key: str) -> str:
        if self.user.has_option(section, key):
            return "user"
        if self.system.has_option(section, key):
            return "system"
        return "default"

    def set_user(self, section: str, key: str, value: str) -> None:
        """Stage a user override (call save_user to write it). Setting a key
        back to the inherited value removes the override."""
        if not self.user.has_section(section):
            self.user.add_section(section)
        inherited = self.system.get(section, key, fallback=DEFAULTS.get(section, {}).get(key, ""))
        if str(value) == inherited.strip():
            self.user.remove_option(section, key)
        else:
            self.user.set(section, key, str(value))
        if not self.merged.has_section(section):
            self.merged.add_section(section)
        self.merged.set(section, key, str(value))

    def save_user(self) -> None:
        import io
        buf = io.StringIO()
        buf.write("# Sonar per-user settings (overrides %s).\n" % self.system_path)
        buf.write("# Written by Edit > Preferences; safe to edit by hand.\n\n")
        for sec in list(self.user.sections()):
            if not self.user.items(sec):
                self.user.remove_section(sec)
        self.user.write(buf)
        atomic_write(self.user_path, buf.getvalue())


# ------------------------------------------------- saved ranges/favourites

def _json_path(name: str) -> str:
    return os.path.join(config_dir(), name)


def _load_list(name: str) -> List[dict]:
    try:
        with open(_json_path(name), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return [d for d in data.get("items", []) if isinstance(d, dict)]
    except (OSError, ValueError, AttributeError):
        return []


def _save_list(name: str, items: List[dict]) -> None:
    atomic_write(_json_path(name), json.dumps({"version": 1, "items": items}, indent=2) + "\n")


def load_ranges() -> List[dict]:
    """[{'name': 'Lab', 'range': '10.1.1.1-254'}, ...]"""
    return _load_list("ranges.json")


def save_ranges(items: List[dict]) -> None:
    _save_list("ranges.json", items)


def load_favorites() -> List[dict]:
    """[{'ip': '10.1.1.5', 'name': 'nas', 'note': ''}, ...]"""
    return _load_list("favorites.json")


def save_favorites(items: List[dict]) -> None:
    _save_list("favorites.json", items)


def load_state() -> dict:
    try:
        with open(_json_path("state.json"), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    atomic_write(_json_path("state.json"), json.dumps(state, indent=2) + "\n")
