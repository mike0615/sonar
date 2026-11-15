# Integration tests

Used to test the release RPMs in fresh Rocky Linux 9 and 10 roots
(chroots unpacked from the official images; podman works the same way).
Nothing here touches a real network.

- `netns-up.sh` / `netns-down.sh` (root): a private test network - bridge
  `br-sonar` 198.18.99.1/29 (RFC 2544 benchmark range) plus four network
  namespaces with fixed MACs (VMware, Raspberry Pi, Google, QEMU OUIs), an
  HTTP server, two TCP listeners and a NetBIOS responder (`nbns_responder.py`).
- `install-test.sh <9|10>` (inside the root, source at /work/src): dnf install,
  `--version` / `--help`, payload and branding checks, unit tests and the
  offscreen GUI smoke test as a non-root user, a scan of the test network,
  the right-click launchers (not installed / stub scripts recording argv /
  real Skiff RPM), then `rpm -e` and a leftover check.
- `launcher_gui.py` drives the installed GUI's Open in Skiff / MultiSSH
  Manager actions with the default /etc/sonar/sonar.conf paths.
- `shot.py` renders docs/screenshot.png from a scan of the test network.
