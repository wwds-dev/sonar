# Third-party notices: SONAR

SONAR itself is MIT-licensed (`LICENSE`, copyright 2026 wwds-dev), as are its two bundled
modules `sonar/macro` and `sonar/playmaker`. This application also contains the following
third-party software. It is provided under the licences named here; their texts are in this
folder.

## Qt and PySide6 (LGPL-3.0)

SONAR's window is built with **PySide6 / Shiboken6 6.11.2** (Qt for Python) and the **Qt 6**
libraries it ships (QtCore, QtGui, QtWidgets, QtNetwork, QtSvg, QtDBus, QtOpenGL and others).
These are used under the **GNU Lesser General Public License v3.0** (`LGPL-3.0.txt`, which
builds on `GPL-3.0.txt`). Copyright belongs to The Qt Company Ltd and other contributors.

- The Qt libraries are **dynamically linked** and sit as separate files under
  `Contents/Frameworks/PySide6/Qt/lib/`. You may replace them with your own build of the same
  Qt version. This is an ad-hoc-signed bundle, so after replacing a library re-sign it
  (`codesign --force --deep --sign - SONAR.app`).
- SONAR is not modified Qt: it does not change PySide6 or Qt.
- **Source code** for the exact versions used is available from the Qt project:
  <https://code.qt.io/cgit/pyside/pyside-setup.git> (PySide6, tag `v6.11.2`) and
  <https://download.qt.io/official_releases/> (Qt). The packages are also on PyPI:
  <https://pypi.org/project/PySide6/6.11.2/>. The full SONAR source is at
  <https://github.com/wwds-dev/sonar>.
- Nothing in SONAR's MIT licence restricts reverse engineering of the application for the
  purpose of debugging modifications to these libraries.
- **Qt Virtual Keyboard is not included.** It is licensed GPL-3.0 or commercially rather than
  LGPL, SONAR does not use it, and the build removes it.

## Python (PSF-2.0)

The interpreter and standard library are bundled by PyInstaller, under the Python Software
Foundation License Version 2 (<https://docs.python.org/3/license.html>).

## PyInstaller bootloader (GPL-2.0-or-later with the bootloader exception)

The launcher that starts SONAR is PyInstaller's bootloader, licensed GPL-2.0-or-later with a
special exception that permits it to be used in programs under any licence
(<https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt>).

## anthropic SDK (MIT), optional

If present in a build, the `anthropic` Python SDK is MIT-licensed.
