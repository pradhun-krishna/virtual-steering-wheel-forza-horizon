"""
ForzaWheel — Windows Server App
PyQt5 GUI for the Forza Horizon 6 virtual steering wheel bridge.
Extends MobilWheel's ServerApp with Forza-specific controls and diagnostics.
"""

import os
import sys
import threading
import logging
import socket
from io import StringIO
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QProgressBar, QTextEdit, QGridLayout,
    QCheckBox, QFrame, QSizePolicy, QMessageBox, QGraphicsDropShadowEffect
)
from PyQt5.QtCore import pyqtSignal, QObject, QTimer, Qt, QSettings
from PyQt5.QtGui import (
    QIcon, QFont, QColor, QTextCursor, QFontDatabase,
    QPainter, QPainterPath, QLinearGradient, QPen, QBrush, QPixmap
)

# ── Logging setup ─────────────────────────────────────────────────────────────
log_stream = StringIO()
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[logging.StreamHandler(log_stream), logging.StreamHandler(sys.stdout)]
)

import forza_controller as controller
from app_version import APP_VERSION

try:
    from vjoy_setup_helper import VjoySetupHelper
    VJOY_SETUP_AVAILABLE = True
except ImportError:
    VJOY_SETUP_AVAILABLE = False

# ── Qt Signal bridge ──────────────────────────────────────────────────────────
class ServerSignals(QObject):
    log_message    = pyqtSignal(str)
    ui_update      = pyqtSignal(str, object)   # (control_name, value)
    connected      = pyqtSignal(str)            # client IP
    disconnected   = pyqtSignal()

signals = ServerSignals()

# ── Main Window ───────────────────────────────────────────────────────────────
class ForzaWheelServer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.server_thread = None
        self.is_running    = False
        self._setup_fonts()
        self._setup_window()
        self._build_ui()
        self._connect_signals()
        self._start_log_poller()

    # ── Fonts ─────────────────────────────────────────────────────────────────
    def _setup_fonts(self):
        self.font_mono   = QFont("Consolas", 9)
        self.font_label  = QFont("Segoe UI", 8)
        self.font_header = QFont("Segoe UI", 10, QFont.Bold)
        self.font_value  = QFont("Consolas", 14, QFont.Bold)
        self.font_big    = QFont("Segoe UI", 22, QFont.Bold)

    # ── Window ────────────────────────────────────────────────────────────────
    def _setup_window(self):
        self.setWindowTitle(f"ForzaWheel Server  v{APP_VERSION}")
        self.setMinimumSize(720, 560)
        self.resize(800, 620)
        self.setStyleSheet("""
            QMainWindow, QWidget { background:#0d0d14; color:#e0e0f0; }
            QLabel  { color:#e0e0f0; }
            QPushButton {
                background:#1a1a2e; color:#e0e0f0;
                border:1px solid #2a2a4a; border-radius:6px;
                padding:6px 14px; font-size:11px;
            }
            QPushButton:hover  { background:#22224a; border-color:#5555cc; }
            QPushButton:pressed{ background:#111130; }
            QPushButton:disabled{ color:#555; border-color:#222; }
            QTextEdit {
                background:#07070f; color:#a0ffb0;
                border:1px solid #1a1a2e; border-radius:4px;
                font-family:Consolas; font-size:9px;
            }
            QProgressBar {
                background:#111120; border:1px solid #2a2a4a; border-radius:3px;
                text-align:center; color:#fff; font-size:9px;
            }
            QProgressBar::chunk { background:#2255cc; border-radius:2px; }
            QFrame[frameShape="4"] { color:#2a2a4a; }
            QCheckBox { color:#a0a0c0; }
            QCheckBox::indicator { width:14px; height:14px;
                border:1px solid #3a3a6a; border-radius:3px; background:#111; }
            QCheckBox::indicator:checked { background:#2255cc; }
        """)

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # ── Header row ────────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        title = QLabel("FORZAWHEEL")
        title.setFont(self.font_big)
        title.setStyleSheet("color:#5599ff; letter-spacing:2px;")
        hdr.addWidget(title)
        hdr.addStretch()

        self.status_pill = QLabel("  ●  OFFLINE  ")
        self.status_pill.setFont(QFont("Segoe UI", 9, QFont.Bold))
        self.status_pill.setStyleSheet(
            "background:#1c0808; color:#ff4444; border:1px solid #440000;"
            "border-radius:10px; padding:3px 10px;")
        hdr.addWidget(self.status_pill)
        root.addLayout(hdr)

        # ── Separator ─────────────────────────────────────────────────────────
        sep = QFrame(); sep.setFrameShape(QFrame.HLine); root.addWidget(sep)

        # ── Control row ───────────────────────────────────────────────────────
        ctrl = QHBoxLayout()
        self.btn_start = QPushButton("▶  START SERVER")
        self.btn_stop  = QPushButton("■  STOP SERVER")
        self.btn_vjoy  = QPushButton("⚙  Setup vJoy")
        self.btn_stop.setEnabled(False)
        self.btn_start.setStyleSheet("background:#0e2a0e; color:#44ff88; border-color:#225522;")
        self.btn_stop.setStyleSheet( "background:#2a0e0e; color:#ff4444; border-color:#552222;")
        for btn in (self.btn_start, self.btn_stop, self.btn_vjoy):
            btn.setFont(QFont("Segoe UI", 10, QFont.Bold))
            btn.setMinimumHeight(36)
            ctrl.addWidget(btn)
        root.addLayout(ctrl)

        # ── IP display ────────────────────────────────────────────────────────
        ip_row = QHBoxLayout()
        ip_lbl  = QLabel("Server IP:")
        ip_lbl.setFont(self.font_label)
        self.ip_value = QLabel(self._get_local_ip())
        self.ip_value.setFont(QFont("Consolas", 11, QFont.Bold))
        self.ip_value.setStyleSheet("color:#5599ff;")
        port_lbl = QLabel("Port: 12345")
        port_lbl.setFont(self.font_label)
        port_lbl.setStyleSheet("color:#888;")
        ip_row.addWidget(ip_lbl)
        ip_row.addWidget(self.ip_value)
        ip_row.addSpacing(20)
        ip_row.addWidget(port_lbl)
        ip_row.addStretch()
        root.addLayout(ip_row)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.HLine); root.addWidget(sep2)

        # ── Main content: inputs + log ────────────────────────────────────────
        content = QHBoxLayout()
        content.setSpacing(12)

        # Left: controller inputs display
        inputs_panel = self._build_inputs_panel()
        content.addWidget(inputs_panel, 1)

        # Right: button states + log
        right = QVBoxLayout()
        btn_panel = self._build_button_panel()
        right.addWidget(btn_panel)

        log_lbl = QLabel("SYSTEM LOG")
        log_lbl.setFont(self.font_header)
        log_lbl.setStyleSheet("color:#888; margin-top:6px;")
        right.addWidget(log_lbl)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(140)
        right.addWidget(self.log_text, 1)

        content.addLayout(right, 1)
        root.addLayout(content, 1)

        # ── Footer ────────────────────────────────────────────────────────────
        footer = QLabel(f"ForzaWheel v{APP_VERSION}  —  Virtual Steering Wheel for Forza Horizon 6")
        footer.setFont(QFont("Segoe UI", 8))
        footer.setStyleSheet("color:#444; margin-top:4px;")
        footer.setAlignment(Qt.AlignCenter)
        root.addWidget(footer)

    def _build_inputs_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        lbl = QLabel("CONTROLLER INPUTS")
        lbl.setFont(self.font_header)
        lbl.setStyleSheet("color:#888;")
        layout.addWidget(lbl)

        # Steering indicator
        steer_lbl = QLabel("STEERING")
        steer_lbl.setFont(self.font_label)
        layout.addWidget(steer_lbl)
        self.steering_bar = SteeringIndicatorWidget()
        self.steering_bar.setFixedHeight(36)
        layout.addWidget(self.steering_bar)

        # Throttle bar
        throt_lbl = QLabel("THROTTLE (GAS)")
        throt_lbl.setFont(self.font_label)
        layout.addWidget(throt_lbl)
        self.throttle_bar = QProgressBar()
        self.throttle_bar.setRange(0, 100)
        self.throttle_bar.setValue(0)
        self.throttle_bar.setStyleSheet(
            "QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            "stop:0 #117700, stop:1 #44ff44); }")
        self.throttle_bar.setFixedHeight(22)
        layout.addWidget(self.throttle_bar)

        # Brake bar
        brake_lbl = QLabel("BRAKE")
        brake_lbl.setFont(self.font_label)
        layout.addWidget(brake_lbl)
        self.brake_bar = QProgressBar()
        self.brake_bar.setRange(0, 100)
        self.brake_bar.setValue(0)
        self.brake_bar.setStyleSheet(
            "QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            "stop:0 #770011, stop:1 #ff4444); }")
        self.brake_bar.setFixedHeight(22)
        layout.addWidget(self.brake_bar)

        # Clutch bar
        clutch_lbl = QLabel("CLUTCH")
        clutch_lbl.setFont(self.font_label)
        layout.addWidget(clutch_lbl)
        self.clutch_bar = QProgressBar()
        self.clutch_bar.setRange(0, 100)
        self.clutch_bar.setValue(0)
        self.clutch_bar.setStyleSheet(
            "QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            "stop:0 #554400, stop:1 #ffcc44); }")
        self.clutch_bar.setFixedHeight(22)
        layout.addWidget(self.clutch_bar)

        # Connection stats
        layout.addSpacing(6)
        stats_grid = QGridLayout()
        self.lbl_client   = self._stat_label("Client:", "—")
        self.lbl_packets  = self._stat_label("Packets/s:", "0")
        stats_grid.addWidget(self.lbl_client[0],  0, 0)
        stats_grid.addWidget(self.lbl_client[1],  0, 1)
        stats_grid.addWidget(self.lbl_packets[0], 1, 0)
        stats_grid.addWidget(self.lbl_packets[1], 1, 1)
        layout.addLayout(stats_grid)

        layout.addStretch()
        return panel

    def _stat_label(self, title, value):
        lbl_title = QLabel(title)
        lbl_title.setFont(self.font_label)
        lbl_title.setStyleSheet("color:#666;")
        lbl_val   = QLabel(value)
        lbl_val.setFont(QFont("Consolas", 9))
        lbl_val.setStyleSheet("color:#aaaaee;")
        return lbl_title, lbl_val

    def _build_button_panel(self):
        panel = QWidget()
        grid  = QGridLayout(panel)
        grid.setSpacing(6)

        lbl = QLabel("BUTTON STATES")
        lbl.setFont(self.font_header)
        lbl.setStyleSheet("color:#888;")
        grid.addWidget(lbl, 0, 0, 1, 4)

        buttons = [
            ("SHIFT ↑", "shift_up"),   ("SHIFT ↓", "shift_down"),
            ("HANDBRAKE", "handbrake"),("HORN", "horn"),
            ("REWIND", "rewind"),      ("PAUSE", "pause"),
            ("CAMERA", "camera"),      ("LOOK←", "look_left"),
            ("LOOK→", "look_right"),   ("LOOK↑", "look_back"),
        ]
        self.btn_lights = {}
        for i, (label, key) in enumerate(buttons):
            row = (i // 4) + 1
            col = i % 4
            w = ButtonLightWidget(label)
            grid.addWidget(w, row, col)
            self.btn_lights[key] = w

        return panel

    # ── Signals ───────────────────────────────────────────────────────────────
    def _connect_signals(self):
        signals.log_message.connect(self._append_log)
        signals.ui_update.connect(self._on_ui_update)
        signals.connected.connect(self._on_connected)
        signals.disconnected.connect(self._on_disconnected)

        self.btn_start.clicked.connect(self._start_server)
        self.btn_stop.clicked.connect(self._stop_server)
        self.btn_vjoy.clicked.connect(self._setup_vjoy)

    # ── Log poller ────────────────────────────────────────────────────────────
    def _start_log_poller(self):
        self._last_log_pos = 0
        timer = QTimer(self)
        timer.timeout.connect(self._poll_logs)
        timer.start(300)

    def _poll_logs(self):
        log_stream.seek(self._last_log_pos)
        new_text = log_stream.read()
        if new_text:
            self._last_log_pos = log_stream.tell()
            for line in new_text.strip().split('\n'):
                if line.strip():
                    self._append_log(line)

    # ── UI update callbacks ───────────────────────────────────────────────────
    def _on_ui_update(self, control, value):
        if control == 'steering':
            # value is vjoy 1-32767; convert to -100..+100 %
            pct = int((value - 16384) / 16384 * 100)
            self.steering_bar.set_percent(pct)
        elif control == 'throttle':
            self.throttle_bar.setValue(int(value))
        elif control == 'brake':
            self.brake_bar.setValue(int(value))
        elif control == 'clutch':
            self.clutch_bar.setValue(int(value))
        elif control in self.btn_lights:
            self.btn_lights[control].set_active(bool(value))

    def _on_connected(self, ip):
        self.status_pill.setText(f"  ●  CONNECTED  ({ip})")
        self.status_pill.setStyleSheet(
            "background:#0c1c0c; color:#44ff88; border:1px solid #225522;"
            "border-radius:10px; padding:3px 10px;")
        self.lbl_client[1].setText(ip)

    def _on_disconnected(self):
        self.status_pill.setText("  ●  OFFLINE  ")
        self.status_pill.setStyleSheet(
            "background:#1c0808; color:#ff4444; border:1px solid #440000;"
            "border-radius:10px; padding:3px 10px;")
        self.lbl_client[1].setText("—")
        self.steering_bar.set_percent(0)
        self.throttle_bar.setValue(0)
        self.brake_bar.setValue(0)
        self.clutch_bar.setValue(0)
        for w in self.btn_lights.values():
            w.set_active(False)

    def _append_log(self, text):
        self.log_text.append(text)
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_text.setTextCursor(cursor)
        # Keep last 500 lines
        doc = self.log_text.document()
        if doc.blockCount() > 500:
            cursor = self.log_text.textCursor()
            cursor.movePosition(QTextCursor.Start)
            cursor.movePosition(QTextCursor.Down, QTextCursor.KeepAnchor, doc.blockCount() - 500)
            cursor.removeSelectedText()

    # ── Server control ────────────────────────────────────────────────────────
    def _start_server(self):
        if self.is_running: return
        self.is_running = True
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.status_pill.setText("  ●  LISTENING  ")
        self.status_pill.setStyleSheet(
            "background:#1a1a08; color:#ffcc44; border:1px solid #555522;"
            "border-radius:10px; padding:3px 10px;")

        def ui_callback(control, value):
            signals.ui_update.emit(control, value)

        def run():
            try:
                controller.start_server(update_ui_callback=ui_callback)
            except Exception as e:
                logging.error(f"Server error: {e}")
            finally:
                self.is_running = False

        self.server_thread = threading.Thread(target=run, daemon=True)
        self.server_thread.start()
        self._append_log(f"Server started on port 12345. IP: {self._get_local_ip()}")

    def _stop_server(self):
        controller.shutdown_event.set()
        self.is_running = False
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        signals.disconnected.emit()
        self._append_log("Server stopped.")

    def _setup_vjoy(self):
        if not VJOY_SETUP_AVAILABLE:
            QMessageBox.information(self, "vJoy Setup",
                "Run vJoy\\vJoySetup.exe manually to install the vJoy driver.\n"
                "Then restart this application.")
            return
        helper = VjoySetupHelper()
        status = helper.check_vjoy_status()
        if status == 'installed':
            QMessageBox.information(self, "vJoy", "vJoy is already installed.")
        else:
            vjoy_exe = Path(__file__).parent / "vJoy" / "vJoySetup.exe"
            if vjoy_exe.exists():
                import subprocess
                subprocess.Popen([str(vjoy_exe)], shell=True)
                QMessageBox.information(self, "vJoy",
                    "vJoy installer launched. After installation:\n"
                    "1. Restart this application\n"
                    "2. In vJoy Config, ensure device 1 has:\n"
                    "   - X, Y, Z, Rx axes enabled\n"
                    "   - At least 12 buttons")
            else:
                QMessageBox.warning(self, "vJoy", f"vJoySetup.exe not found at:\n{vjoy_exe}")

    # ── Utility ───────────────────────────────────────────────────────────────
    @staticmethod
    def _get_local_ip():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def closeEvent(self, event):
        if self.is_running:
            self._stop_server()
        event.accept()


# ── Custom Widgets ─────────────────────────────────────────────────────────────
class SteeringIndicatorWidget(QWidget):
    """Visual horizontal steering bar: -100% left, 0 center, +100% right."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._percent = 0  # -100 to +100

    def set_percent(self, pct):
        self._percent = max(-100, min(100, pct))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        cx = w // 2

        # Background track
        p.fillRect(0, h//2 - 2, w, 4, QColor(30, 30, 60))

        # Center tick
        p.setPen(QPen(QColor(80, 80, 130), 1))
        p.drawLine(cx, h//4, cx, 3*h//4)

        # Filled zone
        fill_w = int((abs(self._percent) / 100) * (cx - 4))
        color  = QColor(0x55, 0x99, 0xff) if self._percent >= 0 else QColor(0xff, 0x77, 0x22)
        if self._percent >= 0:
            p.fillRect(cx, h//2 - 4, fill_w, 8, color)
        else:
            p.fillRect(cx - fill_w, h//2 - 4, fill_w, 8, color)

        # Dot
        dot_x = cx + int((self._percent / 100) * (cx - 8))
        p.setBrush(QBrush(QColor(0xff, 0xff, 0xff)))
        p.setPen(Qt.NoPen)
        p.drawEllipse(dot_x - 6, h//2 - 6, 12, 12)

        # Labels
        p.setPen(QPen(QColor(80, 80, 120)))
        p.setFont(QFont("Consolas", 7))
        p.drawText(2, h - 2, "L")
        p.drawText(w - 10, h - 2, "R")
        p.setPen(QPen(QColor(180, 180, 220)))
        p.drawText(cx - 14, h - 2, f"{self._percent:+d}%")


class ButtonLightWidget(QWidget):
    """Small labeled indicator light that turns green when active."""
    def __init__(self, label, parent=None):
        super().__init__(parent)
        self._label  = label
        self._active = False
        self.setFixedSize(82, 32)

    def set_active(self, active):
        self._active = active
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        bg_color  = QColor(0x0a, 0x2a, 0x0a) if self._active else QColor(0x0f, 0x0f, 0x1a)
        bdr_color = QColor(0x44, 0xff, 0x88) if self._active else QColor(0x2a, 0x2a, 0x4a)
        p.setBrush(QBrush(bg_color))
        p.setPen(QPen(bdr_color, 1))
        p.drawRoundedRect(1, 1, w-2, h-2, 4, 4)

        dot = QColor(0x44, 0xff, 0x88) if self._active else QColor(0x33, 0x33, 0x55)
        p.setBrush(QBrush(dot)); p.setPen(Qt.NoPen)
        p.drawEllipse(6, h//2 - 4, 8, 8)

        txt = QColor(0xcc, 0xff, 0xcc) if self._active else QColor(0x66, 0x66, 0x88)
        p.setPen(QPen(txt))
        p.setFont(QFont("Segoe UI", 7, QFont.Bold if self._active else QFont.Normal))
        p.drawText(18, 0, w - 20, h, Qt.AlignVCenter, self._label)


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    # Check vJoy on startup
    if not os.path.isfile(os.path.join(os.path.dirname(__file__), 'vJoy', 'x64', 'vJoyInterface.dll')):
        print("WARNING: vJoy DLL not found. Virtual controller will not work.")

    app = QApplication(sys.argv)
    app.setApplicationName("ForzaWheel")
    app.setStyle("Fusion")

    win = ForzaWheelServer()
    win.show()

    # Auto-start if requested
    settings = QSettings("ForzaWheel", "Server")
    if settings.value("autostart", False, type=bool):
        win._start_server()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
