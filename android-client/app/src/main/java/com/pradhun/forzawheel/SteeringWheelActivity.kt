package com.pradhun.forzawheel

import android.annotation.SuppressLint
import android.content.Context
import android.hardware.SensorManager
import android.os.Bundle
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.Surface
import android.view.View
import android.widget.Button
import android.widget.FrameLayout
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch

class SteeringWheelActivity : AppCompatActivity() {

    private lateinit var sensorEngine: SensorEngine
    private lateinit var steeringProcessor: SteeringProcessor
    private lateinit var tcpClient: TcpClient

    // ── Pedal zones
    private lateinit var brakeZone: FrameLayout
    private lateinit var gasZone: FrameLayout
    private lateinit var brakeFill: View
    private lateinit var gasFill: View
    private lateinit var brakePct: TextView
    private lateinit var gasPct: TextView

    // ── HUD (just the connection label now)
    private lateinit var connectionLabel: TextView

    // ── Left panel buttons
    private lateinit var btnHandbrake: Button
    private lateinit var btnLook: Button
    private lateinit var btnRewind: Button
    private lateinit var btnShiftDown: Button

    // ── Right panel buttons
    private lateinit var btnShiftUp: Button
    private lateinit var btnHorn: Button
    private lateinit var btnClutch: Button
    private lateinit var btnAnna: Button

    // ── Center gamepad buttons
    private lateinit var btnCamera: Button
    private lateinit var btnDpadUp: Button
    private lateinit var btnDpadDown: Button
    private lateinit var btnDpadLeft: Button
    private lateinit var btnDpadRight: Button
    private lateinit var btnStart: Button
    private lateinit var btnBackBtn: Button
    private lateinit var btnCalibrate: Button
    private lateinit var btnChangeIp: Button

    // ── State
    private var accelSens = 1.0f
    private var brakeSens = 1.0f
    private var lastSteer = 0f

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        @Suppress("DEPRECATION")
        window.decorView.systemUiVisibility = (
            View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
            or View.SYSTEM_UI_FLAG_LAYOUT_STABLE
            or View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
            or View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
            or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
            or View.SYSTEM_UI_FLAG_FULLSCREEN
        )

        val sm = getSystemService(Context.SENSOR_SERVICE) as SensorManager
        sensorEngine = SensorEngine(sm)

        steeringProcessor = SteeringProcessor()
        tcpClient = TcpClient(lifecycleScope)

        initViews()
        loadConfig()
        setupTouchListeners()
        setupButtonListeners()
        observeSensors()
        observeNetwork()
        startDiscovery()
    }

    private fun initViews() {
        brakeZone       = findViewById(R.id.brake_touch_zone)
        gasZone         = findViewById(R.id.gas_touch_zone)
        brakeFill       = findViewById(R.id.brake_fill)
        gasFill         = findViewById(R.id.gas_fill)
        brakePct        = findViewById(R.id.brake_pct)
        gasPct          = findViewById(R.id.gas_pct)
        connectionLabel = findViewById(R.id.connectionLabel)

        // Left panel
        btnHandbrake    = findViewById(R.id.btn_handbrake)
        btnLook         = findViewById(R.id.btn_look)
        btnRewind       = findViewById(R.id.btn_rewind)
        btnShiftDown    = findViewById(R.id.btn_shift_down)

        // Right panel
        btnShiftUp      = findViewById(R.id.btn_shift_up)
        btnHorn         = findViewById(R.id.btn_horn)
        btnClutch       = findViewById(R.id.btn_clutch)
        btnAnna         = findViewById(R.id.btn_anna)

        // Center gamepad
        btnCamera       = findViewById(R.id.btn_camera)
        btnDpadUp       = findViewById(R.id.btn_dpad_up)
        btnDpadDown     = findViewById(R.id.btn_dpad_down)
        btnDpadLeft     = findViewById(R.id.btn_dpad_left)
        btnDpadRight    = findViewById(R.id.btn_dpad_right)
        btnStart        = findViewById(R.id.btn_start)
        btnBackBtn      = findViewById(R.id.btn_back_btn)
        btnCalibrate    = findViewById(R.id.btn_calibrate)
        btnChangeIp     = findViewById(R.id.btn_change_ip)
    }

    private fun loadConfig() {
        val prefs = getSharedPreferences("steering_prefs", MODE_PRIVATE)
        steeringProcessor.maxSteeringAngle = prefs.getInt("steering_angle", 360).toFloat()
        accelSens = prefs.getFloat("accel_sens", 1.0f)
        brakeSens = prefs.getFloat("brake_sens", 1.0f)
    }

    @SuppressLint("ClickableViewAccessibility")
    private fun setupTouchListeners() {
        brakeZone.setOnTouchListener { view, event ->
            val pct = ((1f - event.y / view.height) * 100 * brakeSens).toInt().coerceIn(0, 100)
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN, MotionEvent.ACTION_MOVE -> {
                    applyFill(brakeFill, brakePct, pct, view.height)
                    tcpClient.sendCommand("C:$pct")
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    applyFill(brakeFill, brakePct, 0, view.height)
                    tcpClient.sendCommand("C:0")
                }
            }
            true
        }

        gasZone.setOnTouchListener { view, event ->
            val pct = ((1f - event.y / view.height) * 100 * accelSens).toInt().coerceIn(0, 100)
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN, MotionEvent.ACTION_MOVE -> {
                    applyFill(gasFill, gasPct, pct, view.height)
                    tcpClient.sendCommand("B:$pct")
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    applyFill(gasFill, gasPct, 0, view.height)
                    tcpClient.sendCommand("B:0")
                }
            }
            true
        }
    }

    private fun applyFill(fill: View, label: TextView, pct: Int, zoneHeight: Int) {
        label.text = "$pct%"
        val lp = fill.layoutParams
        lp.height = (zoneHeight * pct / 100f).toInt()
        fill.layoutParams = lp
    }

    @SuppressLint("ClickableViewAccessibility")
    private fun setupButtonListeners() {
        // Left panel
        btnHandbrake.setOnClickListener { tcpClient.sendCommand("D") }   // Handbrake (vJoy btn 1 = A)
        btnLook.setOnClickListener      { tcpClient.sendCommand("H") }   // Look Back (vJoy btn 12 = RSB)
        btnRewind.setOnClickListener    { tcpClient.sendCommand("J") }   // Rewind (vJoy btn 3 = X)
        btnShiftDown.setOnClickListener { tcpClient.sendCommand("E") }   // Shift Down (vJoy btn 5 = LB)

        // Right panel
        btnShiftUp.setOnClickListener { tcpClient.sendCommand("F") }     // Shift Up (vJoy btn 6 = RB)
        btnHorn.setOnClickListener    { tcpClient.sendCommand("G") }     // Horn (vJoy btn 4 = Y)
        btnAnna.setOnClickListener    { tcpClient.sendCommand("ANNA") }  // Anna (vJoy btn 9 = View/Back)

        // Clutch — HOLD to engage, RELEASE to disengage (drives the clutch AXIS, not a button pulse)
        btnClutch.setOnTouchListener { _, event ->
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> tcpClient.sendCommand("CLUTCH_ON")
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> tcpClient.sendCommand("CLUTCH_OFF")
            }
            false
        }

        // Center gamepad
        btnCamera.setOnClickListener    { tcpClient.sendCommand("I") }        // Camera (vJoy btn 2 = B)
        btnDpadUp.setOnClickListener    { tcpClient.sendCommand("DPAD_U") }   // D-pad up
        btnDpadDown.setOnClickListener  { tcpClient.sendCommand("DPAD_D") }   // D-pad down
        btnDpadLeft.setOnClickListener  { tcpClient.sendCommand("DPAD_L") }   // D-pad left
        btnDpadRight.setOnClickListener { tcpClient.sendCommand("DPAD_R") }   // D-pad right
        btnStart.setOnClickListener     { tcpClient.sendCommand("START") }    // Pause (vJoy btn 10)
        btnBackBtn.setOnClickListener   { tcpClient.sendCommand("BACK_BTN") } // View/Back → Anna (vJoy btn 9)

        btnCalibrate.setOnClickListener { sensorEngine.calibrate() }
        btnChangeIp.setOnClickListener {
            val prefs = getSharedPreferences("steering_prefs", MODE_PRIVATE)
            showManualIpDialog(prefs.getString("last_server_ip", null))
        }
    }

    private fun observeSensors() {
        lifecycleScope.launch {
            sensorEngine.sensorData.collect { data ->
                val processed = steeringProcessor.process(data.steeringAngle)
                if (Math.abs(processed - lastSteer) > 0.05f) {
                    lastSteer = processed
                    tcpClient.sendCommand("A:$processed")
                }
                // No counter-rotation — center panel is static
            }
        }
    }

    private fun observeNetwork() {
        lifecycleScope.launch {
            tcpClient.connectionState.collect { state ->
                when (state) {
                    is TcpClient.ConnectionState.Connected -> {
                        connectionLabel.text = "● CONNECTED  ${state.ip}"
                        connectionLabel.setTextColor(0xFF4ADE80.toInt())
                    }
                    is TcpClient.ConnectionState.Disconnected -> {
                        connectionLabel.text = "● OFFLINE"
                        connectionLabel.setTextColor(0xFFFF4444.toInt())
                    }
                    is TcpClient.ConnectionState.Error -> {
                        connectionLabel.text = "● ERROR"
                        connectionLabel.setTextColor(0xFFFF0000.toInt())
                    }
                    is TcpClient.ConnectionState.Connecting -> {
                        connectionLabel.text = "● CONNECTING…"
                        connectionLabel.setTextColor(0xFFFFDD44.toInt())
                    }
                }
            }
        }
    }

    private fun startDiscovery() {
        lifecycleScope.launch {
            val prefs = getSharedPreferences("steering_prefs", MODE_PRIVATE)
            val savedIp = prefs.getString("last_server_ip", null)
            val ip = UdpDiscovery.discoverServer()
            if (ip != null) {
                prefs.edit().putString("last_server_ip", ip).apply()
                tcpClient.connect(ip)
            } else {
                runOnUiThread { showManualIpDialog(savedIp) }
            }
        }
    }

    private fun showManualIpDialog(prefilledIp: String?) {
        val prefs = getSharedPreferences("steering_prefs", MODE_PRIVATE)
        val input = android.widget.EditText(this).apply {
            inputType = android.text.InputType.TYPE_CLASS_TEXT
            hint = "e.g. 10.91.237.77"
            setText(prefilledIp ?: "")
            setPadding(48, 32, 48, 32)
        }
        AlertDialog.Builder(this)
            .setTitle("PC IP Address")
            .setMessage("Auto-discovery failed. Enter your PC's IP.\n(Run 'ipconfig' on PC → IPv4 Address)")
            .setView(input)
            .setPositiveButton("CONNECT") { _, _ ->
                val ip = input.text.toString().trim()
                if (ip.isNotEmpty()) {
                    prefs.edit().putString("last_server_ip", ip).apply()
                    tcpClient.connect(ip)
                }
            }
            .setNegativeButton("CANCEL", null)
            .show()
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent?): Boolean = when (keyCode) {
        KeyEvent.KEYCODE_VOLUME_UP   -> { sensorEngine.calibrate(); true }
        KeyEvent.KEYCODE_VOLUME_DOWN -> { tcpClient.sendCommand("G"); true } // Horn
        else                         -> super.onKeyDown(keyCode, event)
    }

    override fun onResume() {
        super.onResume()
        sensorEngine.register()
        sensorEngine.calibrate()
    }

    override fun onPause() {
        super.onPause()
        sensorEngine.unregister()
    }

    override fun onDestroy() {
        super.onDestroy()
        tcpClient.disconnect()
    }
}
