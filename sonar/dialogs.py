"""Preferences, list manager and ping output dialogs."""

from __future__ import annotations

import shutil
from typing import Callable, List

from .config import Config
from .iprange import RangeError, parse_ports
from .launchers import resolve
from .qtcompat import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFont,
    QFontDatabase,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QProcess,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    Qt,
    qenum,
)


class PreferencesDialog(QDialog):
    """Edits ~/.config/sonar/sonar.conf. Values equal to the system file are
    not written, so later changes to /etc/sonar/sonar.conf still apply."""

    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("Preferences")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        lay.addWidget(tabs)

        # --- Scan tab
        scan = QWidget()
        f = QFormLayout(scan)
        self.threads = QSpinBox()
        self.threads.setRange(1, 512)
        self.threads.setValue(cfg.getint("scan", "threads", 64))
        self.timeout = QSpinBox()
        self.timeout.setRange(50, 30000)
        self.timeout.setSingleStep(100)
        self.timeout.setSuffix(" ms")
        self.timeout.setValue(cfg.getint("scan", "timeout_ms", 1000))
        self.method = QComboBox()
        self.method.addItems(["auto", "icmp", "ping", "tcp"])
        self.method.setCurrentText(cfg.get("scan", "ping_method") or "auto")
        self.ports = QLineEdit(cfg.get("scan", "ports"))
        self.probe_ports = QLineEdit(cfg.get("scan", "probe_ports"))
        self.scan_ports = QCheckBox("Scan ports on live hosts")
        self.scan_ports.setChecked(cfg.getbool("scan", "scan_ports", True))
        self.resolve = QCheckBox("Resolve host names (reverse DNS)")
        self.resolve.setChecked(cfg.getbool("scan", "resolve_hostnames", True))
        self.netbios = QCheckBox("Query NetBIOS names (UDP 137)")
        self.netbios.setChecked(cfg.getbool("scan", "netbios", True))
        self.show_dead = QCheckBox("Show hosts that don't respond")
        self.show_dead.setChecked(cfg.getbool("scan", "show_dead", False))
        f.addRow("Threads:", self.threads)
        f.addRow("Timeout:", self.timeout)
        f.addRow("Ping method:", self.method)
        f.addRow("Ports to scan:", self.ports)
        f.addRow("TCP ping ports:", self.probe_ports)
        for w in (self.scan_ports, self.resolve, self.netbios, self.show_dead):
            f.addRow("", w)
        tabs.addTab(scan, "Scan")

        # --- Launchers tab
        lw = QWidget()
        g = QFormLayout(lw)
        self.skiff_path, self.skiff_state = self._path_row(g, "Skiff:", cfg.get("launchers", "skiff_path"), "skiff")
        self.multissh_path, self.multissh_state = self._path_row(
            g, "MultiSSH Manager:", cfg.get("launchers", "multissh_path"), "multissh-manager")
        self.default_user = QLineEdit(cfg.get("launchers", "default_user"))
        self.default_user.setPlaceholderText("blank = your login name")
        self.ssh_port = QSpinBox()
        self.ssh_port.setRange(1, 65535)
        self.ssh_port.setValue(cfg.getint("launchers", "ssh_port", 22))
        self.skiff_add = QCheckBox("Add a 'Sonar: <ip>' site to Skiff's Site Manager")
        self.skiff_add.setChecked(cfg.getbool("launchers", "skiff_add_site", True))
        self.skiff_args = QLineEdit(cfg.get("launchers", "skiff_args"))
        self.skiff_args.setPlaceholderText("{host} {user} {port}")
        self.multissh_args = QLineEdit(cfg.get("launchers", "multissh_args"))
        self.browser = QLineEdit(cfg.get("launchers", "browser_command"))
        self.browser.setPlaceholderText("blank = desktop default, e.g. firefox {url}")
        g.addRow("Default user:", self.default_user)
        g.addRow("SSH port:", self.ssh_port)
        g.addRow("", self.skiff_add)
        g.addRow("Skiff arguments:", self.skiff_args)
        g.addRow("MultiSSH arguments:", self.multissh_args)
        g.addRow("Browser command:", self.browser)
        note = QLabel("Saved to %s\nSystem defaults: %s" % (cfg.user_path, cfg.system_path))
        note.setEnabled(False)
        g.addRow(note)
        tabs.addTab(lw, "Launchers")

        box = QDialogButtonBox(qenum(QDialogButtonBox, "Save") | qenum(QDialogButtonBox, "Cancel"))
        box.accepted.connect(self.save)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

    def _path_row(self, form, label, value, name):
        edit = QLineEdit(value)
        browse = QPushButton("Browse…")
        state = QLabel()
        row = QHBoxLayout()
        row.addWidget(edit, 1)
        row.addWidget(browse)
        form.addRow(label, row)
        form.addRow("", state)

        def refresh():
            exe = resolve(edit.text(), name)
            state.setText(("found: %s" % exe) if exe else "not found - menu entry will be greyed out")

        def pick():
            path, _ = QFileDialog.getOpenFileName(self, "Choose %s" % name, edit.text() or "/usr/bin")
            if path:
                edit.setText(path)
        edit.textChanged.connect(refresh)
        browse.clicked.connect(pick)
        refresh()
        return edit, state

    def values(self):
        return {
            ("scan", "threads"): str(self.threads.value()),
            ("scan", "timeout_ms"): str(self.timeout.value()),
            ("scan", "ping_method"): self.method.currentText(),
            ("scan", "ports"): self.ports.text().strip(),
            ("scan", "probe_ports"): self.probe_ports.text().strip(),
            ("scan", "scan_ports"): "yes" if self.scan_ports.isChecked() else "no",
            ("scan", "resolve_hostnames"): "yes" if self.resolve.isChecked() else "no",
            ("scan", "netbios"): "yes" if self.netbios.isChecked() else "no",
            ("scan", "show_dead"): "yes" if self.show_dead.isChecked() else "no",
            ("launchers", "skiff_path"): self.skiff_path.text().strip(),
            ("launchers", "multissh_path"): self.multissh_path.text().strip(),
            ("launchers", "default_user"): self.default_user.text().strip(),
            ("launchers", "ssh_port"): str(self.ssh_port.value()),
            ("launchers", "skiff_add_site"): "yes" if self.skiff_add.isChecked() else "no",
            ("launchers", "skiff_args"): self.skiff_args.text().strip(),
            ("launchers", "multissh_args"): self.multissh_args.text().strip(),
            ("launchers", "browser_command"): self.browser.text().strip(),
        }

    def save(self):
        try:
            parse_ports(self.ports.text())
            parse_ports(self.probe_ports.text())
        except (RangeError, ValueError) as e:
            QMessageBox.warning(self, "Preferences", "Port list: %s" % e)
            return
        for (sec, key), val in self.values().items():
            self.cfg.set_user(sec, key, val)
        try:
            self.cfg.save_user()
        except OSError as e:
            QMessageBox.critical(self, "Preferences", "Could not save %s:\n%s" % (self.cfg.user_path, e))
            return
        self.cfg.reload()
        self.accept()


class ListManager(QDialog):
    """Rename / delete entries of a saved list (ranges or favourites)."""

    def __init__(self, title: str, items: List[dict], label: Callable[[dict], str],
                 name_key: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(460, 340)
        self.items = [dict(i) for i in items]
        self.label = label
        self.name_key = name_key
        lay = QHBoxLayout(self)
        self.list = QListWidget()
        lay.addWidget(self.list, 1)
        side = QVBoxLayout()
        for text, fn in (("Rename…", self.rename), ("Delete", self.delete),
                         ("Move up", lambda: self.move(-1)), ("Move down", lambda: self.move(1))):
            b = QPushButton(text)
            b.clicked.connect(fn)
            side.addWidget(b)
        side.addStretch(1)
        box = QDialogButtonBox(qenum(QDialogButtonBox, "Ok") | qenum(QDialogButtonBox, "Cancel"))
        box.setOrientation(qenum(Qt, "Vertical"))
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        side.addWidget(box)
        lay.addLayout(side)
        self.refresh()

    def refresh(self, select=0):
        self.list.clear()
        for it in self.items:
            self.list.addItem(self.label(it))
        if self.items:
            self.list.setCurrentRow(max(0, min(select, len(self.items) - 1)))

    def rename(self):
        i = self.list.currentRow()
        if i < 0:
            return
        text, ok = QInputDialog.getText(self, "Rename", "Name:", text=self.items[i].get(self.name_key, ""))
        if ok:
            self.items[i][self.name_key] = text.strip()
            self.refresh(i)

    def delete(self):
        i = self.list.currentRow()
        if i >= 0:
            del self.items[i]
            self.refresh(i)

    def move(self, d):
        i = self.list.currentRow()
        j = i + d
        if 0 <= i < len(self.items) and 0 <= j < len(self.items):
            self.items[i], self.items[j] = self.items[j], self.items[i]
            self.refresh(j)


class PingDialog(QDialog):
    """Runs `ping -c 4 -n <ip>` and streams the output."""

    def __init__(self, ip: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ping %s" % ip)
        self.resize(620, 320)
        lay = QVBoxLayout(self)
        self.out = QPlainTextEdit()
        self.out.setReadOnly(True)
        self.out.setFont(QFontDatabase.systemFont(qenum(QFontDatabase, "FixedFont")))
        lay.addWidget(self.out)
        box = QDialogButtonBox(qenum(QDialogButtonBox, "Close"))
        box.rejected.connect(self.close)
        lay.addWidget(box)
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(qenum(QProcess, "MergedChannels"))
        self.proc.readyReadStandardOutput.connect(self._read)
        self.proc.finished.connect(lambda *a: self.out.appendPlainText("\n[finished]"))
        exe = shutil.which("ping")
        if exe:
            self.out.appendPlainText("$ ping -c 4 -n %s" % ip)
            self.proc.start(exe, ["-c", "4", "-n", ip])
        else:
            self.out.appendPlainText("ping is not installed (dnf install iputils)")

    def _read(self):
        self.out.insertPlainText(bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace"))

    def closeEvent(self, ev):
        if self.proc.state() != qenum(QProcess, "NotRunning"):
            self.proc.kill()
            self.proc.waitForFinished(1000)
        super().closeEvent(ev)
