"""
ForzaWheel Controller Module
Extends MobilWheel's logic to natively emulate an Xbox 360 controller using ViGEmBus.

Protocol commands from Android:
  A:<float>     - Steering (-10.0 to +10.0)
  B:<0-100>     - Throttle (Gas pedal)
  C:<0-100>     - Brake pedal
  D             - HANDBRAKE      (A button)
  E             - SHIFT DOWN     (LB)
  F             - SHIFT UP       (RB)
  G             - HORN           (Y)
  H             - LOOK BACK      (RSB)
  I             - CAMERA CHANGE  (B)
  J             - REWIND         (X)
  K             - CLUTCH PRESS   (Not natively analog in X360, can map to a button)
  VOLUME_UP     - RECALIBRATE    (handled on Android side only)
  VOLUME_DOWN   - HORN shortcut  (same as G)
"""

import socket
import threading
import time
import logging
import math
from collections import deque

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

VIGEM_AVAILABLE = False
try:
    from virtual_gamepad import VX360Gamepad
    from vigem_commons import XUSB_BUTTON
    VIGEM_AVAILABLE = True
except Exception as e:
    logging.error(f"ViGEm modules could not be loaded: {e}")

# ─── State tracking ───────────────────────────────────────────────────────────
available_devices = [1, 2]
device_lock       = threading.Lock()
device_states     = {}
acquired_devices  = set()
KEEP_DEVICE_ON_DISCONNECT = True

shutdown_event = threading.Event()

# Global gamepad instance
gamepad = None

# ─── ViGEm acquire/release ────────────────────────────────────────────────────
def acquire_vjd(device_id):
    global gamepad
    if not VIGEM_AVAILABLE:
        logging.error("Cannot acquire device: ViGEm is not available.")
        return False
    
    if device_id in acquired_devices:
        return True

    try:
        if gamepad is None:
            gamepad = VX360Gamepad()
            gamepad.reset()
            gamepad.update()
        acquired_devices.add(device_id)
        logging.info(f"ViGEm Virtual Xbox Controller acquired (Assigned to ID {device_id}).")
        return True
    except Exception as e:
        logging.error(f"Failed to acquire ViGEm device (Is ViGEmBus installed?): {e}")
        return False

def relinquish_vjd(device_id):
    global gamepad
    try:
        acquired_devices.discard(device_id)
        if len(acquired_devices) == 0 and gamepad is not None:
            gamepad.reset()
            gamepad.update()
            # Note: We don't delete the gamepad object so we can reuse the bus connection
    except Exception as e:
        logging.error(f"Relinquish error: {e}")

# ─── Axis & button setters ───────────────────────────────────────────────────
def set_steering(server_value):
    if gamepad is None: return
    # Android value: -10.0 (Left) to +10.0 (Right)
    # XInput value: -32768 to 32767
    clamped = max(-10.0, min(10.0, float(server_value)))
    val = int((clamped / 10.0) * 32767)
    gamepad.left_joystick(x_value=val, y_value=0)
    gamepad.update()

def set_gas(percent_0_100):
    if gamepad is None: return
    # XInput RT: 0 to 255
    clamped = max(0, min(100, int(percent_0_100)))
    val = int((clamped / 100.0) * 255)
    gamepad.right_trigger(value=val)
    gamepad.update()

def set_brake(percent_0_100):
    if gamepad is None: return
    # XInput LT: 0 to 255
    clamped = max(0, min(100, int(percent_0_100)))
    val = int((clamped / 100.0) * 255)
    gamepad.left_trigger(value=val)
    gamepad.update()

def set_button(button_flag, state):
    if gamepad is None: return
    if state:
        gamepad.press_button(button=button_flag)
    else:
        gamepad.release_button(button=button_flag)
    gamepad.update()

def pulse_button(button_flag, duration_ms):
    set_button(button_flag, True)
    threading.Timer(duration_ms / 1000.0, set_button, args=(button_flag, False)).start()

def zero_all(device_id):
    if gamepad is not None:
        gamepad.reset()
        gamepad.update()

# ─── Protocol mapping ────────────────────────────────────────────────────────
COMMAND_MAP = {
    'A': 'steering',
    'B': 'throttle',
    'C': 'brake',
    'D': 'handbrake',
    'E': 'shift_down',
    'F': 'shift_up',
    'G': 'horn',
    'H': 'look_back',
    'I': 'camera',
    'J': 'rewind',
    'CLUTCH_ON':  'clutch_on',
    'CLUTCH_OFF': 'clutch_off',
    'BACK_BTN':   'view',
    'START':      'pause',
    'ANNA':       'view',
    'DPAD_U':     'dpad_up',
    'DPAD_D':     'dpad_down',
    'DPAD_L':     'dpad_left',
    'DPAD_R':     'dpad_right',
    'VOLUME_DOWN': 'horn',
}

def get_button_flag(command):
    if not VIGEM_AVAILABLE: return None
    mapping = {
        'D':         XUSB_BUTTON.XUSB_GAMEPAD_A,              # Handbrake
        'E':         XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER,  # Shift Down
        'F':         XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER, # Shift Up
        'G':         XUSB_BUTTON.XUSB_GAMEPAD_Y,              # Horn
        'H':         XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_THUMB,    # Look Back (RSB)
        'I':         XUSB_BUTTON.XUSB_GAMEPAD_B,              # Camera
        'J':         XUSB_BUTTON.XUSB_GAMEPAD_X,              # Rewind
        'BACK_BTN':  XUSB_BUTTON.XUSB_GAMEPAD_BACK,           # View/Anna
        'ANNA':      XUSB_BUTTON.XUSB_GAMEPAD_BACK,
        'START':     XUSB_BUTTON.XUSB_GAMEPAD_START,          # Pause
        'DPAD_U':    XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP,
        'DPAD_D':    XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN,
        'DPAD_L':    XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT,
        'DPAD_R':    XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT,
        'VOLUME_DOWN': XUSB_BUTTON.XUSB_GAMEPAD_Y,            # Horn
        
        # We map clutch to Left Thumb button (LSB) as a fallback since X360 has no 3rd analog trigger
        'CLUTCH_ON': XUSB_BUTTON.XUSB_GAMEPAD_LEFT_THUMB,
        'CLUTCH_OFF': XUSB_BUTTON.XUSB_GAMEPAD_LEFT_THUMB,
    }
    return mapping.get(command)

def process_critical_message(device_id, message, update_ui_callback=None):
    command = message.strip()
    logging.debug(f"Critical: {command}")

    if command == 'CLUTCH_ON':
        btn_flag = get_button_flag('CLUTCH_ON')
        if btn_flag: set_button(btn_flag, True)
        if update_ui_callback: update_ui_callback('clutch', 100)
        return
    if command == 'CLUTCH_OFF':
        btn_flag = get_button_flag('CLUTCH_OFF')
        if btn_flag: set_button(btn_flag, False)
        if update_ui_callback: update_ui_callback('clutch', 0)
        return

    btn_flag = get_button_flag(command)
    if btn_flag:
        btn_name = COMMAND_MAP.get(command, command.lower())
        pulse_button(btn_flag, 80)
        logging.info(f"Button {command} → {btn_name}")
        if update_ui_callback:
            update_ui_callback(btn_name, True)
            threading.Timer(0.1, update_ui_callback, args=(btn_name, False)).start()

def process_non_critical_message(device_id, message, update_ui_callback=None):
    state = device_states.get(device_id)
    if not state: return

    parts = message.strip().split(":")
    if len(parts) != 2: return
    command, value_str = parts[0], parts[1]

    try:
        if command == 'A':
            y = float(value_str)
            state['last_steering'] = y
            set_steering(y)
            if update_ui_callback:
                # Map -10/10 to 0-32767 for UI consistency with old code
                ui_val = int(((y + 10.0) / 20.0) * 32767)
                update_ui_callback('steering', ui_val)

        elif command == 'B':
            pct = int(value_str)
            set_gas(pct)
            if update_ui_callback:
                update_ui_callback('throttle', pct)

        elif command == 'C':
            pct = int(value_str)
            set_brake(pct)
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
                time.sleep(0.005)
        except Exception as e:
            logging.error(f"Critical thread error: {e}")
            time.sleep(0.1)

def handle_non_critical_messages(device_id, update_ui_callback=None):
    while not shutdown_event.is_set():
        try:
            state = device_states.get(device_id)
            if state is None: break
            if state['non_critical_queue']:
                msg = state['non_critical_queue'].popleft()
                state['non_critical_queue'].clear()
                process_non_critical_message(device_id, msg, update_ui_callback)
            else:
                time.sleep(0.01)
        except Exception as e:
            logging.error(f"Non-critical thread error: {e}")
            time.sleep(0.1)

def handle_client(conn, addr, device_id, update_ui_callback=None, connection_callback=None):
    logging.info(f"Assigned {addr} to device {device_id}")
    if connection_callback:
        connection_callback(device_id, True)
    
    with device_lock:
        device_states[device_id] = {
            'critical_queue': deque(),
            'non_critical_queue': deque(),
            'last_steering': 0.0
        }

    critical_thread = threading.Thread(target=handle_critical_messages, args=(device_id, update_ui_callback), daemon=True)
    non_critical_thread = threading.Thread(target=handle_non_critical_messages, args=(device_id, update_ui_callback), daemon=True)
    critical_thread.start()
    non_critical_thread.start()

    conn.settimeout(2.0)
    buffer = ""

    try:
        while not shutdown_event.is_set():
            try:
                data = conn.recv(1024)
                if not data: break
                buffer += data.decode('utf-8', errors='ignore')

                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    line = line.strip()
                    if not line: continue
                    
                    if line in COMMAND_MAP or line.startswith('CLUTCH_'):
                        device_states[device_id]['critical_queue'].append(line)
                    elif line.startswith(('A:', 'B:', 'C:')):
                        device_states[device_id]['non_critical_queue'].append(line)

            except socket.timeout:
                continue
            except Exception as e:
                logging.error(f"Socket error device {device_id}: {e}")
                break
    finally:
        logging.info(f"Client {addr} disconnected from device {device_id}")
        conn.close()
        
        if not KEEP_DEVICE_ON_DISCONNECT:
            relinquish_vjd(device_id)
            zero_all(device_id)
            
        with device_lock:
            if device_id in device_states:
                del device_states[device_id]
            available_devices.append(device_id)
            available_devices.sort()

        if connection_callback:
            connection_callback(device_id, False)

def start_server(host='0.0.0.0', port=12345, update_ui_callback=None, connection_callback=None):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server_socket.bind((host, port))
        server_socket.listen(2)
        server_socket.settimeout(1.0)
        logging.info(f"TCP server listening on {host}:{port}")

        while not shutdown_event.is_set():
            try:
                conn, addr = server_socket.accept()
                logging.info(f"Client connected from {addr}")

                device_id = None
                with device_lock:
                    if available_devices:
                        device_id = available_devices.pop(0)

                if device_id:
                    if acquire_vjd(device_id):
                        client_thread = threading.Thread(
                            target=handle_client,
                            args=(conn, addr, device_id, update_ui_callback, connection_callback),
                            daemon=True
                        )
                        client_thread.start()
                    else:
                        logging.error(f"Failed to acquire device {device_id}. Rejecting {addr}")
                        conn.close()
                        with device_lock:
                            available_devices.append(device_id)
                            available_devices.sort()
                else:
                    logging.warning(f"No available devices. Rejecting {addr}")
                    conn.close()
            except socket.timeout:
                continue
            except Exception as e:
                if not shutdown_event.is_set():
                    logging.error(f"Accept error: {e}")
                    
    finally:
        server_socket.close()
        logging.info("Server socket closed.")

def shutdown_server():
    logging.info("Shutting down server...")
    shutdown_event.set()
    
    # Release all devices cleanly
    for dev_id in list(acquired_devices):
        relinquish_vjd(dev_id)
    if gamepad is not None:
        try:
            gamepad.reset()
            gamepad.update()
        except:
            pass
    logging.info("Shutdown complete.")
