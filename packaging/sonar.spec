%global debug_package %{nil}

Name:           sonar
Version:        1.0.0
Release:        1%{?dist}
Summary:        Multithreaded IP network scanner for Rocky Linux 9 and 10
License:        MIT
URL:            https://github.com/mike0615/sonar
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python3
BuildRequires:  desktop-file-utils

Requires:       python3
# MAC vendor names: IEEE OUI list in /usr/share/hwdata/oui.txt (BaseOS).
Requires:       hwdata
# `ip` for local interfaces / subnet, `ping` for Ping and the ping fallback.
Requires:       iproute
Requires:       iputils

# Qt bindings (AppStream, no EPEL needed):
#   EL9  -> PyQt5 (python3-qt5-base)
#   EL10 -> PyQt6 (python3-pyqt6-base); EL10 has no PyQt5.
%if 0%{?rhel} >= 10
Requires:       python3-pyqt6-base
Recommends:     qt6-qtsvg
Recommends:     qt6-qtwayland
%else
Requires:       python3-qt5-base
Recommends:     qt5-qtsvg
Recommends:     qt5-qtwayland
%endif

%description
Sonar is a multithreaded IP network scanner for Rocky Linux 9 and 10.

Enter an IP range or CIDR block and Sonar pings every address in parallel
(unprivileged ICMP, the system ping, or a TCP connect probe - never root),
then shows reverse DNS names, MAC addresses and vendors, NetBIOS names,
response times and open TCP ports. Results can be sorted, filtered and
exported to CSV, TXT, HTML or XML. Ranges and favourite hosts can be saved,
and a right-click opens a host in a browser, Skiff or MultiSSH Manager.

The master configuration file is /etc/sonar/sonar.conf; each user can
override it in ~/.config/sonar/sonar.conf.

%prep
%setup -q -n %{name}-%{version}
find . -name '__pycache__' -prune -exec rm -rf {} +
find . -name '*.py[co]' -delete

%build
# pure Python

%install
rm -rf %{buildroot}
install -d %{buildroot}/opt/sonar
cp -a sonar %{buildroot}/opt/sonar/
# Ship byte-code so nothing is written under /opt/sonar at run time and
# rpm -e leaves no __pycache__ behind.
python3 -m compileall -q -s %{buildroot} -p / %{buildroot}/opt/sonar/sonar
python3 -O -m compileall -q -s %{buildroot} -p / %{buildroot}/opt/sonar/sonar
install -d %{buildroot}%{_bindir}
install -m 0755 bin/sonar %{buildroot}%{_bindir}/sonar
install -d %{buildroot}%{_sysconfdir}/sonar
install -m 0644 packaging/sonar.conf %{buildroot}%{_sysconfdir}/sonar/sonar.conf
install -d %{buildroot}%{_datadir}/applications
install -m 0644 packaging/sonar.desktop %{buildroot}%{_datadir}/applications/sonar.desktop
install -d %{buildroot}%{_datadir}/icons/hicolor/scalable/apps
install -m 0644 sonar/icons/sonar.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/sonar.svg
install -d %{buildroot}%{_datadir}/pixmaps
install -m 0644 sonar/icons/sonar.svg %{buildroot}%{_datadir}/pixmaps/sonar.svg

%check
desktop-file-validate %{buildroot}%{_datadir}/applications/sonar.desktop
# Network tests use 127.0.0.0/8 only.
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -t . -v
find . -name '__pycache__' -prune -exec rm -rf {} +

%post
if [ -x /usr/bin/update-desktop-database ]; then
    update-desktop-database -q %{_datadir}/applications || true
fi
if [ -x /usr/bin/gtk-update-icon-cache ]; then
    gtk-update-icon-cache -q %{_datadir}/icons/hicolor 2>/dev/null || true
fi

%postun
if [ -x /usr/bin/update-desktop-database ]; then
    update-desktop-database -q %{_datadir}/applications || true
fi
if [ -x /usr/bin/gtk-update-icon-cache ]; then
    gtk-update-icon-cache -q %{_datadir}/icons/hicolor 2>/dev/null || true
fi

%files
%license LICENSE
%doc README.md HELP.md
%dir %{_sysconfdir}/sonar
%config(noreplace) %{_sysconfdir}/sonar/sonar.conf
/opt/sonar/
%{_bindir}/sonar
%{_datadir}/applications/sonar.desktop
%{_datadir}/icons/hicolor/scalable/apps/sonar.svg
%{_datadir}/pixmaps/sonar.svg

%changelog
* Sat Nov 14 2026 Mike Anderson <mike@andersoncomputer.us> - 1.0.0-1
- Initial release for Rocky Linux 9 (PyQt5) and 10 (PyQt6)
- IP range / CIDR / wildcard input, multithreaded ping sweep with
  configurable threads and timeout, progress bar, Start/Stop
- Unprivileged ICMP, system ping or TCP connect probe; never needs root
- Reverse DNS, MAC address and vendor (hwdata OUI list), NetBIOS name and
  workgroup, response time, TCP port scan of a configurable port list
- Sortable, filterable results with an Alive only toggle
- Export to CSV, TXT, HTML and XML; saved ranges and favourites
- Right-click: copy, ping, open in browser, Open in Skiff, Open in
  MultiSSH Manager (paths in /etc/sonar/sonar.conf, per-user override)
- Help (F1), About page and Preferences dialog
