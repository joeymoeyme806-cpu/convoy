"""
convoy_extractor.py
A standalone PySide6 GUI for inspecting and extracting .convoy archives.

Usage:
    python convoy_extractor.py [optional_path.convoy]

Requires:
    pip install PySide6
"""

import io
import os
import struct
import sys
import zlib
from pathlib import Path

from PySide6.QtCore import (
    QMimeData, QSortFilterProxyModel, Qt, QThread, Signal,
)
from PySide6.QtGui import (
    QColor, QDragEnterEvent, QDropEvent, QFont, QFontDatabase,
    QIcon, QPalette, QStandardItem, QStandardItemModel,
)
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit,
    QPushButton, QSizePolicy, QSplitter, QStatusBar,
    QTreeView, QVBoxLayout, QWidget,
)

# ── Convoy format constants (must match builder.py) ──────────────────────────
CONVOY_MAGIC = b"CONVOY\x00\x01"

# ── Colour palette (matches convoy's dark terminal aesthetic) ─────────────────
C_BG       = "#0f0f0f"
C_BG2      = "#1a1a1a"
C_BG3      = "#242424"
C_ACCENT   = "#f5c518"
C_FG       = "#e8e8e8"
C_FG_DIM   = "#666666"
C_RED      = "#e05555"
C_GREEN    = "#55c97a"
C_BLUE     = "#5b8fff"
C_BORDER   = "#2e2e2e"


# ─────────────────────────────────────────────────────────────────────────────
# Low-level parser
# ─────────────────────────────────────────────────────────────────────────────

class ConvoyParseError(Exception):
    pass


def parse_convoy(path: Path) -> dict:
    """
    Returns:
        {
          "manifest": dict[str, str],
          "files": list[{"name": str, "size": int, "data": bytes}],
          "compressed_size": int,
          "raw_size": int,
        }
    """
    raw = path.read_bytes()

    if not raw.startswith(CONVOY_MAGIC):
        raise ConvoyParseError("Not a valid .convoy file (bad magic bytes).")

    offset = len(CONVOY_MAGIC)
    (compressed_len,) = struct.unpack_from(">I", raw, offset)
    offset += 4

    compressed = raw[offset: offset + compressed_len]
    if len(compressed) != compressed_len:
        raise ConvoyParseError("Truncated .convoy file.")

    try:
        raw_bytes = zlib.decompress(compressed)
    except zlib.error as e:
        raise ConvoyParseError(f"Decompression failed: {e}")

    buf = io.BytesIO(raw_bytes)
    (file_count,) = struct.unpack(">I", buf.read(4))

    files = []
    for _ in range(file_count):
        (name_len,) = struct.unpack(">H", buf.read(2))
        arc_name    = buf.read(name_len).decode("utf-8", errors="replace")
        (data_len,) = struct.unpack(">I", buf.read(4))
        data        = buf.read(data_len)
        files.append({"name": arc_name, "size": data_len, "data": data})

    # Parse manifest if present
    manifest = {}
    for f in files:
        if f["name"].endswith("MANIFEST"):
            for line in f["data"].decode("utf-8", errors="replace").splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    manifest[k.strip()] = v.strip()
            break

    return {
        "manifest": manifest,
        "files": files,
        "compressed_size": compressed_len,
        "raw_size": len(raw_bytes),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Worker thread (keeps UI responsive for large files)
# ─────────────────────────────────────────────────────────────────────────────

class LoadWorker(QThread):
    done   = Signal(dict)
    failed = Signal(str)

    def __init__(self, path: Path):
        super().__init__()
        self.path = path

    def run(self):
        try:
            result = parse_convoy(self.path)
            self.done.emit(result)
        except Exception as e:
            self.failed.emit(str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def is_text(data: bytes) -> bool:
    """Heuristic: if the first 512 bytes are mostly printable, treat as text."""
    sample = data[:512]
    if not sample:
        return True
    printable = sum(0x20 <= b < 0x7F or b in (0x09, 0x0A, 0x0D) for b in sample)
    return printable / len(sample) > 0.75


def file_icon(name: str) -> str:
    ext = Path(name).suffix.lower()
    return {
        ".py":   "🐍",
        ".pyc":  "⚙",
        ".toml": "⚙",
        ".txt":  "📄",
        ".md":   "📝",
        ".json": "{}",
        ".png":  "🖼",
        ".jpg":  "🖼",
        ".jpeg": "🖼",
        ".gif":  "🖼",
        ".zip":  "📦",
        ".so":   "🔧",
        ".pyd":  "🔧",
        "":      "📁",  # directory marker
    }.get(ext, "·")


# ─────────────────────────────────────────────────────────────────────────────
# Drag-and-drop zone (shown before a file is loaded)
# ─────────────────────────────────────────────────────────────────────────────

class DropZone(QWidget):
    file_dropped = Signal(Path)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumSize(480, 280)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(16)

        icon = QLabel("⬛")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet(f"font-size: 48px; color: {C_ACCENT};")

        title = QLabel("CONVOY EXTRACTOR")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            f"font-size: 20px; font-weight: bold; font-family: Consolas, monospace;"
            f" color: {C_ACCENT}; letter-spacing: 4px;"
        )

        sub = QLabel("drop a .convoy file here  ·  or click Open")
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet(
            f"font-size: 11px; font-family: Consolas, monospace; color: {C_FG_DIM};"
        )

        btn = QPushButton("Open .convoy…")
        btn.setFixedWidth(160)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(self._btn_style())
        btn.clicked.connect(self._browse)

        layout.addWidget(icon)
        layout.addWidget(title)
        layout.addWidget(sub)
        layout.addWidget(btn, alignment=Qt.AlignCenter)

        self.setStyleSheet(
            f"background: {C_BG2}; border: 2px dashed {C_BORDER}; border-radius: 8px;"
        )

    def _btn_style(self):
        return (
            f"QPushButton {{ background: {C_BG3}; color: {C_ACCENT}; border: 1px solid {C_ACCENT};"
            f" border-radius: 4px; padding: 8px 16px; font-family: Consolas, monospace;"
            f" font-size: 11px; }}"
            f"QPushButton:hover {{ background: {C_ACCENT}; color: {C_BG}; }}"
        )

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open .convoy file", "", "Convoy bundles (*.convoy);;All files (*)"
        )
        if path:
            self.file_dropped.emit(Path(path))

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self.setStyleSheet(
                f"background: {C_BG2}; border: 2px dashed {C_ACCENT}; border-radius: 8px;"
            )

    def dragLeaveEvent(self, _):
        self.setStyleSheet(
            f"background: {C_BG2}; border: 2px dashed {C_BORDER}; border-radius: 8px;"
        )

    def dropEvent(self, e: QDropEvent):
        self.setStyleSheet(
            f"background: {C_BG2}; border: 2px dashed {C_BORDER}; border-radius: 8px;"
        )
        for url in e.mimeData().urls():
            p = Path(url.toLocalFile())
            if p.suffix == ".convoy" and p.is_file():
                self.file_dropped.emit(p)
                return
        QMessageBox.warning(self, "Wrong file type", "Please drop a .convoy file.")


# ─────────────────────────────────────────────────────────────────────────────
# Preview pane
# ─────────────────────────────────────────────────────────────────────────────

class PreviewPane(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._header = QLabel("— no file selected —")
        self._header.setStyleSheet(
            f"background: {C_BG3}; color: {C_FG_DIM}; font-family: Consolas, monospace;"
            f" font-size: 10px; padding: 6px 12px; border-bottom: 1px solid {C_BORDER};"
        )
        layout.addWidget(self._header)

        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setStyleSheet(
            f"background: {C_BG}; color: {C_FG}; font-family: Consolas, monospace;"
            f" font-size: 10px; border: none; padding: 8px;"
        )
        self._text.setLineWrapMode(QPlainTextEdit.NoWrap)
        layout.addWidget(self._text)

        self._current_data: bytes | None = None

    def show_file(self, name: str, data: bytes):
        self._current_data = data
        size_str = human_size(len(data))
        self._header.setText(f"  {file_icon(name)}  {name}   [{size_str}]")

        if is_text(data):
            try:
                text = data.decode("utf-8", errors="replace")
            except Exception:
                text = repr(data)
            self._text.setPlainText(text)
        else:
            # Hex dump
            lines = []
            for i in range(0, min(len(data), 4096), 16):
                chunk = data[i:i + 16]
                hex_part  = " ".join(f"{b:02x}" for b in chunk)
                ascii_part = "".join(chr(b) if 0x20 <= b < 0x7F else "." for b in chunk)
                lines.append(f"{i:06x}  {hex_part:<47}  {ascii_part}")
            if len(data) > 4096:
                lines.append(f"\n… {human_size(len(data) - 4096)} more (binary truncated)")
            self._text.setPlainText("\n".join(lines))

    def clear(self):
        self._current_data = None
        self._header.setText("— no file selected —")
        self._text.clear()

    def current_data(self) -> bytes | None:
        return self._current_data


# ─────────────────────────────────────────────────────────────────────────────
# Main window
# ─────────────────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self, initial_path: Path | None = None):
        super().__init__()
        self.setWindowTitle("Convoy Extractor")
        self.resize(1100, 680)
        self.setMinimumSize(700, 480)

        self._parsed: dict | None = None
        self._convoy_path: Path | None = None
        self._worker: LoadWorker | None = None

        self._apply_palette()
        self._build_ui()

        if initial_path:
            self._load(initial_path)

    # ── Palette ───────────────────────────────────────────────────────────────

    def _apply_palette(self):
        pal = QPalette()
        pal.setColor(QPalette.Window,          QColor(C_BG))
        pal.setColor(QPalette.WindowText,      QColor(C_FG))
        pal.setColor(QPalette.Base,            QColor(C_BG2))
        pal.setColor(QPalette.AlternateBase,   QColor(C_BG3))
        pal.setColor(QPalette.Text,            QColor(C_FG))
        pal.setColor(QPalette.Button,          QColor(C_BG3))
        pal.setColor(QPalette.ButtonText,      QColor(C_FG))
        pal.setColor(QPalette.Highlight,       QColor(C_ACCENT))
        pal.setColor(QPalette.HighlightedText, QColor(C_BG))
        self.setPalette(pal)
        self.setStyleSheet(f"QMainWindow {{ background: {C_BG}; }}")

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        vbox = QVBoxLayout(root)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        # ── Toolbar ──────────────────────────────────────────────────────────
        toolbar = QFrame()
        toolbar.setFixedHeight(44)
        toolbar.setStyleSheet(
            f"background: {C_BG2}; border-bottom: 1px solid {C_BORDER};"
        )
        tbox = QHBoxLayout(toolbar)
        tbox.setContentsMargins(12, 0, 12, 0)
        tbox.setSpacing(8)

        logo = QLabel("⬛ CONVOY EXTRACTOR")
        logo.setStyleSheet(
            f"color: {C_ACCENT}; font-family: Consolas, monospace; font-size: 12px;"
            f" font-weight: bold; letter-spacing: 2px;"
        )
        tbox.addWidget(logo)
        tbox.addStretch()

        self._search = QLineEdit()
        self._search.setPlaceholderText("filter files…")
        self._search.setFixedWidth(200)
        self._search.setStyleSheet(
            f"QLineEdit {{ background: {C_BG3}; color: {C_FG}; border: 1px solid {C_BORDER};"
            f" border-radius: 3px; padding: 4px 8px; font-family: Consolas, monospace;"
            f" font-size: 10px; }}"
            f"QLineEdit:focus {{ border-color: {C_ACCENT}; }}"
        )
        tbox.addWidget(self._search)

        for label, slot in [("Open", self._browse_open),
                             ("Extract All", self._extract_all),
                             ("Extract Selected", self._extract_selected)]:
            btn = QPushButton(label)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(self._btn_css())
            btn.clicked.connect(slot)
            tbox.addWidget(btn)
            if label == "Open":
                self._open_btn = btn
            elif label == "Extract All":
                self._extract_all_btn = btn
                btn.setEnabled(False)
            elif label == "Extract Selected":
                self._extract_sel_btn = btn
                btn.setEnabled(False)

        vbox.addWidget(toolbar)

        # ── Content area ─────────────────────────────────────────────────────
        self._stack = QWidget()
        stack_layout = QVBoxLayout(self._stack)
        stack_layout.setContentsMargins(0, 0, 0, 0)

        # Drop zone (shown initially)
        self._drop_zone = DropZone()
        self._drop_zone.file_dropped.connect(self._load)
        stack_layout.addWidget(self._drop_zone, alignment=Qt.AlignCenter)

        # Splitter (shown after load)
        self._splitter = QSplitter(Qt.Horizontal)
        self._splitter.setStyleSheet(
            f"QSplitter::handle {{ background: {C_BORDER}; width: 1px; }}"
        )
        self._splitter.hide()

        # Left: file tree
        left = QWidget()
        left.setStyleSheet(f"background: {C_BG2};")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        # Info bar
        self._info_bar = QLabel()
        self._info_bar.setStyleSheet(
            f"background: {C_BG3}; color: {C_FG_DIM}; font-family: Consolas, monospace;"
            f" font-size: 10px; padding: 5px 12px; border-bottom: 1px solid {C_BORDER};"
        )
        left_layout.addWidget(self._info_bar)

        self._tree = QTreeView()
        self._tree.setHeaderHidden(False)
        self._tree.setRootIsDecorated(True)
        self._tree.setUniformRowHeights(True)
        self._tree.setAlternatingRowColors(True)
        self._tree.setStyleSheet(
            f"QTreeView {{ background: {C_BG2}; alternate-background-color: {C_BG3};"
            f" color: {C_FG}; font-family: Consolas, monospace; font-size: 10px;"
            f" border: none; outline: none; }}"
            f"QTreeView::item:selected {{ background: {C_ACCENT}; color: {C_BG}; }}"
            f"QTreeView::item:hover {{ background: {C_BG3}; }}"
            f"QHeaderView::section {{ background: {C_BG3}; color: {C_FG_DIM};"
            f" font-family: Consolas, monospace; font-size: 10px; border: none;"
            f" padding: 4px 8px; border-bottom: 1px solid {C_BORDER}; }}"
        )
        self._model = QStandardItemModel()
        self._model.setHorizontalHeaderLabels(["Name", "Size", "Type"])
        self._proxy = QSortFilterProxyModel()
        self._proxy.setSourceModel(self._model)
        self._proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self._proxy.setRecursiveFilteringEnabled(True)
        self._proxy.setFilterKeyColumn(0)
        self._tree.setModel(self._proxy)
        self._tree.selectionModel().selectionChanged.connect(self._on_select)
        self._search.textChanged.connect(self._proxy.setFilterFixedString)

        left_layout.addWidget(self._tree)
        self._splitter.addWidget(left)

        # Right: preview
        self._preview = PreviewPane()
        self._splitter.addWidget(self._preview)
        self._splitter.setSizes([380, 680])

        stack_layout.addWidget(self._splitter)
        vbox.addWidget(self._stack, stretch=1)

        # ── Status bar ────────────────────────────────────────────────────────
        self._status = QStatusBar()
        self._status.setStyleSheet(
            f"QStatusBar {{ background: {C_BG3}; color: {C_FG_DIM};"
            f" font-family: Consolas, monospace; font-size: 10px; border-top: 1px solid {C_BORDER}; }}"
        )
        self.setStatusBar(self._status)
        self._status.showMessage("Open a .convoy bundle to begin.")

    # ── Styles ────────────────────────────────────────────────────────────────

    def _btn_css(self, accent=False):
        if accent:
            return (
                f"QPushButton {{ background: {C_ACCENT}; color: {C_BG}; border: none;"
                f" border-radius: 3px; padding: 5px 12px; font-family: Consolas, monospace;"
                f" font-size: 10px; }}"
                f"QPushButton:hover {{ background: #ffd44a; }}"
                f"QPushButton:disabled {{ opacity: 0.4; }}"
            )
        return (
            f"QPushButton {{ background: {C_BG3}; color: {C_ACCENT}; border: 1px solid {C_BORDER};"
            f" border-radius: 3px; padding: 5px 12px; font-family: Consolas, monospace;"
            f" font-size: 10px; }}"
            f"QPushButton:hover {{ border-color: {C_ACCENT}; }}"
            f"QPushButton:disabled {{ color: {C_FG_DIM}; border-color: {C_BG3}; }}"
        )

    # ── Loading ───────────────────────────────────────────────────────────────

    def _browse_open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open .convoy file", "", "Convoy bundles (*.convoy);;All files (*)"
        )
        if path:
            self._load(Path(path))

    def _load(self, path: Path):
        self._status.showMessage(f"Loading {path.name}…")
        self._worker = LoadWorker(path)
        self._convoy_path = path
        self._worker.done.connect(self._on_loaded)
        self._worker.failed.connect(self._on_load_error)
        self._worker.start()

    def _on_loaded(self, result: dict):
        self._parsed = result
        self._populate_tree(result)
        self._drop_zone.hide()
        self._splitter.show()
        self._extract_all_btn.setEnabled(True)
        self._extract_sel_btn.setEnabled(True)
        self.setWindowTitle(f"Convoy Extractor — {self._convoy_path.name}")

        m = result["manifest"]
        comp_ratio = (1 - result["compressed_size"] / max(result["raw_size"], 1)) * 100
        self._status.showMessage(
            f"  {len(result['files'])} files   "
            f"· raw {human_size(result['raw_size'])}  "
            f"→  compressed {human_size(result['compressed_size'])}  "
            f"({comp_ratio:.0f}% saved)  "
            f"· main: {m.get('main', '?')}  "
            f"· built: {m.get('built', '?')}"
        )

        name = self._convoy_path.name if self._convoy_path else "bundle"
        self._info_bar.setText(
            f"  {name}  ·  {len(result['files'])} entries  "
            f"·  convoy v{m.get('convoy_version', '?')}"
        )

    def _on_load_error(self, msg: str):
        self._status.showMessage(f"Error: {msg}")
        QMessageBox.critical(self, "Failed to open .convoy", msg)

    # ── Tree population ───────────────────────────────────────────────────────

    def _populate_tree(self, result: dict):
        self._model.removeRows(0, self._model.rowCount())

        # Build a virtual folder tree
        folders: dict[str, QStandardItem] = {}

        def get_folder(parts: tuple) -> QStandardItem:
            if not parts:
                return self._model.invisibleRootItem()
            if parts in folders:
                return folders[parts]
            parent = get_folder(parts[:-1])
            item = QStandardItem(f"📁  {parts[-1]}")
            item.setEditable(False)
            item.setData(None, Qt.UserRole)  # None = folder
            item.setForeground(QColor(C_ACCENT))
            size_item = QStandardItem("")
            size_item.setEditable(False)
            type_item = QStandardItem("folder")
            type_item.setEditable(False)
            type_item.setForeground(QColor(C_FG_DIM))
            parent.appendRow([item, size_item, type_item])
            folders[parts] = item
            return item

        for f in result["files"]:
            parts = Path(f["name"]).parts
            folder_parts = parts[:-1]
            file_name = parts[-1]

            parent = get_folder(folder_parts)

            icon = file_icon(file_name)
            name_item = QStandardItem(f"{icon}  {file_name}")
            name_item.setEditable(False)
            name_item.setData(f, Qt.UserRole)  # store file dict

            size_item = QStandardItem(human_size(f["size"]))
            size_item.setEditable(False)
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            size_item.setForeground(QColor(C_FG_DIM))

            ext = Path(file_name).suffix.lstrip(".") or "—"
            type_item = QStandardItem(ext)
            type_item.setEditable(False)
            type_item.setForeground(QColor(C_FG_DIM))

            parent.appendRow([name_item, size_item, type_item])

        self._tree.expandAll()
        self._tree.header().resizeSection(0, 280)
        self._tree.header().resizeSection(1, 70)

    # ── Selection → preview ───────────────────────────────────────────────────

    def _on_select(self, selected, _deselected):
        indexes = selected.indexes()
        if not indexes:
            self._preview.clear()
            self._extract_sel_btn.setEnabled(False)
            return
        src_idx = self._proxy.mapToSource(indexes[0])
        item = self._model.itemFromIndex(src_idx)
        if item is None:
            return
        file_data = item.data(Qt.UserRole)
        if file_data is None:
            # folder
            self._preview.clear()
            self._extract_sel_btn.setEnabled(False)
        else:
            self._preview.show_file(file_data["name"], file_data["data"])
            self._extract_sel_btn.setEnabled(True)

    # ── Extraction ────────────────────────────────────────────────────────────

    def _extract_all(self):
        if not self._parsed:
            return
        out_dir = QFileDialog.getExistingDirectory(self, "Extract all files to…")
        if not out_dir:
            return
        out = Path(out_dir)
        count = 0
        for f in self._parsed["files"]:
            dest = out / f["name"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(f["data"])
            count += 1
        self._status.showMessage(f"Extracted {count} files to {out}")
        QMessageBox.information(self, "Done", f"Extracted {count} files to:\n{out}")

    def _extract_selected(self):
        indexes = self._tree.selectionModel().selectedIndexes()
        if not indexes:
            return
        src_idx = self._proxy.mapToSource(indexes[0])
        item = self._model.itemFromIndex(src_idx)
        if item is None:
            return
        file_data = item.data(Qt.UserRole)
        if file_data is None:
            return  # folder selected

        default_name = Path(file_data["name"]).name
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Save file as…", default_name
        )
        if not save_path:
            return
        Path(save_path).write_bytes(file_data["data"])
        self._status.showMessage(f"Saved → {save_path}")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Convoy Extractor")

    # Use monospace system font as fallback
    font = QFont("Consolas", 10)
    app.setFont(font)

    initial = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    win = MainWindow(initial_path=initial)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
