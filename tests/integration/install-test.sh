#!/bin/bash
# Runs inside a fresh Rocky root: install, smoke, unit, netns scan, launchers, removal.
V=$1; RPM=/work/src/out/sonar-1.0.0-1.el$V.noarch.rpm
cat /etc/rocky-release
echo "=== dnf install $RPM"
dnf -y install $RPM > /tmp/dnf.log 2>&1; echo "dnf rc=$?"
sed -n '/^Installing:/,/^Transaction Summary/p' /tmp/dnf.log | grep -E '^ (sonar|python3-qt5-base|python3-pyqt6-base|hwdata|iproute|iputils|qt[56]-qtsvg) ' | awk '{print "  installed:", $1, $3}'
rpm -q sonar
echo "=== sonar --version / --help"; sonar --version; sonar --help | head -3
echo "=== payload"; rpm -ql sonar | grep -vE "/opt/sonar/sonar/.*\.py$|\.pyc$"; echo "  .pyc files shipped: $(rpm -ql sonar | grep -c "\.pyc$")"
rpm -qc sonar; grep -E '^(skiff_path|multissh_path)' /etc/sonar/sonar.conf
echo "=== branding grep (lrn|softperfect) over payload"; F=$(rpm -ql sonar | while read f; do [ -f "$f" ] && echo "$f"; done); grep -Iil -E 'lrn|softperfect' $F; echo "grep rc=$? (1 = clean)"
dnf -y -q install desktop-file-utils dejavu-sans-fonts procps-ng >/dev/null 2>&1; desktop-file-validate /usr/share/applications/sonar.desktop && echo "desktop-file-validate OK"
id tester >/dev/null 2>&1 || useradd -m tester
grep -q filesrv01 /etc/hosts || printf '198.18.99.2 filesrv01.lab\n198.18.99.3 picam.lab\n' >> /etc/hosts
mkdir -p /tmp/ut && cp -r /work/src/tests /work/src/HELP.md /work/src/packaging /tmp/ut/ && ln -sfn /opt/sonar/sonar /tmp/ut/sonar && chown -R tester /tmp/ut
mkdir -p /tmp/msrc && cp -r /work/test/msrc/multissh_manager /tmp/msrc/ && chmod -R a+rX /tmp/msrc
T="runuser -u tester -- env HOME=/home/tester QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1"
echo "=== unit tests as non-root user against installed /opt/sonar"
cd /tmp/ut && $T MULTISSH_SRC=/tmp/msrc python3 -m unittest discover -s tests -t . 2>&1 | grep -E 'argv|parsed|^Ran|^OK|FAIL|Error' ; cd /
echo "=== ping method as tester / as root"
$T python3 -c "import sys; sys.path.insert(0,'/opt/sonar'); from sonar.probe import Pinger; print('  tester:', Pinger().method)"
python3 -B -c "import sys; sys.path.insert(0,'/opt/sonar'); from sonar.probe import Pinger; print('  root:', Pinger().method)"
echo "=== root runs the real launcher (must not write __pycache__ into /opt/sonar)"
touch /tmp/marker; sleep 1; QT_QPA_PLATFORM=offscreen timeout 4 sonar; find /opt/sonar -newer /tmp/marker -name "*.pyc" | wc -l | sed "s/^/  new .pyc files after root run: /"
echo "=== offscreen GUI smoke (tests/smoke_offscreen.py, SONAR_ROOT=/opt/sonar) as tester"
cd /tmp/ut && $T SONAR_ROOT=/opt/sonar timeout 90 python3 tests/smoke_offscreen.py; echo "rc=$?"; cd /
echo "=== real launcher, headless 5 s"
$T timeout 5 sonar --range 127.0.0.1; echo "rc=$? (124 = GUI still running after 5 s)"
echo "=== netns test network 198.18.99.0/29 scan as tester (MAC, vendor, NetBIOS, ports)"
$T python3 - <<'PY'
import sys; sys.path.insert(0, "/opt/sonar")
from sonar.scanner import Scanner, ScanOptions
from sonar.iprange import parse_range
got = {}
Scanner(ScanOptions(timeout_ms=600, ports=[22, 80, 443, 445])).run(parse_range("198.18.99.0/29"), lambda r: got.__setitem__(r.ip, r))
for ip in sorted(got): r = got[ip]; print("  %-12s %-6s %-14s %-17s %-24s %-9s %s" % (ip, r.method, r.hostname, r.mac, r.vendor, r.netbios, r.ports_text()))
ok = (got["198.18.99.2"].vendor == "VMware, Inc." and got["198.18.99.2"].netbios == "FILESRV01" and got["198.18.99.2"].open_ports == [80]
      and got["198.18.99.3"].vendor.startswith("Raspberry Pi") and got["198.18.99.3"].open_ports == [22]
      and got["198.18.99.4"].open_ports == [443] and got["198.18.99.2"].hostname == "filesrv01.lab" and "198.18.99.6" not in got)
print("PASS netns scan" if ok else "FAIL netns scan"); sys.exit(0 if ok else 1)
PY
echo "=== launchers: absent"
$T python3 /work/test/launcher_gui.py absent 2>&1 | grep -v '^QStandardPaths'
echo "=== launchers: stub /usr/bin/skiff + /usr/bin/multissh-manager recording argv"
for n in skiff multissh-manager; do printf '#!/bin/sh\nout=${SONAR_STUB_LOG:-/tmp/stub.log}\nprintf "%%s" "$0" > $out.tmp\nfor a in "$@"; do printf "\\n%%s" "$a" >> $out.tmp; done\nmv $out.tmp $out\n' > /usr/bin/$n; chmod 755 /usr/bin/$n; done
$T SONAR_STUB_LOG=/tmp/stub-tester.log python3 /work/test/launcher_gui.py stub 2>&1 | grep -v '^QStandardPaths'
rm -f /usr/bin/skiff /usr/bin/multissh-manager
echo "=== launchers: real Skiff 1.1.0 RPM"
dnf -y -q install /work/test/skiff-1.1.0-1.el$V.noarch.rpm >/dev/null 2>&1; rpm -q skiff
rm -rf /home/tester/.config/skiff
$T python3 /work/test/launcher_gui.py real-skiff 2>&1 | grep -v '^QStandardPaths'
sleep 3; echo "skiff process (pgrep): $(pgrep -u tester -a -f '/usr/bin/skiff' | head -1)"
$T python3 -B -c "import sys; sys.path.insert(0,'/opt/skiff'); from skiff import config; print('  skiff load_sites():', [(s['name'], s['host'], s['port'], s['username']) for s in config.load_sites()])"
pkill -u tester -f /usr/bin/skiff; sleep 1
dnf -y -q remove skiff >/dev/null 2>&1; rpm -q skiff
echo "=== rpm -e sonar"
rpm -e sonar; echo "rpm -e rc=$?"; rpm -q sonar
echo "  leftovers (none expected):"; ls -d /opt/sonar /usr/bin/sonar /etc/sonar /usr/share/applications/sonar.desktop /usr/share/icons/hicolor/scalable/apps/sonar.svg /usr/share/pixmaps/sonar.svg 2>&1 | sed 's/^/  /'
echo "INSTALL-TEST DONE el$V"
