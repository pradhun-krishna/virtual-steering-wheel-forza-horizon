import ctypes
import time
import os
import sys

dll_path = os.path.join(os.path.dirname(__file__), 'vJoy', 'x64', 'vJoyInterface.dll')
vjoy = ctypes.WinDLL(dll_path)

vjoy.AcquireVJD.argtypes = [ctypes.c_uint]
vjoy.AcquireVJD.restype = ctypes.c_bool
vjoy.SetAxis.argtypes = [ctypes.c_long, ctypes.c_uint, ctypes.c_uint]
vjoy.SetAxis.restype = ctypes.c_bool
vjoy.RelinquishVJD.argtypes = [ctypes.c_uint]

device_id = 1
print(f"Acquiring device {device_id}...")
if vjoy.AcquireVJD(device_id):
    print("Acquired. Wiggling X Axis...")
    for _ in range(50):
        # 0x30 is HID_USAGE_X
        success1 = vjoy.SetAxis(1, device_id, 0x30)
        time.sleep(0.05)
        success2 = vjoy.SetAxis(32000, device_id, 0x30)
        time.sleep(0.05)
    print(f"Last status: {success1}, {success2}")
    vjoy.RelinquishVJD(device_id)
    print("Done")
else:
    print("Failed to acquire")
