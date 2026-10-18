"""Complete four-image AI + automatic emergency + ESP32 IoT application.

Bug fixes and improvements:
- Model caching: YOLO weights are loaded once and reused across calculations.
- QImage memory safety: QImage.copy() prevents use-after-free crashes.
- Unicode/non-ASCII path support on Windows via cv2.imdecode(np.fromfile(...)).
- Unified countdown timer: both Yellow AND Green phases show live second-by-second countdown.
- ESP32 Hardware Toolbar: runtime IP input, Test Ping button, Hardware Sync toggle, status indicator.
- Graceful Simulation Mode: if ESP32 is unreachable the sequence keeps running in software only.
- Race condition prevention: buttons are disabled while a sequence is running.
- Stop button always resets to a safe known state.
"""
import sys
import threading
import cv2
import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QGridLayout, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFileDialog, QMessageBox, QTableWidget, QTableWidgetItem,
    QGroupBox, QLineEdit, QCheckBox
)
from detector import VehicleDetector
from emergency_detector import EmergencyDetector
import iot_controller

DIRECTIONS  = ['NORTH', 'EAST', 'SOUTH', 'WEST']
YELLOW_SECS = 3   # seconds to hold yellow before switching to green


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _imread_unicode(path: str):
    """Load an image from a path that may contain non-ASCII characters (Windows)."""
    buf = np.fromfile(path, dtype=np.uint8)
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


# ─────────────────────────────────────────────────────────────────────────────
#  Traffic Light Widget  (R → Y → G, vertical, configurable dot size)
# ─────────────────────────────────────────────────────────────────────────────
class TrafficLightWidget(QWidget):
    """
    Visual traffic-light widget with three coloured circles stacked vertically.
    Active bulb is fully lit; inactive bulbs are shown very dim.

    States
    ------
    'red'    – STOP   (check camera)
    'yellow' – READY  (get ready)
    'green'  – GO     (traffic is flowing)
    """

    # (lit colour, dim colour)
    COLORS = {
        'red':    ('#ff3333', '#3a0808'),
        'yellow': ('#ffdd00', '#302a00'),
        'green':  ('#00ff55', '#002210'),
    }

    def __init__(self, parent=None, dot_size: int = 44):
        super().__init__(parent)
        ds       = dot_size
        spacing  = max(8,  ds // 5)
        pad      = max(10, ds // 4)
        w        = ds + 2 * pad
        h        = 3 * ds + 2 * spacing + 2 * pad
        self.setFixedSize(w, h)

        # Dark housing that contains the three bulbs
        housing = QWidget(self)
        housing.setGeometry(0, 0, w, h)
        housing.setStyleSheet(
            'background: qlineargradient(x1:0, y1:0, x2:1, y2:1,'
            '   stop:0 #242424, stop:1 #181818);'
            'border-radius: 14px;'
            'border: 2px solid #555;'
        )

        inner = QVBoxLayout(housing)
        inner.setContentsMargins(pad, pad, pad, pad)
        inner.setSpacing(spacing)

        self.dots: dict[str, QLabel] = {}
        for color in ('red', 'yellow', 'green'):
            dot = QLabel()
            dot.setFixedSize(ds, ds)
            dot.setAlignment(Qt.AlignCenter)
            inner.addWidget(dot, 0, Qt.AlignCenter)
            self.dots[color] = dot

        self._state = 'red'
        self.set_state('red')

    # ── public API ────────────────────────────────────────────────────────────

    def set_state(self, state: str):
        """Switch the active bulb; dim the other two."""
        self._state = state
        for color, dot in self.dots.items():
            active    = (color == state)
            on_c, off_c = self.COLORS[color]
            c         = on_c if active else off_c
            border_c  = on_c if active else '#444'
            r         = dot.width() // 2
            dot.setStyleSheet(
                f'background: {c};'
                f'border-radius: {r}px;'
                f'border: 2px solid {border_c};'
            )

    @property
    def state(self) -> str:
        return self._state


# ─────────────────────────────────────────────────────────────────────────────
#  Main Application
# ─────────────────────────────────────────────────────────────────────────────
class TrafficApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('AI Traffic Signal Control - IoT')
        self.resize(1550, 980)

        self.images             = {d: None for d in DIRECTIONS}
        # FIX: cache detectors so models are not reloaded on every Calculate press
        self._vehicle_detector: VehicleDetector | None   = None
        self._emergency_detector: EmergencyDetector | None = None
        self.results            = {}
        self.sequence           = []
        self.seq_index          = 0
        self.remaining          = 0          # seconds remaining in current phase
        self._yellow_dir: str | None = None
        self._phase             = 'idle'     # 'idle' | 'yellow' | 'green'

        # Single unified 1-second timer drives both Yellow and Green countdowns
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)

        self.build_ui()

    # ── Detector accessors (lazy init / cache) ────────────────────────────────

    @property
    def vehicle_detector(self) -> VehicleDetector:
        if self._vehicle_detector is None:
            self.status.setText('Loading YOLO model (yolo11n.pt)...')
            QApplication.processEvents()
            self._vehicle_detector = VehicleDetector('yolo11n.pt', 0.25)
        return self._vehicle_detector

    @vehicle_detector.setter
    def vehicle_detector(self, val):
        self._vehicle_detector = val

    @property
    def emergency_detector(self) -> EmergencyDetector:
        if self._emergency_detector is None:
            self.status.setText('Loading YOLO-World model (yolov8s-worldv2.pt)...')
            QApplication.processEvents()
            self._emergency_detector = EmergencyDetector('yolov8s-worldv2.pt', 0.60)
        return self._emergency_detector

    @emergency_detector.setter
    def emergency_detector(self, val):
        self._emergency_detector = val

    # ── UI construction ───────────────────────────────────────────────────────

    def build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        main = QVBoxLayout(root)

        title = QLabel('AI TRAFFIC SIGNAL CONTROL')
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet('font-size:28px;font-weight:bold;padding:12px')
        main.addWidget(title)

        subtitle = QLabel(
            'Four camera images → YOLO/OpenCV → automatic emergency priority → ESP32 IoT'
        )
        subtitle.setAlignment(Qt.AlignCenter)
        main.addWidget(subtitle)

        # ── ESP32 Hardware Toolbar ─────────────────────────────────────────
        hw_box = QGroupBox('ESP32 Hardware Settings')
        hw_layout = QHBoxLayout(hw_box)

        hw_layout.addWidget(QLabel('ESP32 IP:'))
        self.ip_input = QLineEdit(iot_controller.get_esp32_ip())
        self.ip_input.setFixedWidth(160)
        self.ip_input.setPlaceholderText('e.g. 192.168.1.100')
        self.ip_input.editingFinished.connect(self._apply_ip)
        hw_layout.addWidget(self.ip_input)

        self.btn_ping = QPushButton('Test Ping')
        self.btn_ping.setFixedWidth(90)
        self.btn_ping.clicked.connect(self._ping_esp32)
        hw_layout.addWidget(self.btn_ping)

        self.hw_status = QLabel('⚪ Simulation Mode')
        self.hw_status.setStyleSheet('color:#aaa; font-weight:bold; padding: 0 8px;')
        hw_layout.addWidget(self.hw_status)

        self.hw_toggle = QCheckBox('Hardware Sync (ESP32)')
        self.hw_toggle.setChecked(True)
        hw_layout.addWidget(self.hw_toggle)

        hw_layout.addStretch()
        main.addWidget(hw_box)

        # ── 4-direction camera grid ───────────────────────────────────────
        grid = QGridLayout()
        main.addLayout(grid)
        self.image_labels  = {}
        self.traffic_lights = {}
        self.state_labels  = {}

        for i, d in enumerate(DIRECTIONS):
            box = QGroupBox(f'{d} CAMERA IMAGE')
            box_h = QHBoxLayout(box)

            # Left column: camera image preview + upload button
            left = QVBoxLayout()
            lab = QLabel('No image')
            lab.setAlignment(Qt.AlignCenter)
            lab.setMinimumSize(380, 260)
            lab.setStyleSheet('background:#151515; border:1px solid #555')
            btn = QPushButton(f'Upload {d} Image')
            btn.clicked.connect(lambda _, x=d: self.upload(x))
            left.addWidget(lab)
            left.addWidget(btn)

            # Right column: traffic light widget + state text label
            right = QVBoxLayout()
            right.setAlignment(Qt.AlignCenter)

            tl = TrafficLightWidget(dot_size=44)

            slbl = QLabel('🔴 STOP\nCheck Camera')
            slbl.setAlignment(Qt.AlignCenter)
            slbl.setWordWrap(True)
            slbl.setFixedWidth(92)
            slbl.setStyleSheet(
                'font-size:10px; color:#ff6666; font-weight:bold; padding:4px;'
            )

            right.addStretch()
            right.addWidget(tl,   0, Qt.AlignCenter)
            right.addWidget(slbl, 0, Qt.AlignCenter)
            right.addStretch()

            box_h.addLayout(left,  1)
            box_h.addLayout(right, 0)

            self.image_labels[d]   = lab
            self.traffic_lights[d] = tl
            self.state_labels[d]   = slbl
            grid.addWidget(box, i // 2, i % 2)

        # ── Control buttons ───────────────────────────────────────────────
        controls = QHBoxLayout()
        self.bcalc  = QPushButton('CALCULATE TRAFFIC SIGNAL')
        self.bstart = QPushButton('START SIGNAL SEQUENCE')
        self.bstop  = QPushButton('STOP ESP32 / ALL RED')
        self.bcalc.clicked.connect(self.calculate)
        self.bstart.clicked.connect(self.start_sequence)
        self.bstop.clicked.connect(self.stop_all)
        controls.addWidget(self.bcalc)
        controls.addWidget(self.bstart)
        controls.addWidget(self.bstop)
        main.addLayout(controls)

        # ── Status bar ────────────────────────────────────────────────────
        self.status = QLabel('Upload four images, then calculate.')
        self.status.setAlignment(Qt.AlignCenter)
        main.addWidget(self.status)

        # ── Bottom row: results table + live signal panel ─────────────────
        bottom = QHBoxLayout()
        main.addLayout(bottom)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ['Direction', 'Vehicles', 'Density', 'Green Time', 'Emergency', 'Order']
        )
        bottom.addWidget(self.table, 2)

        # Live signal execution panel – contains a BIG traffic light
        live = QGroupBox('LIVE SIGNAL EXECUTION')
        ll   = QVBoxLayout(live)

        # Large traffic light (dot_size=70 → ~230px tall)
        self.main_tl = TrafficLightWidget(dot_size=70)
        ll.addWidget(self.main_tl, 0, Qt.AlignCenter)

        self.current = QLabel('WAITING')
        self.current.setAlignment(Qt.AlignCenter)
        self.current.setStyleSheet(
            'font-size:22px; font-weight:bold; margin-top:8px;'
        )
        self.countdown = QLabel('-- seconds')
        self.countdown.setAlignment(Qt.AlignCenter)
        self.countdown.setStyleSheet('font-size:18px;')

        ll.addWidget(self.current)
        ll.addWidget(self.countdown)
        bottom.addWidget(live, 1)

    # ── ESP32 toolbar helpers ─────────────────────────────────────────────────

    def _apply_ip(self):
        """Apply the IP address entered in the toolbar."""
        new_ip = self.ip_input.text().strip()
        if new_ip:
            iot_controller.set_esp32_ip(new_ip)
            self.ip_input.setText(iot_controller.get_esp32_ip())
            self.hw_status.setText('⚪ IP updated — ping to verify')
            self.hw_status.setStyleSheet('color:#aaa; font-weight:bold; padding: 0 8px;')

    def _ping_esp32(self):
        """Ping the ESP32 in a background thread so the GUI stays responsive."""
        self.btn_ping.setEnabled(False)
        self._apply_ip()
        self.hw_status.setText('⏳ Pinging...')
        self.hw_status.setStyleSheet('color:#ffdd00; font-weight:bold; padding: 0 8px;')

        def _do_ping():
            ok = iot_controller.check_connection(timeout=2.0)
            # Marshal result back to the main thread
            QTimer.singleShot(0, lambda: self._ping_result(ok))

        threading.Thread(target=_do_ping, daemon=True).start()

    def _ping_result(self, ok: bool):
        self.btn_ping.setEnabled(True)
        if ok:
            self.hw_status.setText('🟢 Connected')
            self.hw_status.setStyleSheet('color:#00ff88; font-weight:bold; padding: 0 8px;')
        else:
            self.hw_status.setText('🔴 Offline — Simulation Mode')
            self.hw_status.setStyleSheet('color:#ff4444; font-weight:bold; padding: 0 8px;')

    def _hw_sync_enabled(self) -> bool:
        return self.hw_toggle.isChecked()

    def _send_yellow_async(self, direction: str):
        """Non-blocking ESP32 yellow call — fires and forgets in a daemon thread."""
        if not self._hw_sync_enabled():
            return
        threading.Thread(
            target=iot_controller.send_yellow, args=(direction,), daemon=True
        ).start()

    def _send_signal_async(self, direction: str, seconds: int, callback=None):
        """Non-blocking ESP32 green call in a daemon thread.

        *callback* (if provided) is invoked on the main thread with success bool.
        """
        if not self._hw_sync_enabled():
            if callback:
                QTimer.singleShot(0, lambda: callback(True))
            return

        def _do():
            ok = iot_controller.send_signal(direction, seconds)
            if callback:
                QTimer.singleShot(0, lambda: callback(ok))

        threading.Thread(target=_do, daemon=True).start()

    def _send_stop_async(self):
        if not self._hw_sync_enabled():
            return
        threading.Thread(target=iot_controller.stop_signal, daemon=True).start()

    # ── Traffic light helpers ─────────────────────────────────────────────────

    def _set_light(self, direction: str, state: str):
        """Update one direction's traffic light widget and its state label."""
        self.traffic_lights[direction].set_state(state)
        texts = {
            'red':    '🔴 STOP\nCheck Camera',
            'yellow': '🟡 READY\nGet Ready...',
            'green':  '🟢 GO!',
        }
        text_colors = {
            'red':    '#ff6666',
            'yellow': '#ffdd66',
            'green':  '#66ff99',
        }
        self.state_labels[direction].setText(texts[state])
        self.state_labels[direction].setStyleSheet(
            f'font-size:10px; color:{text_colors[state]};'
            f'font-weight:bold; padding:4px;'
        )

    def _set_all_lights(self, state: str):
        """Set all four direction lights to the same state."""
        for d in DIRECTIONS:
            self._set_light(d, state)

    # ── Image handling ────────────────────────────────────────────────────────

    def upload(self, direction):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Select traffic image', '', 'Images (*.png *.jpg *.jpeg *.webp)'
        )
        if not path:
            return
        # FIX: Use imdecode for Unicode/non-ASCII Windows paths
        img = _imread_unicode(path)
        if img is None:
            QMessageBox.warning(self, 'Image Error', 'Could not read this image.')
            return
        self.images[direction] = img
        self.show_image(img, self.image_labels[direction])
        self.status.setText(f'{direction} image loaded.')

    def show_image(self, img, label):
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        # FIX: Call .copy() on QImage to detach it from the numpy buffer
        q = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888).copy()
        pix = QPixmap.fromImage(q).scaled(
            label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        label.setPixmap(pix)

    # ── Detection & calculation ───────────────────────────────────────────────

    def calculate(self):
        missing = [d for d in DIRECTIONS if self.images[d] is None]
        if missing:
            QMessageBox.warning(self, 'Missing images', 'Upload: ' + ', '.join(missing))
            return
        try:
            # FIX: detectors are cached — models load once and are reused
            vd = self.vehicle_detector
            ed = self.emergency_detector
            self.results = {}

            for d in DIRECTIONS:
                img       = self.images[d]
                det, _    = vd.detect(img)
                em        = ed.detect(img)
                annotated = vd.annotate(img, det)
                annotated = ed.annotate(annotated, em)
                self.show_image(annotated, self.image_labels[d])

                count   = len(det)
                density = 'LOW' if count <= 5 else ('MEDIUM' if count <= 12 else 'HIGH')
                green   = max(10, min(30, 10 + count))
                self.results[d] = {
                    'vehicles': count, 'density': density,
                    'green': green,
                    'emergency': len(em) > 0, 'emergency_items': em,
                }

            self.build_sequence()
            self.update_table()

            # Reset all traffic lights to RED after fresh calculation
            self._set_all_lights('red')
            self.main_tl.set_state('red')
            self.current.setText('WAITING')
            self.countdown.setText('-- seconds')

            ems = [d for d in DIRECTIONS if self.results[d]['emergency']]
            self.status.setText(
                '🚑 AUTOMATIC EMERGENCY PRIORITY: ' + ', '.join(ems)
                if ems else
                'No emergency vehicle detected. Normal traffic priority ready.'
            )
        except Exception as e:
            QMessageBox.critical(self, 'Processing Error', str(e))

    def build_sequence(self):
        emergency = [d for d in DIRECTIONS if self.results[d]['emergency']]
        normal    = [d for d in DIRECTIONS if d not in emergency]
        normal.sort(key=lambda d: self.results[d]['vehicles'], reverse=True)
        self.sequence = emergency + normal

    def update_table(self):
        self.table.setRowCount(len(DIRECTIONS))
        for i, d in enumerate(self.sequence):
            r    = self.results[d]
            vals = [
                d, str(r['vehicles']), r['density'],
                f"{r['green']} sec",
                'YES' if r['emergency'] else 'NO',
                str(i + 1),
            ]
            for j, v in enumerate(vals):
                self.table.setItem(i, j, QTableWidgetItem(v))

    # ── Signal sequence ───────────────────────────────────────────────────────

    def start_sequence(self):
        if not self.sequence:
            QMessageBox.warning(
                self, 'Calculate first', 'Click CALCULATE TRAFFIC SIGNAL first.'
            )
            return
        # FIX: disable start button while running to prevent double-start
        self.bstart.setEnabled(False)
        self.bcalc.setEnabled(False)
        self.seq_index = 0
        self._start_current()

    def _start_current(self):
        """
        Begin the next direction in the sequence.

        Phase 1 – YELLOW: all RED, current direction YELLOW for YELLOW_SECS seconds.
        Phase 2 – GREEN:  current direction GREEN for the computed green seconds.
        Both phases show a live second-by-second countdown via the unified _tick().
        """
        if self.seq_index >= len(self.sequence):
            self._finish_sequence()
            return

        d = self.sequence[self.seq_index]
        self._yellow_dir = d
        self._phase = 'yellow'
        self.remaining = YELLOW_SECS

        # ── PHASE 1: YELLOW ──────────────────────────────────────────────
        self._set_all_lights('red')
        self._set_light(d, 'yellow')
        self.main_tl.set_state('yellow')
        self.current.setText(f'🟡 {d} → READY')
        self.countdown.setText(f'{self.remaining} seconds')
        self.status.setText(
            f'🟡 {d}: Yellow phase — Get ready... (green in {YELLOW_SECS} seconds)'
        )

        # Non-blocking ESP32 call (fire-and-forget)
        self._send_yellow_async(d)

        # Start the unified countdown timer
        self.timer.start(1000)

    def _tick(self):
        """Unified 1-second tick for both Yellow and Green phases."""
        self.remaining -= 1
        self.countdown.setText(f'{max(0, self.remaining)} seconds')

        if self.remaining > 0:
            return

        # Phase expired — advance
        self.timer.stop()

        if self._phase == 'yellow':
            self._begin_green()
        elif self._phase == 'green':
            self.seq_index += 1
            self._start_current()

    def _begin_green(self):
        """
        Transition from Yellow to Green.
        Sends /set to ESP32 in a background thread; continues in Simulation Mode
        if the ESP32 is unreachable (graceful fallback).
        """
        d   = self._yellow_dir
        sec = self.results[d]['green']

        # ── PHASE 2: GREEN ───────────────────────────────────────────────
        self._phase     = 'green'
        self.remaining  = sec

        self._set_light(d, 'green')
        self.main_tl.set_state('green')
        self.current.setText(f'🟢  {d}  →  GO!')
        self.countdown.setText(f'{self.remaining} seconds')
        self.status.setText(f'🟢 {d}: GREEN — Traffic is flowing!')

        def _on_send(ok: bool):
            if not ok:
                # Graceful fallback: warn once, keep the GUI cycle running
                self.hw_status.setText('🔴 Offline — Simulation Mode')
                self.hw_status.setStyleSheet(
                    'color:#ff4444; font-weight:bold; padding: 0 8px;'
                )

        self._send_signal_async(d, sec, callback=_on_send)

        # Start the Green countdown immediately (no need to wait for ESP32 ACK)
        self.timer.start(1000)

    def _finish_sequence(self):
        """Called after the last direction has completed its green phase."""
        self.stop_all()
        self.status.setText('✅ Sequence completed. ESP32 is ALL RED.')

    def stop_all(self):
        """Stop everything, set all signals to RED, notify ESP32 asynchronously."""
        self.timer.stop()
        self._phase      = 'idle'
        self._yellow_dir = None

        self._send_stop_async()

        self._set_all_lights('red')
        self.main_tl.set_state('red')
        self.current.setText('🔴  ALL RED / STOPPED')
        self.countdown.setText('-- seconds')

        # FIX: re-enable buttons after stop
        self.bstart.setEnabled(True)
        self.bcalc.setEnabled(True)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    w   = TrafficApp()
    w.show()
    sys.exit(app.exec())
