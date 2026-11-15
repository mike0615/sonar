"""Fixed content for Help > About Sonar."""

from __future__ import annotations

import os

from . import APP_NAME as _APP_NAME
from . import __version__

LOGO_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons", "sonar.svg")

APP_NAME = _APP_NAME
VERSION = __version__
TAGLINE = "Multithreaded IP network scanner for Rocky Linux 9 and 10"
AUTHOR = "Mike Anderson"
COPYRIGHT = "Copyright (c) 2026 Mike Anderson"
LINKS = [
    ("Project page", "https://github.com/mike0615/sonar"),
    ("www.andersoncomputer.net", "https://www.andersoncomputer.net"),
]

LICENSE_NOTICE = (
    "Sonar is free software, released under the MIT License. You may "
    "use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies "
    "of it, provided the copyright notice and permission notice are included in "
    "all copies or substantial portions of the software.\n\n"
    "Sonar is provided \"as is\", without warranty of any kind, express "
    "or implied, including but not limited to the warranties of merchantability, "
    "fitness for a particular purpose and noninfringement. See the MIT License "
    "for more details."
)
