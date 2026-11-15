"""Qt table model + sort/filter proxy for scan results."""

from __future__ import annotations

import ipaddress
from typing import List

from .export import COLUMNS, row
from .qtcompat import (
    QAbstractTableModel,
    QBrush,
    QColor,
    QModelIndex,
    QSortFilterProxyModel,
    Qt,
    qenum,
)
from .scanner import HostResult

DISPLAY = qenum(Qt, "DisplayRole")
SORT = qenum(Qt, "UserRole")
FG = qenum(Qt, "ForegroundRole")
TOOLTIP = qenum(Qt, "ToolTipRole")
HORIZONTAL = qenum(Qt, "Horizontal")


class ResultsModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.results: List[HostResult] = []
        self._index = {}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.results)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section, orientation, role=DISPLAY):
        if orientation == HORIZONTAL and role == DISPLAY:
            return COLUMNS[section][1]
        return None

    def data(self, index, role=DISPLAY):
        if not index.isValid():
            return None
        r = self.results[index.row()]
        col = index.column()
        if role == DISPLAY:
            return row(r)[col]
        if role == SORT:
            key = COLUMNS[col][0]
            if key == "ip":
                return int(ipaddress.IPv4Address(r.ip))
            if key == "rtt":
                return r.rtt_ms if r.rtt_ms is not None else 1e9
            if key == "open_ports":
                return len(r.open_ports)
            return row(r)[col].lower()
        if role == FG and not r.alive:
            return QBrush(QColor("#888888"))
        if role == TOOLTIP and COLUMNS[col][0] == "ip":
            return "Ping method: %s\nScanned: %s" % (r.method, r.scanned_at)
        return None

    def add(self, r: HostResult):
        if r.ip in self._index:
            i = self._index[r.ip]
            self.results[i] = r
            self.dataChanged.emit(self.index(i, 0), self.index(i, len(COLUMNS) - 1))
            return
        n = len(self.results)
        self.beginInsertRows(QModelIndex(), n, n)
        self.results.append(r)
        self._index[r.ip] = n
        self.endInsertRows()

    def clear(self):
        self.beginResetModel()
        self.results = []
        self._index = {}
        self.endResetModel()


class ResultsProxy(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.text = ""
        self.alive_only = False
        self.setSortRole(SORT)

    def set_text(self, text: str):
        self.text = text.strip().lower()
        self.invalidateFilter()

    def set_alive_only(self, on: bool):
        self.alive_only = bool(on)
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        r = self.sourceModel().results[source_row]
        if self.alive_only and not r.alive:
            return False
        if self.text:
            return any(self.text in c.lower() for c in row(r))
        return True

    def result_at(self, proxy_row: int) -> HostResult:
        src = self.mapToSource(self.index(proxy_row, 0))
        return self.sourceModel().results[src.row()]

    def visible_results(self) -> List[HostResult]:
        return [self.result_at(i) for i in range(self.rowCount())]
