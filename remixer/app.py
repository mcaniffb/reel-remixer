"""Reel Remixer desktop app (PySide6)."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QButtonGroup, QComboBox, QFileDialog, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QProgressBar, QPushButton, QRadioButton, QSizePolicy, QVBoxLayout, QWidget,
)

from remixer import engine

APP_NAME = "Reel Remixer"
APP_VERSION = "1.0.0"

STYLE = """
* { font-size: 13px; }
QMainWindow, #root { background: #F6F4F0; }
QLabel { color: #2A2723; }
#title { font-size: 22px; font-weight: 700; color: #1E1B18; }
#subtitle { color: #6B655D; }
#card { background: #FFFFFF; border: 1px solid #E4DFD7; border-radius: 12px; }
#cardTitle { font-size: 14px; font-weight: 700; }
#cardHint { color: #8A8379; font-size: 12px; }
#sectionLabel { color: #6B655D; font-size: 12px; font-weight: 600; }
QListWidget {
    background: #FBFAF8; border: 1.5px dashed #D6CFC4; border-radius: 8px;
    padding: 4px; color: #2A2723; outline: none;
}
QListWidget[dragHover="true"] { border-color: #D2683A; background: #FDF3EE; }
QListWidget::item { padding: 7px 6px; border-radius: 6px; }
QListWidget::item:selected { background: #F3E3DA; color: #1E1B18; }
QPushButton {
    background: #FFFFFF; border: 1px solid #D6CFC4; border-radius: 7px;
    padding: 6px 12px; color: #2A2723;
}
QPushButton:hover { background: #F3EFE9; }
QPushButton:disabled { color: #B5AEA4; background: #F6F4F0; }
QPushButton#primary {
    background: #D2683A; border: none; color: #FFFFFF; font-weight: 700;
    padding: 10px 22px; font-size: 14px;
}
QPushButton#primary:hover { background: #BC5A2F; }
QPushButton#primary:disabled { background: #E7B9A3; color: #FFFFFF; }
QPushButton#link { border: none; background: transparent; color: #8A8379; padding: 2px 4px; }
QPushButton#link:hover { color: #D2683A; }
QLineEdit, QComboBox {
    background: #FFFFFF; border: 1px solid #D6CFC4; border-radius: 7px;
    padding: 6px 8px; color: #2A2723; min-height: 18px;
}
QComboBox QAbstractItemView { background: #FFFFFF; color: #2A2723; selection-background-color: #F3E3DA; }
QRadioButton { color: #2A2723; spacing: 6px; }
QProgressBar {
    background: #EAE5DD; border: none; border-radius: 4px; height: 8px; max-height: 8px;
}
QProgressBar::chunk { background: #D2683A; border-radius: 4px; }
#status { color: #6B655D; }
#count { color: #D2683A; font-weight: 700; }
"""


class ClipList(QListWidget):
    """A drop zone that holds clips in order, relabels itself, and accepts files or folders."""
    changed = Signal()

    def __init__(self, letter: str, placeholder: str):
        super().__init__()
        self.letter = letter
        self.placeholder = placeholder
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setMinimumHeight(190)
        self.model().rowsMoved.connect(lambda *a: self._relabel())
        QShortcut(QKeySequence.Delete, self, activated=self.remove_selected)
        QShortcut(QKeySequence(Qt.Key_Backspace), self, activated=self.remove_selected)

    # ---- data
    def paths(self) -> list[Path]:
        return [Path(self.item(i).data(Qt.UserRole)) for i in range(self.count())]

    def add_paths(self, paths) -> int:
        existing = {str(p) for p in self.paths()}
        added = 0
        for p in paths:
            p = Path(p)
            if p.is_dir():
                added += self.add_paths(sorted(c for c in p.iterdir() if engine.is_video(c)))
                continue
            if engine.is_video(p) and str(p) not in existing:
                it = QListWidgetItem()
                it.setData(Qt.UserRole, str(p))
                it.setToolTip(str(p))
                self.addItem(it)
                existing.add(str(p))
                added += 1
        self._relabel()
        return added

    def remove_selected(self):
        for it in self.selectedItems():
            self.takeItem(self.row(it))
        self._relabel()

    def clear_all(self):
        self.clear()
        self._relabel()

    def _relabel(self):
        for i in range(self.count()):
            it = self.item(i)
            it.setText(f"{self.letter}{i + 1}   {Path(it.data(Qt.UserRole)).name}")
        self.viewport().update()
        self.changed.emit()

    # ---- empty-state text
    def paintEvent(self, e):
        super().paintEvent(e)
        if self.count() == 0:
            from PySide6.QtGui import QPainter, QColor
            p = QPainter(self.viewport())
            p.setPen(QColor("#A39C92"))
            p.drawText(self.viewport().rect(), Qt.AlignCenter, self.placeholder)

    # ---- drag and drop from Finder / Explorer
    def _set_hover(self, on: bool):
        self.setProperty("dragHover", on)
        self.style().unpolish(self); self.style().polish(self)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            self._set_hover(True); e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)

    def dragLeaveEvent(self, e):
        self._set_hover(False)
        super().dragLeaveEvent(e)

    def dropEvent(self, e):
        self._set_hover(False)
        if e.mimeData().hasUrls():
            files = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
            self.add_paths(files)
            e.acceptProposedAction()
        else:
            super().dropEvent(e)
            self._relabel()


class Worker(QObject):
    progress = Signal(float, str)
    finished = Signal(list)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, job: engine.Job):
        super().__init__()
        self.job = job

    def run(self):
        try:
            out = self.job.run(lambda f, m: self.progress.emit(f, m))
            self.finished.emit([str(p) for p in out])
        except engine.Cancelled:
            self.cancelled.emit()
        except Exception as ex:  # surface anything to the user instead of crashing
            self.failed.emit(str(ex))


def _card(number: str, title: str, hint: str, clip_list: ClipList) -> QFrame:
    card = QFrame(objectName="card")
    v = QVBoxLayout(card)
    v.setContentsMargins(14, 14, 14, 12)
    v.setSpacing(8)
    head = QLabel(f"{number}  {title}", objectName="cardTitle")
    sub = QLabel(hint, objectName="cardHint")
    v.addWidget(head)
    v.addWidget(sub)
    v.addWidget(clip_list, 1)
    row = QHBoxLayout()
    add = QPushButton("Add clips…")
    clear = QPushButton("Clear", objectName="link")
    row.addWidget(add)
    row.addStretch(1)
    row.addWidget(clear)
    v.addLayout(row)
    add.clicked.connect(lambda: _pick_files(card, clip_list, title))
    clear.clicked.connect(clip_list.clear_all)
    return card


def _pick_files(parent, clip_list: ClipList, title: str):
    exts = " ".join(f"*{e}" for e in sorted(engine.VIDEO_EXTS))
    files, _ = QFileDialog.getOpenFileNames(parent, f"Add {title.lower()}", "", f"Videos ({exts})")
    clip_list.add_paths(files)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.settings = QSettings("Laulima Digital", APP_NAME)
        self.thread: QThread | None = None
        self.worker: Worker | None = None
        self.last_out: Path | None = None

        root = QWidget(objectName="root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(16)

        title = QLabel(APP_NAME, objectName="title")
        subtitle = QLabel("Drop in your hooks, bodies and endings. Get every combination as a ready-to-post vertical reel.",
                          objectName="subtitle")
        subtitle.setWordWrap(True)
        outer.addWidget(title)
        outer.addWidget(subtitle)

        self.hooks = ClipList("H", "Drop hook clips here")
        self.bodies = ClipList("B", "Drop body clips here")
        self.endings = ClipList("E", "Drop ending clips here\n(optional)")
        cols = QHBoxLayout()
        cols.setSpacing(12)
        cols.addWidget(_card("1", "Hooks", "The first few seconds", self.hooks))
        cols.addWidget(_card("2", "Bodies", "The main content", self.bodies))
        cols.addWidget(_card("3", "Endings", "CTA or payoff, optional", self.endings))
        outer.addLayout(cols, 1)
        for lst in (self.hooks, self.bodies, self.endings):
            lst.changed.connect(self._refresh)

        # ---- options
        opts = QFrame(objectName="card")
        og = QVBoxLayout(opts)
        og.setContentsMargins(16, 14, 16, 14)
        og.setSpacing(10)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("WHAT TO MAKE", objectName="sectionLabel"))
        mode_row.addSpacing(8)
        self.rb_all = QRadioButton("Every combination")
        self.rb_bal = QRadioButton("Balanced set")
        self.rb_bal.setToolTip("Each hook, body and ending appears the same number of times,\n"
                               "and every hook is paired with every body once.\n"
                               "Needs the same number of clips in all three columns.")
        grp = QButtonGroup(self)
        grp.addButton(self.rb_all); grp.addButton(self.rb_bal)
        self.rb_all.setChecked(self.settings.value("mode", engine.MODE_ALL) != engine.MODE_BALANCED)
        self.rb_bal.setChecked(not self.rb_all.isChecked())
        self.rb_all.toggled.connect(self._refresh)
        mode_row.addWidget(self.rb_all)
        mode_row.addSpacing(10)
        mode_row.addWidget(self.rb_bal)
        mode_row.addStretch(1)
        og.addLayout(mode_row)

        row2 = QHBoxLayout()
        row2.setSpacing(10)
        row2.addWidget(QLabel("FRAMING", objectName="sectionLabel"))
        self.framing = QComboBox()
        self.framing.addItem("Fill the screen (crops edges)", engine.FRAMING_FILL)
        self.framing.addItem("Fit with blurred background", engine.FRAMING_BLUR)
        self.framing.addItem("Fit with black bars", engine.FRAMING_BARS)
        idx = self.framing.findData(self.settings.value("framing", engine.FRAMING_FILL))
        self.framing.setCurrentIndex(max(idx, 0))
        self.framing.setToolTip("Only matters for clips that aren't already vertical 9:16.")
        row2.addWidget(self.framing)
        row2.addSpacing(14)
        row2.addWidget(QLabel("NAME", objectName="sectionLabel"))
        self.prefix = QLineEdit()
        self.prefix.setPlaceholderText("e.g. Paragon Oct")
        self.prefix.setText(self.settings.value("prefix", ""))
        self.prefix.setMaximumWidth(200)
        row2.addWidget(self.prefix)
        row2.addStretch(1)
        og.addLayout(row2)

        row3 = QHBoxLayout()
        row3.setSpacing(10)
        row3.addWidget(QLabel("SAVE TO", objectName="sectionLabel"))
        default_out = str(Path.home() / "Desktop" / "Reel Remixes")
        self.out_dir = Path(self.settings.value("out_dir", default_out))
        self.out_label = QLabel()
        self.out_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._show_out()
        change = QPushButton("Change…")
        change.clicked.connect(self._choose_out)
        row3.addWidget(self.out_label, 1)
        row3.addWidget(change)
        og.addLayout(row3)
        outer.addWidget(opts)

        # ---- action bar
        bar = QHBoxLayout()
        bar.setSpacing(12)
        left = QVBoxLayout()
        left.setSpacing(6)
        self.count_label = QLabel(objectName="count")
        self.status = QLabel("", objectName="status")
        self.status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.hide()
        left.addWidget(self.count_label)
        left.addWidget(self.bar)
        left.addWidget(self.status)
        bar.addLayout(left, 1)
        self.open_btn = QPushButton("Open folder")
        self.open_btn.clicked.connect(self._open_out)
        self.open_btn.hide()
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self._cancel)
        self.cancel_btn.hide()
        self.go = QPushButton("Make reels", objectName="primary")
        self.go.clicked.connect(self._start)
        bar.addWidget(self.open_btn)
        bar.addWidget(self.cancel_btn)
        bar.addWidget(self.go)
        outer.addLayout(bar)

        self.resize(980, 760)
        self._refresh()

    # ------------------------------------------------------------------ state
    def _mode(self) -> str:
        return engine.MODE_BALANCED if self.rb_bal.isChecked() else engine.MODE_ALL

    def _refresh(self):
        nh, nb, ne = self.hooks.count(), self.bodies.count(), self.endings.count()
        bal_ok = engine.balanced_available(nh, nb, ne)
        all_n = len(engine.plan_combos(nh, nb, ne, engine.MODE_ALL))
        self.rb_all.setText(f"Every combination ({all_n})" if all_n else "Every combination")
        self.rb_bal.setText(f"Balanced set ({nh * nh})" if bal_ok else "Balanced set (needs equal columns)")
        self.rb_bal.setEnabled(bal_ok or nh + nb + ne == 0)
        if self.rb_bal.isChecked() and not bal_ok and nh + nb + ne > 0:
            self.rb_all.setChecked(True)
        n = len(engine.plan_combos(nh, nb, ne, self._mode()))
        busy = self.thread is not None
        if not nh or not nb:
            self.count_label.setText("Add at least one hook and one body to get started.")
        else:
            self.count_label.setText(f"{n} reel{'s' if n != 1 else ''} will be made")
        self.go.setEnabled(n > 0 and not busy)

    def _show_out(self):
        self.out_label.setText(str(self.out_dir))
        self.out_label.setToolTip(str(self.out_dir))

    def _choose_out(self):
        d = QFileDialog.getExistingDirectory(self, "Save reels to", str(self.out_dir))
        if d:
            self.out_dir = Path(d)
            self._show_out()

    def _set_busy(self, busy: bool):
        for w in (self.hooks, self.bodies, self.endings, self.framing, self.prefix,
                  self.rb_all, self.rb_bal):
            w.setEnabled(not busy)
        self.cancel_btn.setVisible(busy)
        self.bar.setVisible(busy)
        if busy:
            self.open_btn.hide()
        self._refresh()
        if not busy:
            self.rb_bal.setEnabled(engine.balanced_available(
                self.hooks.count(), self.bodies.count(), self.endings.count()))

    # --------------------------------------------------------------- actions
    def _start(self):
        prefix = self.prefix.text().strip()
        stamp = datetime.now().strftime("%Y-%m-%d %H.%M")
        folder = self.out_dir / f"{prefix or 'Remix'} {stamp}"
        self.settings.setValue("mode", self._mode())
        self.settings.setValue("framing", self.framing.currentData())
        self.settings.setValue("prefix", prefix)
        self.settings.setValue("out_dir", str(self.out_dir))

        job = engine.Job(self.hooks.paths(), self.bodies.paths(), self.endings.paths(), folder,
                         mode=self._mode(), framing=self.framing.currentData(), prefix=prefix)
        self.last_out = folder
        self.thread = QThread(self)
        self.worker = Worker(job)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.cancelled.connect(self._on_cancelled)
        for sig in (self.worker.finished, self.worker.failed, self.worker.cancelled):
            sig.connect(self.thread.quit)
        self.thread.finished.connect(self._cleanup_thread)
        self.bar.setValue(0)
        self.status.setText("Starting…")
        self._set_busy(True)
        self.thread.start()

    def _on_progress(self, frac: float, msg: str):
        self.bar.setValue(int(frac * 1000))
        self.status.setText(msg)

    def _on_done(self, outputs: list):
        self.status.setText(f"Done. {len(outputs)} reels saved to “{self.last_out.name}”, "
                            f"with remix-key.csv listing what's in each one.")
        self.open_btn.show()

    def _on_failed(self, msg: str):
        self.status.setText("Something went wrong.")
        QMessageBox.warning(self, APP_NAME, msg)

    def _on_cancelled(self):
        self.status.setText("Cancelled. Any reels finished before cancelling are in the output folder.")
        if self.last_out and self.last_out.exists():
            self.open_btn.show()

    def _cleanup_thread(self):
        self.thread.deleteLater()
        self.thread = None
        self.worker = None
        self._set_busy(False)

    def _cancel(self):
        if self.worker:
            self.status.setText("Cancelling…")
            self.worker.job.cancel()

    def _open_out(self):
        target = self.last_out if self.last_out and self.last_out.exists() else self.out_dir
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def closeEvent(self, e):
        if self.worker:
            self.worker.job.cancel()
            if self.thread:
                self.thread.quit()
                self.thread.wait(3000)
        super().closeEvent(e)


def main():
    if sys.platform == "win32":
        try:  # crisp taskbar icon grouping on Windows
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("laulima.reelremixer")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    icon = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "assets" / "icon.png"
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
