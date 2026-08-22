"""
ForzaWheel Controller Module
Extends MobilWheel's vJoy integration with Forza Horizon 6-specific button mapping.

Protocol commands from Android:
  A:<float>     - Steering (-10.0 to +10.0)
  B:<0-100>     - Throttle (Gas pedal)
  C:<0-100>     - Brake pedal
  D             - HANDBRAKE      (vJoy btn 1 = A button)
  E             - SHIFT DOWN     (vJoy btn 5 = LB)
  F             - SHIFT UP       (vJoy btn 6 = RB)
  G             - HORN           (vJoy btn 4 = Y)
  H             - LOOK BACK      (vJoy btn 9 = Back)
  I             - CAMERA CHANGE  (vJoy btn 2 = B)
  J             - REWIND         (vJoy btn 3 = X)
  K             - CLUTCH PRESS   (vJoy btn 7)
  VOLUME_UP     - RECALIBRATE    (handled on Android side only)
  VOLUME_DOWN   - HORN shortcut  (same as G)

vJoy Axis IDs (HID usage page):
  0x30 = X  -> Steering
  0x31 = Y  -> Throttle
  0x32 = Z  -> Brake
  0x33 = Rx -> Clutch

vJoy Button IDs -> Forza XInput mapping:
  1  = A     (Handbrake)
  2  = B     (Camera Change)
  3  = X     (Rewind)
  4  = Y     (Horn)
  5  = LB    (Shift Down)
  6  = RB    (Shift Up)
  7  = Clutch / reserved
  9  = Back  (Look Back)
  10 = Start (Pause/Menu)
  11 = LSB   (Look Left)
  12 = RSB   (Look Right)
"""

import socket
import ctypes
import time
import struct
import os
import sys
import platform
import logging
import threading
import signal
from collections import deque

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

IS_WINDOWS = platform.system() == 'Windows'
IS_LINUX   = platform.system() == 'Linux'

# ─── vJoy / uinput setup ────────────────────────────────────────────────────
vjoy = None
uinput_devices = {}

if IS_WINDOWS:
    is_64bits = struct.calcsize("P") * 8 == 64
    if getattr(sys, 'frozen', False):
        base_dir = sys._MEIPASS
    else:
        base_dir = os.path.dirname(__file__)

    dll_path = os.path.join(base_dir, 'vJoy', 'x64' if is_64bits else 'x86', 'vJoyInterface.dll')
    if not os.path.isfile(dll_path):
        raise FileNotFoundError(f"vJoy DLL not found at '{dll_path}'. Please install vJoy.")

    vjoy = ctypes.WinDLL(dll_path)
    VJD_STAT_OWN  = 0
    VJD_STAT_FREE = 1
    VJD_STAT_BUSY = 2
    VJD_STAT_MISS = 3
    VJD_STAT_UNKN = 4

    vjoy.AcquireVJD.argtypes   = [ctypes.c_uint]; vjoy.AcquireVJD.restype   = ctypes.c_bool
    vjoy.RelinquishVJD.argtypes= [ctypes.c_uint]; vjoy.RelinquishVJD.restype= ctypes.c_bool
    vjoy.SetBtn.argtypes       = [ctypes.c_bool, ctypes.c_uint, ctypes.c_uint]; vjoy.SetBtn.restype = ctypes.c_bool
    vjoy.SetAxis.argtypes      = [ctypes.c_long, ctypes.c_uint, ctypes.c_uint]; vjoy.SetAxis.restype= ctypes.c_bool
    vjoy.GetVJDStatus.argtypes = [ctypes.c_uint]; vjoy.GetVJDStatus.restype = ctypes.c_int

elif IS_LINUX:
    try:
        import evdev
        from evdev import UInput, AbsInfo, ecodes
    except ImportError:
        logging.error("evdev not installed. Install with: pip install evdev")
        raise

# ─── vJoy axis IDs ───────────────────────────────────────────────────────────
AXIS_STEERING  = 0x30   # X
AXIS_THROTTLE  = 0x31   # Y
AXIS_BRAKE     = 0x32   # Z
AXIS_CLUTCH    = 0x33   # Rx

# vJoy range: 0x00001 – 0x7FFF (1 – 32767), center = 16384
VJOY_MIN    =     1
VJOY_MAX    = 32767
VJOY_CENTER = 16384

# ─── Button mapping — Forza Horizon XInput layout ────────────────────────────
# Forza uses standard XInput:
#   A=1  B=2  X=3  Y=4  LB=5  RB=6  Back/View=9  Start=10  LSB=11  RSB=12
BTN_HANDBRAKE  = 1    # A        → Handbrake
BTN_CAMERA     = 2    # B        → Camera Change / Look Back (held)
BTN_REWIND     = 3    # X        → Rewind
BTN_HORN       = 4    # Y        → Horn / Headlights
BTN_SHIFT_DOWN = 5    # LB       → Shift Down (manual)
BTN_SHIFT_UP   = 6    # RB       → Shift Up (manual)
BTN_VIEW       = 9    # Back/View → Anna assistant / View menu
BTN_PAUSE      = 10   # Start     → Pause menu
BTN_LSB        = 11   # LSB       → Look Left (can rebind)
BTN_RSB        = 12   # RSB       → Look Back (can rebind)
# D-pad → buttons 13-16 (bind in Forza custom controls)
BTN_DPAD_UP    = 13
BTN_DPAD_DOWN  = 14
BTN_DPAD_LEFT  = 15
BTN_DPAD_RIGHT = 16

# ─── Protocol command → action description ────────────────────────────────────
# Analog axes:  A=steering  B=throttle  C=brake
# Clutch:       CLUTCH_ON (hold) / CLUTCH_OFF (release) → AXIS_CLUTCH
# Buttons:      D,E,F,G,H,I,J — see btn_map in process_critical_message
COMMAND_MAP = {
    'A': 'steering',
    'B': 'throttle',
    'C': 'brake',
    'D': 'handbrake',     # A  button → Handbrake
    'E': 'shift_down',    # LB button → Shift Down
    'F': 'shift_up',      # RB button → Shift Up
    'G': 'horn',          # Y  button → Horn
    'H': 'look_back',     # RSB       → Look Back
    'I': 'camera',        # B  button → Camera Change
    'J': 'rewind',        # X  button → Rewind
    'CLUTCH_ON':  'clutch_on',
    'CLUTCH_OFF': 'clutch_off',
    'BACK_BTN':   'view',       # View/Back → Anna
    'START':      'pause',
    'ANNA':       'view',       # same as BACK_BTN
    'DPAD_U':     'dpad_up',
    'DPAD_D':     'dpad_down',
    'DPAD_L':     'dpad_left',
    'DPAD_R':     'dpad_right',
    'VOLUME_DOWN': 'horn',
}

# ─── State tracking ───────────────────────────────────────────────────────────
available_devices = [1, 2]
device_lock       = threading.Lock()
device_states     = {}
acquired_devices  = set()
KEEP_DEVICE_ON_DISCONNECT = True

shutdown_event = threading.Event()

# ─── vJoy acquire/release ─────────────────────────────────────────────────────
def acquire_vjd(device_id):
    if IS_WINDOWS: return _acquire_vjd_windows(device_id)
    if IS_LINUX:   return _acquire_vjd_linux(device_id)
    return False

def _acquire_vjd_windows(device_id):
    if device_id in acquired_devices:
        return True
    for _ in range(5):
        status = vjoy.GetVJDStatus(device_id)
        if status in (VJD_STAT_FREE, VJD_STAT_OWN):
            if vjoy.AcquireVJD(device_id):
                logging.info(f"vJoy device {device_id} acquired.")
                # Center all axes
                set_axis(device_id, AXIS_STEERING, VJOY_CENTER)
                set_axis(device_id, AXIS_THROTTLE, VJOY_MIN)
                set_axis(device_id, AXIS_BRAKE,    VJOY_MIN)
                set_axis(device_id, AXIS_CLUTCH,   VJOY_MIN)
                acquired_devices.add(device_id)
                return True
            return False
        relinquish_vjd(device_id)
        time.sleep(0.5)
    return False

def _acquire_vjd_linux(device_id):
    try:
        if device_id in uinput_devices:
            acquired_devices.add(device_id); return True
        cap = {
            ecodes.EV_KEY: [ecodes.BTN_TRIGGER, ecodes.BTN_THUMB, ecodes.BTN_THUMB2,
                            ecodes.BTN_TOP, ecodes.BTN_TOP2, ecodes.BTN_PINKIE,
                            ecodes.BTN_BASE, ecodes.BTN_BASE2, ecodes.BTN_BASE3,
                            ecodes.BTN_BASE4, ecodes.BTN_BASE5, ecodes.BTN_BASE6],
            ecodes.EV_ABS: [
                (ecodes.ABS_X, AbsInfo(16384, 0, 32767, 0, 0, 0)),
                (ecodes.ABS_Y, AbsInfo(0,     0, 32767, 0, 0, 0)),
                (ecodes.ABS_Z, AbsInfo(0,     0, 32767, 0, 0, 0)),
                (ecodes.ABS_RX,AbsInfo(0,     0, 32767, 0, 0, 0)),
            ],
        }
        dev = UInput(cap, name=f'ForzaWheel-{device_id}', version=0x1)
        uinput_devices[device_id] = dev
        acquired_devices.add(device_id)
        return True
    except Exception as e:
        logging.error(f"Linux uinput failed: {e}"); return False

def relinquish_vjd(device_id):
    if IS_WINDOWS: _relinquish_vjd_windows(device_id)
    if IS_LINUX:   _relinquish_vjd_linux(device_id)

def _relinquish_vjd_windows(device_id):
    try:
        for _ in range(3):
            if vjoy.RelinquishVJD(device_id):
                acquired_devices.discard(device_id); break
            time.sleep(0.1)
    except Exception as e:
        logging.error(f"RelinquishVJD error: {e}")

def _relinquish_vjd_linux(device_id):
    try:
        if device_id in uinput_devices:
            uinput_devices[device_id].close()
            del uinput_devices[device_id]
            acquired_devices.discard(device_id)
    except Exception as e:
        logging.error(f"Linux release error: {e}")

# ─── Axis & button setters ───────────────────────────────────────────────────
def set_axis(device_id, axis_id, value):
    if IS_WINDOWS:
        vjoy.SetAxis(int(value), device_id, axis_id)
    elif IS_LINUX and device_id in uinput_devices:
        axis_map = {0x30: ecodes.ABS_X, 0x31: ecodes.ABS_Y,
                    0x32: ecodes.ABS_Z, 0x33: ecodes.ABS_RX}
        if axis_id in axis_map:
            dev = uinput_devices[device_id]
            dev.write(ecodes.EV_ABS, axis_map[axis_id], int(value))
            dev.syn()

def set_button(device_id, button_id, state):
    if IS_WINDOWS:
        vjoy.SetBtn(state, device_id, button_id)
    elif IS_LINUX and device_id in uinput_devices:
        btn_map = {1: ecodes.BTN_TRIGGER, 2: ecodes.BTN_THUMB, 3: ecodes.BTN_THUMB2,
                   4: ecodes.BTN_TOP, 5: ecodes.BTN_TOP2, 6: ecodes.BTN_PINKIE,
                   9: ecodes.BTN_BASE3, 10: ecodes.BTN_BASE4,
                   11: ecodes.BTN_BASE5, 12: ecodes.BTN_BASE6}
        if button_id in btn_map:
            dev = uinput_devices[device_id]
            dev.write(ecodes.EV_KEY, btn_map[button_id], 1 if state else 0)
            dev.syn()

def pulse_button(device_id, button_id, duration_ms=80):
    """Press and release a button after duration_ms."""
    set_button(device_id, button_id, True)
    threading.Timer(duration_ms / 1000.0, set_button, args=(device_id, button_id, False)).start()

def zero_all(device_id):
    """Failsafe: release all inputs to zero/center."""
    set_axis(device_id, AXIS_STEERING, VJOY_CENTER)
    set_axis(device_id, AXIS_THROTTLE, VJOY_MIN)
    set_axis(device_id, AXIS_BRAKE,    VJOY_MIN)
    set_axis(device_id, AXIS_CLUTCH,   VJOY_MIN)
    for btn in [BTN_HANDBRAKE, BTN_CAMERA, BTN_REWIND, BTN_HORN,
                BTN_SHIFT_DOWN, BTN_SHIFT_UP, BTN_LOOK_BACK,
                BTN_PAUSE, BTN_LOOK_LEFT, BTN_LOOK_RIGHT]:
        set_button(device_id, btn, False)

# ─── Value mapping ────────────────────────────────────────────────────────────
def map_value(value, in_min, in_max, out_min, out_max):
    value = max(min(value, in_max), in_min)
    return int((value - in_min) * (out_max - out_min) / (in_max - in_min) + out_min)

def map_steering(server_value):
    """Map steering from Android range (-10 to +10) to vJoy (1 to 32767)."""
    return map_value(server_value, -10.0, 10.0, VJOY_MIN, VJOY_MAX)

def map_pedal(percent_0_100):
    """Map pedal 0–100 to vJoy 1–32767."""
    return map_value(percent_0_100, 0, 100, VJOY_MIN, VJOY_MAX)

# ─── Message processing ───────────────────────────────────────────────────────
def process_critical_message(device_id, message, update_ui_callback=None):
    """Handle button presses and clutch axis control."""
    command = message.strip()
    logging.debug(f"Critical: {command}")

    # Clutch — axis-based (hold = engaged, release = disengaged)
    if command == 'CLUTCH_ON':
        set_axis(device_id, AXIS_CLUTCH, VJOY_MAX)
        if update_ui_callback: update_ui_callback('clutch', 100)
        return
    if command == 'CLUTCH_OFF':
        set_axis(device_id, AXIS_CLUTCH, VJOY_MIN)
        if update_ui_callback: update_ui_callback('clutch', 0)
        return

    # Button commands → vJoy button IDs
    # NOTE on look-back vs Anna:
    #   H  → RSB (btn 12) = Look Back while driving
    #   BACK_BTN / ANNA → View/Back (btn 9) = Anna assistant
    btn_map = {
        'D':         BTN_HANDBRAKE,  # A   → Handbrake
        'E':         BTN_SHIFT_DOWN, # LB  → Shift Down
        'F':         BTN_SHIFT_UP,   # RB  → Shift Up
        'G':         BTN_HORN,       # Y   → Horn
        'H':         BTN_RSB,        # RSB → Look Back (hold B / RSB in Forza)
        'I':         BTN_CAMERA,     # B   → Camera Change
        'J':         BTN_REWIND,     # X   → Rewind
        'BACK_BTN':  BTN_VIEW,       # View/Back → Anna
        'ANNA':      BTN_VIEW,       # View/Back → Anna (alias)
        'START':     BTN_PAUSE,      # Start → Pause
        'DPAD_U':    BTN_DPAD_UP,
        'DPAD_D':    BTN_DPAD_DOWN,
        'DPAD_L':    BTN_DPAD_LEFT,
        'DPAD_R':    BTN_DPAD_RIGHT,
        'VOLUME_DOWN': BTN_HORN,     # Volume down → Horn
    }

    if command in btn_map:
        btn_id = btn_map[command]
        btn_name = COMMAND_MAP.get(command, command.lower())
        pulse_button(device_id, btn_id, 80)
        logging.info(f"Button {command} → vJoy btn {btn_id} ({btn_name})")
        if update_ui_callback:
            update_ui_callback(btn_name, True)
            threading.Timer(0.1, update_ui_callback, args=(btn_name, False)).start()


def process_non_critical_message(device_id, message, update_ui_callback=None):
    """Handle analog inputs (A=steering, B=throttle, C=brake)."""
    state = device_states.get(device_id)
    if not state: return

    parts = message.strip().split(":")
    if len(parts) != 2: return
    command, value_str = parts[0], parts[1]

    try:
        if command == 'A':  # Steering
            y = float(value_str)
            steering_value = map_steering(y)
            state['last_steering'] = steering_value
            set_axis(device_id, AXIS_STEERING, steering_value)
            if update_ui_callback:
                update_ui_callback('steering', steering_value)

        elif command == 'B':  # Throttle
            pct = int(value_str)
            axis_val = map_pedal(pct)
            set_axis(device_id, AXIS_THROTTLE, axis_val)
            if update_ui_callback:
                update_ui_callback('throttle', pct)

        elif command == 'C':  # Brake
            pct = int(value_str)
            axis_val = map_pedal(pct)
            set_axis(device_id, AXIS_BRAKE, axis_val)
            if update_ui_callback:
                update_ui_callback('brake', pct)

    except (ValueError, TypeError) as e:
        logging.error(f"Value error processing '{message}': {e}")

# ─── Client handler threads ───────────────────────────────────────────────────
def handle_critical_messages(device_id, update_ui_callback=None):
    while not shutdown_event.is_set():
        try:
            state = device_states.get(device_id)
            if state is None: break
            if state['critical_queue']:
                process_critical_message(device_id, state['critical_queue'].popleft(), update_ui_callback)
            else:
                time.sleep(0.001)
        except (KeyError, IndexError):
            break

def handle_non_critical_messages(device_id, update_ui_callback=None):
    while not shutdown_event.is_set():
        try:
            state = device_states.get(device_id)
            if state is None: break
            processed = 0
            while state['non_critical_queue'] and processed < 20:
                process_non_critical_message(device_id, state['non_critical_queue'].popleft(), update_ui_callback)
                processed += 1
            if processed == 0:
                time.sleep(0.001)
        except (KeyError, IndexError):
            break

def handle_client(conn, addr, update_ui_callback=None):
    logging.info(f"Client connected: {addr}")
    device_id = None

    if acquire_vjd(1):   device_id = 1
    elif acquire_vjd(2): device_id = 2
    else:
        logging.error("No vJoy device available.")
        conn.close(); return

    device_states[device_id] = {
        'critical_queue':     deque(),
        'non_critical_queue': deque(),
        'last_steering':      VJOY_CENTER,
    }

    t_crit = threading.Thread(target=handle_critical_messages,     args=(device_id, update_ui_callback), daemon=True)
    t_ncrit= threading.Thread(target=handle_non_critical_messages, args=(device_id, update_ui_callback), daemon=True)
    t_crit.start(); t_ncrit.start()

    # ── Failsafe watchdog ────────────────────────────────────────────────────
    last_packet_time = [time.time()]
    STALE_TIMEOUT = 0.5  # seconds

    def failsafe_watchdog():
        while not shutdown_event.is_set() and device_id in device_states:
            if time.time() - last_packet_time[0] > STALE_TIMEOUT:
                zero_all(device_id)
                if update_ui_callback:
                    update_ui_callback('steering', VJOY_CENTER)
                    update_ui_callback('throttle', 0)
                    update_ui_callback('brake', 0)
            time.sleep(0.1)

    t_watchdog = threading.Thread(target=failsafe_watchdog, daemon=True)
    t_watchdog.start()

    try:
        with conn:
            buffer = ""
            conn.settimeout(5.0)
            while not shutdown_event.is_set():
                try:
                    data = conn.recv(8192).decode('utf-8', errors='ignore')
                    if not data: break
                    last_packet_time[0] = time.time()
                    buffer += data
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        msg = line.strip()
                        if not msg: continue
                        cmd = msg.split(':')[0]
                        # ── Route to correct queue ──────────────────────────────
                        # Non-critical: analog axes with float/int value (A, B, C)
                        # Critical: all button presses (single OR multi-word commands)
                        ANALOG_CMDS = {'A', 'B', 'C'}
                        if cmd in ANALOG_CMDS:
                            device_states[device_id]['non_critical_queue'].append(msg)
                        else:
                            device_states[device_id]['critical_queue'].append(msg)
                except socket.timeout:
                    if shutdown_event.is_set(): break
    except Exception as e:
        logging.error(f"Client error: {e}")
    finally:
        zero_all(device_id)
        logging.info(f"Client {addr} disconnected. Inputs zeroed.")
        if device_id in device_states:
            del device_states[device_id]
        if not KEEP_DEVICE_ON_DISCONNECT:
            relinquish_vjd(device_id)
        try:
            conn.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        conn.close()

# ─── Discovery handler ────────────────────────────────────────────────────────
def get_local_ip_for_client(client_ip):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1)
        s.connect((client_ip, 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None

def handle_discovery(sock_udp):
    while not shutdown_event.is_set():
        try:
            sock_udp.settimeout(1.0)
            msg, addr = sock_udp.recvfrom(1024)
            if msg.decode('utf-8', errors='ignore').strip() == "DISCOVER_SERVER":
                server_ip = get_local_ip_for_client(addr[0])
                if server_ip:
                    response = f"{server_ip}:12345"
                    sock_udp.sendto(response.encode(), addr)
                    logging.info(f"Discovery: replied to {addr} with {server_ip}")
        except socket.timeout:
            continue
        except OSError:
            break

# ─── Main server entry point ──────────────────────────────────────────────────
def start_server(update_ui_callback=None):
    HOST = "0.0.0.0"
    PORT = 12345

    shutdown_event.clear()

    sock_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock_tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock_tcp.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    sock_tcp.bind((HOST, PORT))
    sock_tcp.listen(5)
    logging.info(f"TCP server listening on {HOST}:{PORT}")

    sock_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock_udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock_udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock_udp.bind((HOST, PORT))
    logging.info(f"UDP discovery listening on {HOST}:{PORT}")

    t_disc = threading.Thread(target=handle_discovery, args=(sock_udp,), daemon=True)
    t_disc.start()

    try:
        while not shutdown_event.is_set():
            sock_tcp.settimeout(1.0)
            try:
                conn, addr = sock_tcp.accept()
                conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                conn.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
                conn.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
                t = threading.Thread(target=handle_client, args=(conn, addr, update_ui_callback), daemon=True)
                t.start()
            except socket.timeout:
                continue
    finally:
        shutdown_event.set()
        for s in (sock_tcp, sock_udp):
            try: s.close()
            except: pass
        cleanup_devices()
        logging.info("Server stopped.")

def cleanup_devices():
    for dev_id in list(acquired_devices):
        try: relinquish_vjd(dev_id)
        except: pass

signal.signal(signal.SIGINT, lambda s, f: shutdown_event.set())
