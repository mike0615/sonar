"""PyQt5 (Rocky 9) / PyQt6 (Rocky 10) compatibility shim.

Everything Sonar needs from Qt is imported from here. Enum members are
looked up with qenum(), which works with PyQt5's flat enums and PyQt6's
scoped enums (Qt.AlignLeft vs Qt.AlignmentFlag.AlignLeft).
"""

from __future__ import annotations

try:
    from PyQt5 import QtCore, QtGui, QtWidgets  # type: ignore
    from PyQt5.QtWidgets import QAction  # type: ignore
    QT_VERSION = 5
except ImportError:  # Rocky 10
    from PyQt6 import QtCore, QtGui, QtWidgets  # type: ignore
    from PyQt6.QtGui import QAction  # type: ignore
    QT_VERSION = 6

Qt = QtCore.Qt
QT_VERSION_STR = QtCore.QT_VERSION_STR
QAbstractTableModel = QtCore.QAbstractTableModel
QModelIndex = QtCore.QModelIndex
QObject = QtCore.QObject
QProcess = QtCore.QProcess
QSortFilterProxyModel = QtCore.QSortFilterProxyModel
QThread = QtCore.QThread
QTimer = QtCore.QTimer
QUrl = QtCore.QUrl
QRegularExpression = QtCore.QRegularExpression
pyqtSignal = QtCore.pyqtSignal

QDesktopServices = QtGui.QDesktopServices
QFont = QtGui.QFont
QFontDatabase = QtGui.QFontDatabase
QGuiApplication = QtGui.QGuiApplication
QIcon = QtGui.QIcon
QKeySequence = QtGui.QKeySequence
QColor = QtGui.QColor
QBrush = QtGui.QBrush

_W = QtWidgets
QAbstractItemView = _W.QAbstractItemView
QApplication = _W.QApplication
QCheckBox = _W.QCheckBox
QComboBox = _W.QComboBox
QDialog = _W.QDialog
QDialogButtonBox = _W.QDialogButtonBox
QFileDialog = _W.QFileDialog
QFormLayout = _W.QFormLayout
QGroupBox = _W.QGroupBox
QHBoxLayout = _W.QHBoxLayout
QHeaderView = _W.QHeaderView
QInputDialog = _W.QInputDialog
QLabel = _W.QLabel
QLayout = _W.QLayout
QLineEdit = _W.QLineEdit
QListWidget = _W.QListWidget
QListWidgetItem = _W.QListWidgetItem
QMainWindow = _W.QMainWindow
QMenu = _W.QMenu
QMessageBox = _W.QMessageBox
QPlainTextEdit = _W.QPlainTextEdit
QProgressBar = _W.QProgressBar
QPushButton = _W.QPushButton
QSpinBox = _W.QSpinBox
QStatusBar = _W.QStatusBar
QTableView = _W.QTableView
QTabWidget = _W.QTabWidget
QTextBrowser = _W.QTextBrowser
QToolBar = _W.QToolBar
QVBoxLayout = _W.QVBoxLayout
QWidget = _W.QWidget

_SCOPES = {
    "Qt": ["ItemDataRole", "AlignmentFlag", "SortOrder", "ContextMenuPolicy",
           "Orientation", "CaseSensitivity", "ItemFlag", "ToolButtonStyle",
           "WindowModality", "CheckState", "MatchFlag", "TextInteractionFlag"],
    "QAbstractItemView": ["SelectionBehavior", "SelectionMode", "EditTrigger"],
    "QHeaderView": ["ResizeMode"],
    "QDialogButtonBox": ["StandardButton", "ButtonRole"],
    "QMessageBox": ["StandardButton", "Icon"],
    "QLineEdit": ["EchoMode"],
    "QKeySequence": ["StandardKey"],
    "QProcess": ["ProcessChannelMode", "ProcessState", "ExitStatus"],
    "QFont": ["StyleHint", "Weight"],
    "QFontDatabase": ["SystemFont"],
    "QPlainTextEdit": ["LineWrapMode"],
    "QDialog": ["DialogCode"],
    "QLayout": ["SizeConstraint"],
}


def qenum(owner, name: str):
    """Return enum member `name` from `owner` for either PyQt5 or PyQt6."""
    member = getattr(owner, name, None)
    if member is not None:
        return member
    for scope in _SCOPES.get(owner.__name__, []):
        group = getattr(owner, scope, None)
        if group is not None and hasattr(group, name):
            return getattr(group, name)
    raise AttributeError("%s.%s" % (owner.__name__, name))


def exec_(obj, *args):
    """QDialog/QMenu/QApplication exec for Qt5 (exec_) and Qt6 (exec)."""
    fn = getattr(obj, "exec", None) or getattr(obj, "exec_")
    return fn(*args)


def flags(*members):
    out = members[0]
    for m in members[1:]:
        out = out | m
    return out
