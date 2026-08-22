# ForzaWheel — Virtual Steering Wheel for Forza Horizon 6

Turn your Android phone into a high-performance steering wheel and racing controller for Forza Horizon 6.

By combining an ultra-low latency local network protocol with advanced Android Sensor Fusion, ForzaWheel provides a highly responsive, drift-free steering experience that bridges directly into a virtual Xbox controller on Windows.

## ✨ Features

- **Drift-Free Sensor Fusion**: Uses the Android `TYPE_ROTATION_VECTOR` sensor to combine gyroscope, accelerometer, and magnetometer data for incredibly smooth and stable steering (no center drifting).
- **Proportional Pedals**: Use the left and right sides of your touchscreen as smooth, variable sliders for Throttle and Brake—allowing for precise trail-braking and throttle control.
- **Forza-Optimized Layout**: Tap specific zones for Shift Up/Down, Handbrake, and Horn.
- **Physical Buttons Support**: Use your phone's physical volume buttons to Look Back or Change the Camera.
- **Auto-Discovery**: The Android app automatically finds and connects to the Windows Server on your local Wi-Fi.
- **Failsafe System**: If the connection drops, the Windows server instantly zeroes all inputs so your car doesn't crash into a wall.

---

## 🚀 Installation & Setup

### 1. Windows PC (The Server)

You can either run the Python source code directly, or build/download the standalone `.exe`.

**Prerequisite (Required):**
You must have the **vJoy** device driver installed. vJoy allows this software to create a virtual Xbox controller.
1. Download vJoy from [SourceForge](https://sourceforge.net/projects/vjoystick/).
2. Install it.
3. Open **Configure vJoy** from your Start Menu. Ensure **Device 1** is enabled and configured with:
   - Axes: `X`, `Y`, `Z`, `Rx` (all checked)
   - Buttons: At least `12`
   - POV: `0`

**Running from Source:**
1. Install Python 3.10+.
2. Run `setup_and_run.bat` in the `windows-bridge` folder. This will install the required dependencies (PyQt5, pywin32) and launch the server.

**Building the EXE:**
If you want to create a standalone `.exe` to share with others (no Python required):
1. Navigate to the `windows-bridge` folder.
2. Double-click `build_exe.bat`.
3. Your executable will be generated in `windows-bridge\dist\ForzaWheelServer.exe`.

### 2. Android Phone (The Client)

You can build the APK from source using Android Studio, or download a pre-built APK from the [Releases page](../../releases).

**Building the APK from Source:**
1. Open the `android-client` folder in **Android Studio**.
2. Wait for Gradle to sync.
3. In the top menu, go to **Build** -> **Build Bundle(s) / APK(s)** -> **Build APK(s)**.
4. Once finished, click "locate" in the bottom right popup. Transfer the generated `.apk` file to your phone and install it.

*(Note for developers: You can upload this generated APK directly to your GitHub repository's "Releases" section so users can download it directly without needing Android Studio).*

---

## 🎮 How to Play

1. **Start the Server:** Open `ForzaWheelServer.exe` (or run `ServerApp.py` via python) on your Windows PC and click **START SERVER**.
2. **Start the App:** Ensure your phone is connected to the same Wi-Fi network as your PC. Open the ForzaWheel app and tap **START WHEEL**.
3. **Connect:** The app will automatically discover your PC and connect. You should see "CONNECTED" on your phone, and the sliders on the PC Server should move as you tilt the phone.
4. **Map Controls in Forza:**
   - Launch Forza Horizon 6.
   - Go to **Settings -> Controls -> Custom Wheel Profile**.
   - Map the steering axis by turning your phone.
   - Map the Throttle and Brake by sliding your thumbs up and down on the left/right sides of the phone screen.
   - Have fun!

---

## 🛠️ Tech Stack
- **Android**: Kotlin, XML Views, Coroutines (UDP/TCP Networking), SensorManager
- **Windows**: Python 3, PyQt5, ctypes (vJoy Interface), pyinstaller

## 📄 License
MIT License. Feel free to fork, modify, and improve!
