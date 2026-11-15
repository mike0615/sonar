#!/usr/bin/env python3
"""Headless GUI smoke test (QT_QPA_PLATFORM=offscreen): main window, a real
loopback scan, filter/alive toggle, context menu launcher state, export,
Preferences, Help and About. Optional: SONAR_SCREENSHOT=/path.png."""
import os
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
d = tempfile.mkdtemp(prefix="sonar-smoke-")
os.environ["XDG_CONFIG_HOME"] = os.path.join(d, "config")
os.environ["XDG_CACHE_HOME"] = os.path.join(d, "cache")
ROOT = os.environ.get("SONAR_ROOT") or os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from helpers import Listener  # noqa: E402
from sonar import about_config  # noqa: E402
from sonar.help_content import HELP_TOPICS  # noqa: E402
from sonar.help_dialogs import AboutDialog, HelpDialog  # noqa: E402
from sonar.qtcompat import QApplication, QT_VERSION, QT_VERSION_STR  # noqa: E402


def pump(app, cond, secs=20):
    t0 = time.time()
    while not cond() and time.time() - t0 < secs:
        app.processEvents()
        time.sleep(0.02)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    from sonar.main_window import MainWindow
    from sonar.dialogs import PreferencesDialog
    win = MainWindow()
    win.show()
    app.processEvents()
    print("QT_VERSION", QT_VERSION, QT_VERSION_STR, "| title", win.windowTitle())
    menus = {a.text().replace("&", ""): a for a in win.menuBar().actions()}
    print("menus", list(menus))
    for m in ("File", "Edit", "Scan", "Ranges", "Favourites", "Help"):
        assert m in menus, m
    help_items = [a.text().replace("&", "") for a in menus["Help"].menu().actions() if a.text()]
    assert help_items == ["Sonar Help", "About Sonar"], help_items
    assert win.act_help.shortcut().toString() == "F1"

    lst = Listener()
    win.range_edit.setText("127.0.0.1-30")
    win.ports_edit.setText("%d,1" % lst.port)
    win.timeout.setValue(400)
    win.threads.setValue(16)
    win.start_scan()
    assert win.thread is not None and not win.start_btn.isEnabled()
    pump(app, lambda: win.thread is None)
    print("scan:", win.status.text())
    assert win.thread is None and win.proxy.rowCount() == 30, win.proxy.rowCount()
    assert win.progress.value() == 30
    first = win.proxy.result_at(0)
    assert first.ip == "127.0.0.1" and lst.port in first.open_ports, (first.ip, first.open_ports)
    win.table.sortByColumn(0, __import__("sonar.qtcompat", fromlist=["Qt"]).qenum(
        __import__("sonar.qtcompat", fromlist=["Qt"]).Qt, "DescendingOrder"))
    assert win.proxy.result_at(0).ip == "127.0.0.30", win.proxy.result_at(0).ip  # numeric sort
    win.filter_edit.setText("127.0.0.1")
    app.processEvents()
    print("filter '127.0.0.1' ->", win.proxy.rowCount(), "rows")
    assert win.proxy.rowCount() == 11  # .1 and .10-.19
    win.filter_edit.setText("")
    print("launchers: skiff", win.act_skiff.isEnabled(), "| multissh", win.act_multissh.isEnabled(),
          "| skiff exe", win.launcher.skiff_exe(), "| multissh exe", win.launcher.multissh_exe())

    from sonar.export import export
    for fmt in ("csv", "txt", "html", "xml"):
        p = os.path.join(d, "out." + fmt)
        export(win.proxy.visible_results(), p)
        print("export", fmt, os.path.getsize(p), "bytes")

    shot = os.environ.get("SONAR_SCREENSHOT")
    if shot:
        win.sortByColumn = None
        win.table.sortByColumn(0, __import__("sonar.qtcompat", fromlist=["Qt"]).qenum(
            __import__("sonar.qtcompat", fromlist=["Qt"]).Qt, "AscendingOrder"))
        win.range_edit.setText("127.0.0.1-30")
        app.processEvents()
        win.grab().save(shot)
        print("screenshot", shot)

    pd = PreferencesDialog(win.cfg, win)
    pd.show()
    app.processEvents()
    pd.default_user.setText("smoketest")
    pd.save()
    assert "default_user = smoketest" in open(win.cfg.user_path).read()
    print("preferences saved to", win.cfg.user_path)

    win.act_help.trigger()
    app.processEvents()
    hd = win._help_dlg
    assert isinstance(hd, HelpDialog) and hd.isVisible()
    text = hd.browser.toPlainText()
    for heading, _ in HELP_TOPICS:
        assert heading in text, heading
    print("help_dialog OK", len(HELP_TOPICS), "topics")
    ad = AboutDialog(win)
    ad.show()
    app.processEvents()
    assert ad.version.text() == "Version " + about_config.VERSION
    assert ad.author.text() == "Author: Mike Anderson"
    logo = ad.logo.pixmap()
    print("about_dialog OK |", ad.version.text(), "| logo", "yes" if logo is not None and not logo.isNull() else "no")
    if shot:
        ad.grab().save(shot.replace(".png", "-about.png"))
    ad.close()
    win.close()
    lst.close()
    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
