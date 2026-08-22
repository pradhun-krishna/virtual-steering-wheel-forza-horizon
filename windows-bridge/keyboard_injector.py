import ctypes
import time
import threading

# Windows SendInput constants
SendInput = ctypes.windll.user32.SendInput
PUL = ctypes.POINTER(ctypes.c_ulong)

# C struct definitions for SendInput
class KeyBdInput(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort),
                ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", PUL)]

class HardwareInput(ctypes.Structure):
    _fields_ = [("uMsg", ctypes.c_ulong),
                ("wParamL", ctypes.c_short),
                ("wParamH", ctypes.c_ushort)]

class MouseInput(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long),
                ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", PUL)]

class Input_I(ctypes.Union):
    _fields_ = [("ki", KeyBdInput),
                ("mi", MouseInput),
                ("hi", HardwareInput)]

class Input(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong),
                ("ii", Input_I)]

# Scancodes for standard keys
DIK_W = 0x11
DIK_A = 0x1E
DIK_S = 0x1F
DIK_D = 0x20
DIK_SPACE = 0x39
DIK_Q = 0x10
DIK_E = 0x12
DIK_H = 0x23
DIK_C = 0x2E
DIK_R = 0x13
DIK_ESCAPE = 0x01
DIK_ENTER = 0x1C
DIK_UP = 0xC8
DIK_DOWN = 0xD0
DIK_LEFT = 0xCB
DIK_RIGHT = 0xCD

def press_key(hexKeyCode):
    extra = ctypes.c_ulong(0)
    ii_ = Input_I()
    ii_.ki = KeyBdInput(0, hexKeyCode, 0x0008, 0, ctypes.pointer(extra))
    x = Input(ctypes.c_ulong(1), ii_)
    SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))

def release_key(hexKeyCode):
    extra = ctypes.c_ulong(0)
    ii_ = Input_I()
    ii_.ki = KeyBdInput(0, hexKeyCode, 0x0008 | 0x0002, 0, ctypes.pointer(extra))
    x = Input(ctypes.c_ulong(1), ii_)
    SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))

# ─── PWM Steering Logic ────────────────────────────────────────────────────────
_pwm_running = False
_pwm_thread = None
_steering_val = 0.0  # -1.0 to 1.0 (Left to Right)
_gas_val = 0.0       # 0.0 to 1.0
_brake_val = 0.0     # 0.0 to 1.0

def _pwm_loop():
    global _steering_val, _gas_val, _brake_val, _pwm_running
    cycle_time = 0.02  # 20ms cycle (50Hz)
    
    last_steer_key = None
    last_gas_key = False
    last_brake_key = False
    
    while _pwm_running:
        start_t = time.perf_counter()
        
        # Snapshot current values
        s_val = _steering_val
        g_val = _gas_val
        b_val = _brake_val
        
        # ── Steering ──
        steer_key = None
        steer_duty = 0.0
        if s_val < -0.05:
            steer_key = DIK_A
            steer_duty = abs(s_val)
        elif s_val > 0.05:
            steer_key = DIK_D
            steer_duty = abs(s_val)
            
        # ── Gas / Brake (Simple threshold for now, or PWM if desired) ──
        # We'll use 20% threshold for gas/brake to avoid stuttering
        gas_pressed = g_val > 0.2
        brake_pressed = b_val > 0.2
        
        # Release old keys if direction changed
        if last_steer_key and last_steer_key != steer_key:
            release_key(last_steer_key)
            last_steer_key = None
            
        if steer_key:
            on_time = cycle_time * steer_duty
            if on_time > 0: press_key(steer_key)
        
        if gas_pressed and not last_gas_key: press_key(DIK_W)
        elif not gas_pressed and last_gas_key: release_key(DIK_W)
        
        if brake_pressed and not last_brake_key: press_key(DIK_S)
        elif not brake_pressed and last_brake_key: release_key(DIK_S)
        
        last_steer_key = steer_key
        last_gas_key = gas_pressed
        last_brake_key = brake_pressed
        
        # Sleep for ON duration
        if steer_key and on_time > 0:
            time.sleep(on_time)
            if steer_duty < 0.99: 
                release_key(steer_key)
            
        # Sleep for OFF duration
        elapsed = time.perf_counter() - start_t
        remaining = cycle_time - elapsed
        if remaining > 0:
            time.sleep(remaining)

def start_keyboard_mode():
    global _pwm_running, _pwm_thread
    if _pwm_running: return
    _pwm_running = True
    _pwm_thread = threading.Thread(target=_pwm_loop, daemon=True)
    _pwm_thread.start()

def stop_keyboard_mode():
    global _pwm_running
    _pwm_running = False
    # Release all potential keys
    release_key(DIK_W)
    release_key(DIK_S)
    release_key(DIK_A)
    release_key(DIK_D)

def set_steering(val_neg10_to_10):
    global _steering_val
    _steering_val = max(-1.0, min(1.0, val_neg10_to_10 / 10.0))

def set_gas(val_0_to_100):
    global _gas_val
    _gas_val = max(0.0, min(1.0, val_0_to_100 / 100.0))

def set_brake(val_0_to_100):
    global _brake_val
    _brake_val = max(0.0, min(1.0, val_0_to_100 / 100.0))

def pulse_key(hexKeyCode, duration=0.05):
    press_key(hexKeyCode)
    threading.Timer(duration, release_key, args=[hexKeyCode]).start()

# Mapping for Android buttons -> PC Keys
# Handbrake = Space, Shift Down = Q, Shift Up = E, Horn = H, Camera = C, Rewind = R, Pause = Escape
BTN_MAP = {
    'D': DIK_SPACE,
    'E': DIK_Q,
    'F': DIK_E,
    'G': DIK_H,
    'I': DIK_C,
    'J': DIK_R,
    'START': DIK_ESCAPE,
    'DPAD_U': DIK_UP,
    'DPAD_D': DIK_DOWN,
    'DPAD_L': DIK_LEFT,
    'DPAD_R': DIK_RIGHT,
}
