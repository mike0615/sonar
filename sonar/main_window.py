"""Sonar main window."""

from __future__ import annotations

import ipaddress
import os
import re
import shutil
import subprocess
import time
from typing import List, Optional

from . import APP_NAME, __version__, config, probe
from .dialogs import ListManager, PingDialog, PreferencesDialog
from .export import FORMATS, export
from .help_dialogs import AboutDialog, HelpDialog
from .iprange import RangeError, parse_ports, parse_range
from .launchers import Launcher
from .models import ResultsModel, ResultsProxy
from .qtcompat import (
    QAbstractItemView,
    QAction,
    QApplication,
    QCheckBox,
    QDesktopServices,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QIcon,
    QInputDialog,
    QKeySequence,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableView,
    QThread,
    QUrl,
    QVBoxLayout,
    QWidget,
    Qt,
    exec_,
    pyqtSignal,
    qenum,
)
from .scanner import HostResult, ScanOptions, Scanner


class ScanThread(QThread):
    result = pyqtSignal(object)
    progress = pyqtSignal(int, int)
    done = pyqtSignal(int, float, str)

    def __init__(self, addresses: List[str], options: ScanOptions, parent=None):
        super().__init__(parent)
        self.addresses = addresses
        self.scanner = Scanner(options)

    def run(self):
        t0 = time.monotonic()
        try:
            alive = self.scanner.run(self.addresses, self.result.emit, self.progress.emit)
            err = ""
        except Exception as e:  # pragma: no cover - shown to the user
            alive, err = 0, "%s: %s" % (type(e).__name__, e)
        self.done.emit(alive, time.monotonic() - t0, err)

    def stop(self):
        self.scanner.stop()


def local_subnet() -> str:
    """First non-loopback IPv4 network of this computer, e.g. 10.0.0.0/24."""
    exe = shutil.which("ip")
    if not exe:
        return ""
    try:
        txt = subprocess.run([exe, "-o", "-4", "addr", "show", "scope", "global"],
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5).stdout.decode()
    except (OSError, subprocess.TimeoutExpired):
        return ""
    for m in re.finditer(r"inet\s+([\d.]+/\d+)", txt):
        net = ipaddress.IPv4Interface(m.group(1)).network
        if net.prefixlen < 16:
            net = ipaddress.IPv4Interface("%s/24" % m.group(1).split("/")[0]).network
        return str(net)
    return ""


class MainWindow(QMainWindow):
    def __init__(self, cfg: Optional[config.Config] = None):
        super().__init__()
        self.cfg = cfg or config.Config()
        self.launcher = Launcher(self.cfg)
        self.thread: Optional[ScanThread] = None
        self._help_dlg = None
        self._children = []
        self.setWindowTitle("%s %s" % (APP_NAME, __version__))
        self.resize(1100, 640)

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.setContentsMargins(6, 6, 6, 6)

        top = QHBoxLayout()
        top.addWidget(QLabel("Range:"))
        self.range_edit = QLineEdit()
        self.range_edit.setPlaceholderText("10.0.0.1-254, 10.0.0.0/24 or 10.0.0.*")
        self.range_edit.returnPressed.connect(self.start_scan)
        top.addWidget(self.range_edit, 3)
        top.addWidget(QLabel("Threads:"))
        self.threads = QSpinBox()
        self.threads.setRange(1, 512)
        top.addWidget(self.threads)
        top.addWidget(QLabel("Timeout:"))
        self.timeout = QSpinBox()
        self.timeout.setRange(50, 30000)
        self.timeout.setSingleStep(100)
        self.timeout.setSuffix(" ms")
        top.addWidget(self.timeout)
        self.start_btn = QPushButton("Start")
        self.start_btn.clicked.connect(self.start_scan)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self.stop_scan)
        self.stop_btn.setEnabled(False)
        top.addWidget(self.start_btn)
        top.addWidget(self.stop_btn)
        lay.addLayout(top)

        mid = QHBoxLayout()
        mid.addWidget(QLabel("Ports:"))
        self.ports_edit = QLineEdit()
        mid.addWidget(self.ports_edit, 3)
        mid.addWidget(QLabel("Filter:"))
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("text in any column")
        self.filter_edit.setClearButtonEnabled(True)
        mid.addWidget(self.filter_edit, 2)
        self.alive_only = QCheckBox("Alive only")
        self.alive_only.setChecked(True)
        mid.addWidget(self.alive_only)
        self.show_dead = QCheckBox("Show dead hosts")
        mid.addWidget(self.show_dead)
        lay.addLayout(mid)

        self.model = ResultsModel(self)
        self.proxy = ResultsProxy(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.set_alive_only(True)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, qenum(Qt, "AscendingOrder"))
        self.table.setSelectionBehavior(qenum(QAbstractItemView, "SelectRows"))
        self.table.setSelectionMode(qenum(QAbstractItemView, "ExtendedSelection"))
        self.table.setEditTriggers(qenum(QAbstractItemView, "NoEditTriggers"))
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(22)
        hh = self.table.horizontalHeader()
        hh.setStretchLastSection(True)
        hh.setSectionResizeMode(qenum(QHeaderView, "Interactive"))
        for col, w in enumerate((110, 70, 150, 130, 170, 110, 90, 120)):
            self.table.setColumnWidth(col, w)
        self.table.setContextMenuPolicy(qenum(Qt, "CustomContextMenu"))
        self.table.customContextMenuRequested.connect(self.context_menu)
        lay.addWidget(self.table, 1)
        self.setCentralWidget(central)

        self.filter_edit.textChanged.connect(self.proxy.set_text)
        self.alive_only.toggled.connect(self.proxy.set_alive_only)

        self.status = QLabel("Ready")
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(260)
        self.progress.setTextVisible(True)
        self.statusBar().addWidget(self.status, 1)
        self.statusBar().addPermanentWidget(self.progress)

        self._build_actions()
        self._build_menus()
        self.apply_config()
        state = config.load_state()
        self.range_edit.setText(state.get("last_range", ""))

    # ------------------------------------------------------------ setup
    def _act(self, text, slot, shortcut=None, menu=None):
        a = QAction(text, self)
        a.triggered.connect(lambda _checked=False: slot())
        if shortcut:
            if isinstance(shortcut, (list, tuple)):
                a.setShortcuts([QKeySequence(s) for s in shortcut])
            else:
                a.setShortcut(QKeySequence(shortcut))
        if menu is not None:
            menu.addAction(a)
        return a

    def _build_actions(self):
        self.act_start = self._act("&Start scan", self.start_scan, ["F5", "Ctrl+Return"])
        self.act_stop = self._act("S&top scan", self.stop_scan, "Esc")
        self.act_stop.setEnabled(False)
        self.act_copy = self._act("&Copy IP address", self.copy_ips, "Ctrl+C")
        self.act_copy_row = self._act("Copy &row", self.copy_rows)
        self.act_ping = self._act("&Ping", self.ping_selected)
        self.act_http = self._act("Open in browser (&http)", lambda: self.open_browser("http"))
        self.act_https = self._act("Open in browser (http&s)", lambda: self.open_browser("https"))
        self.act_skiff = self._act("Open in S&kiff", self.open_skiff)
        self.act_multissh = self._act("Open in &MultiSSH Manager", self.open_multissh)
        self.act_fav = self._act("Add to &Favourites", self.add_favorite, "Ctrl+D")
        self.act_help = self._act("Sonar &Help", self.show_help, "F1")
        self.act_about = self._act("&About Sonar", self.show_about)
        for a in (self.act_start, self.act_stop, self.act_copy, self.act_fav, self.act_help):
            self.addAction(a)

    def _build_menus(self):
        mb = self.menuBar()
        m = mb.addMenu("&File")
        self._act("&Export…", self.export_dialog, "Ctrl+E", m)
        m.addSeparator()
        self._act("&Quit", self.close, "Ctrl+Q", m)

        m = mb.addMenu("&Edit")
        m.addAction(self.act_copy)
        m.addAction(self.act_copy_row)
        self._act("Select &all", self.table.selectAll, "Ctrl+A", m)
        self._act("&Filter results", lambda: self.filter_edit.setFocus(), "Ctrl+F", m)
        m.addSeparator()
        self._act("&Preferences…", self.preferences, "Ctrl+,", m)

        m = mb.addMenu("&Scan")
        m.addAction(self.act_start)
        m.addAction(self.act_stop)
        self._act("Use &local subnet", self.use_local_subnet, "Ctrl+L", m)
        self._act("&Clear results", self.model.clear, None, m)

        self.ranges_menu = mb.addMenu("&Ranges")
        self.ranges_menu.aboutToShow.connect(self._fill_ranges_menu)
        self.favs_menu = mb.addMenu("Fa&vourites")
        self.favs_menu.aboutToShow.connect(self._fill_favs_menu)
        self._fill_ranges_menu()
        self._fill_favs_menu()

        m = mb.addMenu("&Help")
        m.addAction(self.act_help)
        m.addSeparator()
        m.addAction(self.act_about)

    def apply_config(self):
        c = self.cfg
        self.threads.setValue(c.getint("scan", "threads", 64))
        self.timeout.setValue(c.getint("scan", "timeout_ms", 1000))
        self.ports_edit.setText(c.get("scan", "ports"))
        self.show_dead.setChecked(c.getbool("scan", "show_dead", False))
        self.update_launchers()

    def update_launchers(self):
        skiff, mssh = self.launcher.skiff_exe(), self.launcher.multissh_exe()
        self.act_skiff.setEnabled(bool(skiff))
        self.act_skiff.setToolTip(skiff or "Skiff not found - set skiff_path in Preferences")
        self.act_multissh.setEnabled(bool(mssh))
        self.act_multissh.setToolTip(mssh or "MultiSSH Manager not found - set multissh_path in Preferences")

    # ------------------------------------------------------------ scan
    def options(self) -> ScanOptions:
        c = self.cfg
        return ScanOptions(
            threads=self.threads.value(), timeout_ms=self.timeout.value(),
            ping_method=c.get("scan", "ping_method") or "auto",
            probe_ports=parse_ports(c.get("scan", "probe_ports")) or list(probe.DEFAULT_PROBE_PORTS),
            resolve_hostnames=c.getbool("scan", "resolve_hostnames", True),
            netbios=c.getbool("scan", "netbios", True),
            scan_ports=c.getbool("scan", "scan_ports", True),
            ports=parse_ports(self.ports_edit.text()),
            show_dead=self.show_dead.isChecked())

    def start_scan(self, addresses: Optional[List[str]] = None):
        if self.thread is not None:
            return
        try:
            if not addresses:
                addresses = parse_range(self.range_edit.text())
            opts = self.options()
        except (RangeError, ValueError) as e:
            QMessageBox.warning(self, APP_NAME, str(e))
            return
        state = config.load_state()
        state["last_range"] = self.range_edit.text().strip()
        try:
            config.save_state(state)
        except OSError:
            pass
        self.model.clear()
        self.progress.setRange(0, len(addresses))
        self.progress.setValue(0)
        self.thread = ScanThread(addresses, opts, self)
        self.thread.result.connect(self.model.add)
        self.thread.progress.connect(self._on_progress)
        self.thread.done.connect(self._on_done)
        self._set_running(True)
        self.status.setText("Scanning %d address(es) with %d threads (ping: %s)…"
                            % (len(addresses), opts.threads, self.thread.scanner.pinger.method))
        self.thread.start()

    def stop_scan(self):
        if self.thread is not None:
            self.thread.stop()
            self.status.setText("Stopping…")

    def _set_running(self, on: bool):
        self.start_btn.setEnabled(not on)
        self.act_start.setEnabled(not on)
        self.stop_btn.setEnabled(on)
        self.act_stop.setEnabled(on)
        self.range_edit.setEnabled(not on)

    def _on_progress(self, done, total):
        self.progress.setValue(done)
        self.progress.setFormat("%d / %d" % (done, total))

    def _on_done(self, alive, secs, err):
        t = self.thread
        self.thread = None
        if t is not None:
            t.wait(2000)
        self._set_running(False)
        stopped = t is not None and t.scanner.stop_event.is_set()
        msg = "%s: %d host(s) up, %d scanned in %.1f s (ping: %s)" % (
            "Stopped" if stopped else "Done", alive, self.progress.value(), secs,
            t.scanner.pinger.method if t else "?")
        if err:
            msg += " - error: " + err
        self.status.setText(msg)

    # ------------------------------------------------------------ selection
    def selected(self) -> List[HostResult]:
        rows = sorted({i.row() for i in self.table.selectionModel().selectedRows()})
        if not rows:
            cur = self.table.currentIndex()
            rows = [cur.row()] if cur.isValid() else []
        return [self.proxy.result_at(r) for r in rows]

    def context_menu(self, pos):
        idx = self.table.indexAt(pos)
        if idx.isValid() and not self.table.selectionModel().isRowSelected(idx.row(), idx.parent()):
            self.table.selectRow(idx.row())
        has = bool(self.selected())
        self.update_launchers()
        m = QMenu(self)
        for a in (self.act_copy, self.act_copy_row, None, self.act_ping, self.act_http, self.act_https,
                  None, self.act_skiff, self.act_multissh, None, self.act_fav):
            if a is None:
                m.addSeparator()
            else:
                m.addAction(a)
        for a in (self.act_copy, self.act_copy_row, self.act_ping, self.act_http, self.act_https, self.act_fav):
            a.setEnabled(has)
        if not has:
            self.act_skiff.setEnabled(False)
            self.act_multissh.setEnabled(False)
        exec_(m, self.table.viewport().mapToGlobal(pos))
        for a in (self.act_copy, self.act_copy_row, self.act_ping, self.act_http, self.act_https, self.act_fav):
            a.setEnabled(True)
        self.update_launchers()

    def copy_ips(self):
        sel = self.selected()
        if sel:
            QApplication.clipboard().setText("\n".join(r.ip for r in sel))
            self.status.setText("Copied %d address(es)" % len(sel))

    def copy_rows(self):
        from .export import row
        sel = self.selected()
        if sel:
            QApplication.clipboard().setText("\n".join("\t".join(row(r)) for r in sel))

    def ping_selected(self):
        for r in self.selected()[:5]:
            d = PingDialog(r.ip, self)
            d.show()
            self._children.append(d)

    def open_browser(self, scheme: str):
        for r in self.selected()[:5]:
            url = "%s://%s/" % (scheme, r.ip)
            argv = self.launcher.browser_argv(url)
            if argv:
                try:
                    subprocess.Popen(argv, start_new_session=True)
                except OSError as e:
                    QMessageBox.warning(self, APP_NAME, "Could not run %s: %s" % (argv[0], e))
            else:
                QDesktopServices.openUrl(QUrl(url))

    def _launch(self, fn, label):
        sel = self.selected()
        if not sel:
            return
        r = sel[0]
        try:
            msg = fn(r.ip, None, r.hostname or r.netbios or "")
            self.status.setText(msg)
        except Exception as e:
            QMessageBox.warning(self, APP_NAME, "%s: %s" % (label, e))

    def open_skiff(self):
        self._launch(self.launcher.open_skiff, "Open in Skiff")

    def open_multissh(self):
        self._launch(self.launcher.open_multissh, "Open in MultiSSH Manager")

    # ------------------------------------------------------------ ranges / favourites
    def _fill_ranges_menu(self):
        m = self.ranges_menu
        m.clear()
        self._act("&Save current range…", self.save_range, "Ctrl+B", m)
        self._act("&Manage ranges…", self.manage_ranges, None, m)
        items = config.load_ranges()
        if items:
            m.addSeparator()
        for it in items:
            a = QAction("%s   (%s)" % (it.get("name") or it.get("range"), it.get("range")), m)
            a.triggered.connect(lambda _c=False, rng=it.get("range", ""): self.range_edit.setText(rng))
            m.addAction(a)

    def save_range(self):
        rng = self.range_edit.text().strip()
        try:
            parse_range(rng)
        except RangeError as e:
            QMessageBox.warning(self, APP_NAME, str(e))
            return
        name, ok = QInputDialog.getText(self, "Save range", "Name for %s:" % rng, text=rng)
        if not ok:
            return
        items = [i for i in config.load_ranges() if i.get("range") != rng]
        items.append({"name": name.strip() or rng, "range": rng})
        config.save_ranges(items)
        self.status.setText("Saved range '%s'" % (name.strip() or rng))

    def manage_ranges(self):
        d = ListManager("Saved ranges", config.load_ranges(),
                        lambda i: "%s   (%s)" % (i.get("name"), i.get("range")), "name", self)
        if exec_(d):
            config.save_ranges(d.items)

    def _fill_favs_menu(self):
        m = self.favs_menu
        m.clear()
        m.addAction(self.act_fav)
        self._act("&Scan favourites", self.scan_favorites, None, m)
        self._act("&Manage favourites…", self.manage_favorites, None, m)
        items = config.load_favorites()
        if items:
            m.addSeparator()
        for it in items:
            a = QAction("%s   %s" % (it.get("ip"), it.get("name") or ""), m)
            a.triggered.connect(lambda _c=False, ip=it.get("ip", ""): self.range_edit.setText(ip))
            m.addAction(a)

    def add_favorite(self):
        sel = self.selected()
        if not sel:
            return
        items = config.load_favorites()
        known = {i.get("ip") for i in items}
        added = 0
        for r in sel:
            if r.ip not in known:
                items.append({"ip": r.ip, "name": r.hostname or r.netbios or "", "mac": r.mac})
                added += 1
        config.save_favorites(items)
        self.status.setText("Added %d favourite(s)" % added)

    def scan_favorites(self):
        ips = [i.get("ip") for i in config.load_favorites() if i.get("ip")]
        if not ips:
            QMessageBox.information(self, APP_NAME, "No favourites yet. Right-click a host > Add to Favourites.")
            return
        self.range_edit.setText(", ".join(ips))
        self.start_scan()

    def manage_favorites(self):
        d = ListManager("Favourites", config.load_favorites(),
                        lambda i: "%s   %s" % (i.get("ip"), i.get("name") or ""), "name", self)
        if exec_(d):
            config.save_favorites(d.items)

    # ------------------------------------------------------------ misc
    def use_local_subnet(self):
        net = local_subnet()
        if net:
            self.range_edit.setText(net)
        else:
            self.status.setText("No IPv4 network found on this computer")

    def export_dialog(self):
        rows = self.proxy.visible_results()
        if not rows:
            QMessageBox.information(self, APP_NAME, "Nothing to export yet.")
            return
        filters = ";;".join(FORMATS.values())
        path, chosen = QFileDialog.getSaveFileName(self, "Export results",
                                                   os.path.expanduser("~/sonar-results.csv"), filters)
        if not path:
            return
        fmt = next((k for k, v in FORMATS.items() if v == chosen), "csv")
        if "." not in os.path.basename(path):
            path += "." + fmt
        else:
            ext = path.rsplit(".", 1)[-1].lower()
            fmt = ext if ext in FORMATS or ext == "htm" else fmt
        try:
            export(rows, path, fmt)
            self.status.setText("Exported %d row(s) to %s" % (len(rows), path))
        except (OSError, ValueError) as e:
            QMessageBox.critical(self, APP_NAME, "Export failed: %s" % e)

    def preferences(self):
        d = PreferencesDialog(self.cfg, self)
        if exec_(d):
            self.apply_config()
            self.status.setText("Preferences saved to %s" % self.cfg.user_path)

    def show_help(self):
        if self._help_dlg is None:
            self._help_dlg = HelpDialog(self)
        self._help_dlg.show()
        self._help_dlg.raise_()

    def show_about(self):
        exec_(AboutDialog(self))

    def closeEvent(self, ev):
        if self.thread is not None:
            self.thread.stop()
            self.thread.wait(5000)
        super().closeEvent(ev)
