"""Integration: right-click launchers in the installed GUI with the default
/etc/sonar/sonar.conf paths. Usage: launcher_gui.py <stub|real-skiff|absent>"""
import os, sys, time, json, tempfile
os.environ["QT_QPA_PLATFORM"] = "offscreen"
mode = sys.argv[1]
sys.path.insert(0, "/opt/sonar")
from sonar.qtcompat import QApplication
app = QApplication(sys.argv)
from sonar.main_window import MainWindow
w = MainWindow(); w.show(); app.processEvents()
print("config:", w.cfg.system_path, "| skiff_path =", w.cfg.get("launchers", "skiff_path"),
      "| multissh_path =", w.cfg.get("launchers", "multissh_path"))
w.range_edit.setText("127.0.0.1-3"); w.timeout.setValue(300); w.start_scan()
t = time.time()
while w.thread is not None and time.time() - t < 20:
    app.processEvents(); time.sleep(0.02)
w.table.selectRow(0); app.processEvents()
w.update_launchers()
r = w.selected()[0]
print("selected", r.ip, "| Open in Skiff enabled:", w.act_skiff.isEnabled(),
      "| Open in MultiSSH Manager enabled:", w.act_multissh.isEnabled())
log = os.environ.get("SONAR_STUB_LOG", "/tmp/stub.log")
if mode == "absent":
    assert not w.act_skiff.isEnabled() and not w.act_multissh.isEnabled()
    print("PASS greyed out when not installed"); sys.exit(0)
assert w.act_skiff.isEnabled()
for name, act in (("skiff", w.act_skiff), ("multissh-manager", w.act_multissh)):
    if mode == "real-skiff" and name != "skiff":
        continue
    if os.path.exists(log): os.unlink(log)
    act.trigger()
    print("status:", w.status.text())
    if mode == "stub":
        t = time.time()
        while not os.path.exists(log) and time.time() - t < 5: time.sleep(0.05)
        argv = open(log).read().split("\n")
        print("%s argv: %r" % (name, argv))
        if name == "skiff":
            assert argv == ["/usr/bin/skiff"], argv
            sites = json.load(open(os.path.expanduser("~/.config/skiff/sites.json")))["sites"]
            print("skiff site:", {k: sites[0][k] for k in ("name", "host", "port", "username", "auth")})
        else:
            assert argv[0] == "/usr/bin/multissh-manager" and argv[1].endswith("/sonar-127.0.0.1.json"), argv
            data = json.load(open(argv[1]))
            print("multissh session host:", data["root"]["folders"][0]["hosts"][0]["hostname"])
print("PASS", mode)
