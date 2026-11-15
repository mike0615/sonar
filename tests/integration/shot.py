"""Render README screenshot: scan of the private netns test network 198.18.99.0/29."""
import os, sys, time, tempfile
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
d = tempfile.mkdtemp(); os.environ["XDG_CONFIG_HOME"] = d
sys.path.insert(0, os.environ.get("SONAR_ROOT", "/work/src"))
from sonar.qtcompat import QApplication
app = QApplication(sys.argv); app.setStyle("Fusion")
from sonar.main_window import MainWindow
w = MainWindow(); w.resize(1100, 330); w.show(); app.processEvents()
w.range_edit.setText("198.18.99.0/29"); w.timeout.setValue(500); w.threads.setValue(32)
w.ports_edit.setText("21,22,23,80,139,443,445,3389,8080")
w.start_scan()
t = time.time()
while w.thread is not None and time.time() - t < 30:
    app.processEvents(); time.sleep(0.02)
w.table.clearSelection(); w.threads.clearFocus(); w.table.setFocus(); app.processEvents()
for r in w.proxy.visible_results(): print(r)
w.grab().save(sys.argv[1]); print("saved", sys.argv[1])
