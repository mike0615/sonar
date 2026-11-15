"""Sonar entry point."""

from __future__ import annotations

import os
import sys

from . import APP_ID, APP_NAME, __version__


def _parse_cli(argv):
    """Handle --help/--version/--range before Qt starts; pass Qt options through."""
    import argparse

    parser = argparse.ArgumentParser(
        prog=APP_ID,
        description=APP_NAME + " - multithreaded IP network scanner.",
        epilog="Master configuration: /etc/sonar/sonar.conf, overridden per user by "
        "~/.config/sonar/sonar.conf. Standard Qt options (e.g. -platform offscreen) "
        "are passed through.",
    )
    parser.add_argument("--version", action="version", version=APP_NAME + " " + __version__)
    parser.add_argument("--range", metavar="RANGE", help="pre-fill the Range box (does not start a scan)")
    args, rest = parser.parse_known_args(argv[1:])
    return args, [argv[0]] + rest


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    args, qt_argv = _parse_cli(argv)
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")

    from .qtcompat import QApplication, QIcon, QtWidgets, exec_
    from .about_config import LOGO_FILE

    app = QApplication(qt_argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setDesktopFileName(APP_ID)
    if "Fusion" in QtWidgets.QStyleFactory.keys():
        app.setStyle("Fusion")
    icon = QIcon(LOGO_FILE) if os.path.isfile(LOGO_FILE) else QIcon()
    if not icon.isNull():
        app.setWindowIcon(icon)

    from .main_window import MainWindow

    win = MainWindow()
    if args.range:
        win.range_edit.setText(args.range)
    win.show()
    return exec_(app)


if __name__ == "__main__":
    sys.exit(main())
