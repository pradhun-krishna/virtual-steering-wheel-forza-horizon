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

VJOY_AVAILABLE = False
try:
    import pyvjoy
    VJOY_AVAILABLE = True
except Exception as e:
    logging.warning(f"pyvjoy could not be loaded: {e}. Steering wheel bypass requires vJoy driver.")

# ─── State tracking ───────────────────────────────────────────────────────────
class DeviceState:
    def __init__(self):
        self.steering = 0.0
        self.gas = 0.0
        self.brake = 0.0
        self.rx = 0.0
        self.ry = 0.0
        self.critical_queue = deque()
        self.non_critical_queue = deque()

available_devices = [1, 2]
device_lock       = threading.Lock()
device_states     = {}
acquired_devices  = set()
KEEP_DEVICE_ON_DISCONNECT = True

shutdown_event = threading.Event()

# Global gamepad instances
gamepad = None
vj = None

# ─── ViGEm acquire/release ────────────────────────────────────────────────────

def acquire_vjd(device_id=1):
    global gamepad, vj
    
    if gamepad is None and VIGEM_AVAILABLE:
        gamepad = VX360Gamepad()
        gamepad.reset()
        gamepad.update()

    if not VJOY_AVAILABLE:
        if device_id in acquired_devices: return True
        acquired_devices.add(device_id)
        logging.info(f"ViGEm Virtual Xbox Controller acquired (Assigned to ID {device_id}).")
        return True
        
    try:
        if pyvjoy._sdk.vJoyEnabled():
            vj = pyvjoy.VJoyDevice(device_id)
            # Initialize all axes to dead center (16384) instead of 0 (-100%)
            vj.data.wAxisX = 16384
            vj.data.wAxisY = 16384
            vj.data.wAxisZ = 16384
            vj.data.wAxisXRot = 16384
            vj.data.wAxisYRot = 16384
            vj.data.wAxisZRot = 16384
            vj.data.wSlider = 16384
            vj.data.wDial = 16384
            vj.data.lButtons = 0
            vj.update()
            logging.info("vJoy Virtual Steering Wheel acquired.")
            acquired_devices.add(device_id)
            return True
    except Exception as e:
        logging.warning(f"Could not open vJoy Device {device_id}: {e}")
        vj = None
    return False

def relinquish_vjd(device_id):
    global gamepad, vj
    try:
        acquired_devices.discard(device_id)
        if len(acquired_devices) == 0 and gamepad is not None:
            gamepad.reset()
            gamepad.update()
    except Exception as e:
        logging.error(f"Relinquish error: {e}")

# ─── Axis & button setters ───────────────────────────────────────────────────
mapping_mode = False

def set_mapping_mode(enabled):
    global mapping_mode
    mapping_mode = enabled
    if vj:
        try:
            if enabled:
                # Lock resting state to 50% to avoid Forza auto-detecting
                vj.data.wAxisX = 16384
                vj.data.wAxisXRot = 16384
                vj.data.wAxisYRot = 16384
                # Also force gas/brake to rest at 50% when mapping mode turns on
                vj.data.wAxisY = 16384
                vj.data.wAxisZ = 16384
                vj.data.wAxisZRot = 16384
            else:
                # Restore full pedal range resting state (0%)
                vj.data.wAxisY = 0
                vj.data.wAxisZ = 0
                vj.data.wAxisZRot = 0
            vj.update()
        except: pass

last_smoothed_steering = 16384.0

def set_steering(server_value):
    global last_smoothed_steering
    if mapping_mode:
        last_smoothed_steering = 16384.0
        return
    clamped = max(-10.0, min(10.0, float(server_value)))
    
    # Small deadzone so resting the phone perfectly straight is easy
    if abs(clamped) < 0.2:
        clamped = 0.0
        
    if vj:
        target_val = ((clamped + 10.0) / 20.0) * 32768
        
        # Adaptive Exponential Moving Average (EMA) for flawless motion
        diff = abs(target_val - last_smoothed_steering)
        if diff < 30:
            smoothed_val = target_val # Snap when extremely close to prevent floating
        else:
            if diff < 200:
                alpha = 0.05 # Extreme smoothing for micro-jitters (hand shake)
            elif diff < 800:
                alpha = 0.20 # Medium smoothing for slight adjustments
            else:
                alpha = 0.45 # Fast response for sharp, intentional turns
            smoothed_val = (alpha * target_val) + ((1.0 - alpha) * last_smoothed_steering)
            
        last_smoothed_steering = smoothed_val
        
        try:
            vj.data.wAxisX = int(smoothed_val)
            vj.update()
        except: pass
    elif gamepad:
        val = int((clamped / 10.0) * 32767)
        gamepad.left_joystick(x_value=val, y_value=0)
        gamepad.update()

def set_gas(percent_0_100):
    clamped = max(0, min(100, int(percent_0_100)))
    if vj:
        if mapping_mode:
            val = int(16384 + (clamped / 100.0) * 16384)
        else:
            val = int((clamped / 100.0) * 32768)
        try:
            vj.data.wAxisY = val
            vj.update()
        except: pass
    elif gamepad:
        val = int((clamped / 100.0) * 255)
        gamepad.right_trigger(value=val)
        gamepad.update()

def set_brake(percent_0_100):
    clamped = max(0, min(100, int(percent_0_100)))
    if vj:
        if mapping_mode:
            val = int(16384 + (clamped / 100.0) * 16384)
        else:
            val = int((clamped / 100.0) * 32768)
        try:
            vj.data.wAxisZ = val
            vj.update()
        except: pass
    elif gamepad:
        val = int((clamped / 100.0) * 255)
        gamepad.left_trigger(value=val)
        gamepad.update()

def set_clutch(percent_0_100):
    clamped = max(0, min(100, int(percent_0_100)))
    if vj:
        if mapping_mode:
            val = int(16384 + (clamped / 100.0) * 16384)
        else:
            val = int((clamped / 100.0) * 32768)
        try:
            vj.data.wAxisZRot = val
            vj.update()
        except: pass
    elif gamepad:
        val = int((clamped / 100.0) * 255)
        gamepad.left_trigger(value=val)
        gamepad.update()

def set_right_joystick(x_pct, y_pct):
    # Convert joystick swipes into discrete button presses (Buttons 10, 11, 12).
    if mapping_mode:
        # SPECIAL OVERRIDE: During mapping mode, use the Right Joystick to 
        # send mathematically perfect steering values. This prevents the user 
        # from accidentally locking in a tilted default center state in Forza.
        if vj:
            if x_pct < -50:
                vj.data.wAxisX = 0
            elif x_pct > 50:
                vj.data.wAxisX = 32768
            else:
                vj.data.wAxisX = 16384
            try: vj.update()
            except: pass
        return
    if vj:
        # Clear bits safely for ctypes c_ulong
        mask = (1 << 9) | (1 << 10) | (1 << 11)
        vj.data.lButtons = vj.data.lButtons & (~mask & 0xFFFFFFFF)
        
        # Look Left = Button 10
        if x_pct < -30: vj.data.lButtons |= (1 << 9)
        # Look Right = Button 11
        elif x_pct > 30: vj.data.lButtons |= (1 << 10)
        
        # Look Back = Button 12
        if y_pct > 30: vj.data.lButtons |= (1 << 11)
        
        try: vj.update()
        except: pass

def update_button(btn_key, pressed):
    if vj:
        btn_mapping = {
            'shift_up': 1, 
            'shift_down': 2, 
            'handbrake': 3,
            'rewind': 4, 
            'horn': 5, 
            'pause': 6,
            'camera': 7, 
            'clutch': 8, 
            'view': 9,
            'dpad_up': 13,
            'dpad_down': 14,
            'dpad_left': 15,
            'dpad_right': 16
        }
        if btn_key in btn_mapping:
            bit = 1 << (btn_mapping[btn_key] - 1)
            if pressed: 
                vj.data.lButtons |= bit
            else: 
                vj.data.lButtons = vj.data.lButtons & (~bit & 0xFFFFFFFF)
            try: vj.update()
            except: pass
    elif gamepad:
        if btn_key in BUTTON_MAP:
            btn = BUTTON_MAP[btn_key]
            if pressed: gamepad.press_button(button=btn)
            else: gamepad.release_button(button=btn)
            gamepad.update()

def update_dpad(direction):
    if vj:
        dpad_mapping = {
            XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP: 11,
            XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN: 12,
            XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT: 13,
            XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT: 14
        }
        for bit_idx in dpad_mapping.values():
            vj.data.lButtons &= ~(1 << (bit_idx - 1))
        if direction in dpad_mapping:
            vj.data.lButtons |= (1 << (dpad_mapping[direction] - 1))
        try: vj.update()
        except: pass
    elif gamepad:
        gamepad.release_button(button=XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP)
        gamepad.release_button(button=XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN)
        gamepad.release_button(button=XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT)
        gamepad.release_button(button=XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT)
        if direction is not None: gamepad.press_button(button=direction)
        gamepad.update()



def zero_all(device_id):
    if gamepad:
        gamepad.left_joystick(x_value=0, y_value=0)
        gamepad.right_joystick(x_value=0, y_value=0)
        gamepad.right_trigger(value=0)
        gamepad.left_trigger(value=0)
        for btn in BUTTON_MAP.values():
            gamepad.release_button(button=btn)
        update_dpad(None)
        gamepad.update()
    
    if vj:
        try:
            vj.data.wAxisX = 16384
            vj.data.wAxisY = 16384
            vj.data.wAxisZ = 16384
            vj.data.wAxisXRot = 16384
            vj.data.wAxisYRot = 16384
            vj.data.wAxisZRot = 16384
            vj.data.wSlider = 16384
            vj.data.wDial = 16384
            vj.data.lButtons = 0
            vj.update()
        except: pass

# ─── Protocol mapping ────────────────────────────────────────────────────────
COMMAND_MAP = {
    'HANDBRAKE': 'handbrake',
    'LB': 'shift_down',
    'RB': 'shift_up',
    'BTN_Y': 'horn',
    'BTN_X': 'rewind',
    'BTN_A': 'clutch',
    'BTN_B': 'camera',
    'START': 'pause',
    'BACK_BTN': 'view',
    'DPAD_U': 'dpad_up',
    'DPAD_D': 'dpad_down',
    'DPAD_L': 'dpad_left',
    'DPAD_R': 'dpad_right',
}

BUTTON_MAP = {
    'handbrake': XUSB_BUTTON.XUSB_GAMEPAD_A,
    'shift_down': XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER,
    'shift_up': XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER,
    'horn': XUSB_BUTTON.XUSB_GAMEPAD_Y,
    'rewind': XUSB_BUTTON.XUSB_GAMEPAD_X,
    'clutch': XUSB_BUTTON.XUSB_GAMEPAD_A,
    'camera': XUSB_BUTTON.XUSB_GAMEPAD_B,
    'pause': XUSB_BUTTON.XUSB_GAMEPAD_START,
    'view': XUSB_BUTTON.XUSB_GAMEPAD_BACK,
    'dpad_up': XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP,
    'dpad_down': XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN,
    'dpad_left': XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT,
    'dpad_right': XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT
}

def get_button_flag(command):
    if not VIGEM_AVAILABLE: return None
    mapping = {
        'HANDBRAKE': XUSB_BUTTON.XUSB_GAMEPAD_A,
        'LB':        XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER,
        'RB':        XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER,
        'BTN_Y':     XUSB_BUTTON.XUSB_GAMEPAD_Y,
        'BTN_X':     XUSB_BUTTON.XUSB_GAMEPAD_X,
        'BTN_A':     XUSB_BUTTON.XUSB_GAMEPAD_A,
        'BTN_B':     XUSB_BUTTON.XUSB_GAMEPAD_B,
        'BACK_BTN':  XUSB_BUTTON.XUSB_GAMEPAD_BACK,
        'START':     XUSB_BUTTON.XUSB_GAMEPAD_START,
        'DPAD_U':    XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP,
        'DPAD_D':    XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN,
        'DPAD_L':    XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT,
        'DPAD_R':    XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT,
        'D':         XUSB_BUTTON.XUSB_GAMEPAD_A,
        'E':         XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER,
        'F':         XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER,
        'G':         XUSB_BUTTON.XUSB_GAMEPAD_Y,
        'H':         XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_THUMB,
        'I':         XUSB_BUTTON.XUSB_GAMEPAD_B,
        'J':         XUSB_BUTTON.XUSB_GAMEPAD_X,
    }
    return mapping.get(command)

def process_critical_message(device_id, message, update_ui_callback=None):
    command = message.strip()
    logging.debug(f"Critical: {command}")

    is_on = command.endswith('_ON')
    is_off = command.endswith('_OFF')
    
    base_cmd = command
    if is_on: base_cmd = command[:-3]
    if is_off: base_cmd = command[:-4]

    btn_flag = get_button_flag(base_cmd)
    logging.info(f"Crit: {message} -> btn_flag: {btn_flag}")
    
    if btn_flag:
        btn_name = COMMAND_MAP.get(base_cmd, base_cmd.lower())
        
        if is_on:
            update_button(btn_name, True)
            logging.info(f"Button {base_cmd} (PRESSED)")
            if update_ui_callback: update_ui_callback(btn_name, True)
        elif is_off:
            update_button(btn_name, False)
            logging.info(f"Button {base_cmd} (RELEASED)")
            if update_ui_callback: update_ui_callback(btn_name, False)

def process_non_critical_message(device_id, message, update_ui_callback=None):
    state = device_states.get(device_id)
    if not state:
        return

    parts = message.split(':')
    if len(parts) == 2:
        key = parts[0]
        try:
            val = float(parts[1])
            if key == 'A':
                set_steering(val)
                state.steering = val
                if update_ui_callback: 
                    ui_val = int(((val + 10.0) / 20.0) * 32767)
                    update_ui_callback('steering', ui_val)
            elif key == 'B':
                set_gas(val)
                state.gas = val
                if update_ui_callback: update_ui_callback('throttle', val)
            elif key == 'C':
                set_brake(val)
                state.brake = val
                if update_ui_callback: update_ui_callback('brake', val)
            elif key == 'RX':
                state.rx = val
                set_right_joystick(state.rx, getattr(state, 'ry', 0.0))
            elif key == 'RY':
                state.ry = val
                set_right_joystick(getattr(state, 'rx', 0.0), state.ry)
        except ValueError:
            pass

# ─── Client handler threads ───────────────────────────────────────────────────
def handle_critical_messages(device_id, update_ui_callback=None):
    while not shutdown_event.is_set():
        try:
            state = device_states.get(device_id)
            if state is None: break
            if state.critical_queue:
                process_critical_message(device_id, state.critical_queue.popleft(), update_ui_callback)
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
            if state.non_critical_queue:
                msg = state.non_critical_queue.popleft()
                # Do NOT clear the queue here, otherwise batched zero-values (release events) are dropped!
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
        device_states[device_id] = DeviceState()
        device_states[device_id].critical_queue = deque()
        device_states[device_id].non_critical_queue = deque()

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
                    
                    is_critical = False
                    if line in COMMAND_MAP or line.endswith('_ON') or line.endswith('_OFF') or len(line) == 1 or line == 'BACK_BTN' or line.startswith('DPAD_'):
                        is_critical = True
                    
                    if is_critical:
                        device_states[device_id].critical_queue.append(line)
                    elif line.startswith(('A:', 'B:', 'C:', 'RX:', 'RY:')):
                        device_states[device_id].non_critical_queue.append(line)

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
    shutdown_event.clear()
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
