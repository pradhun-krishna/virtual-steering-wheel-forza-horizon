package com.pradhun.forzawheel

import android.annotation.SuppressLint
import android.content.Context
import android.hardware.SensorManager
import android.os.Bundle
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.View
import android.widget.FrameLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch
import kotlinx.coroutines.delay

class SteeringWheelActivity : AppCompatActivity() {

    private lateinit var sensorEngine: SensorEngine
    private lateinit var steeringProcessor: SteeringProcessor
    private lateinit var tcpClient: TcpClient

    // Views
    private lateinit var leftSide: FrameLayout
    private lateinit var rightSide: FrameLayout
    private lateinit var accelerateIndicator: View
    private lateinit var brakeIndicator: View
    private lateinit var gearIndicator: TextView
    private lateinit var speedValue: TextView

    // Status
    private lateinit var connectionLabel: TextView
    private lateinit var ipDisplay: TextView

    // Button overlays
    private lateinit var btnLeftTop: View
    private lateinit var btnLeftBottom: View
    private lateinit var btnRightTop: View
    private lateinit var btnRightBottom: View
    
    // Config
    private var accelSens = 1.0f
    private var brakeSens = 1.0f
    private var lastSteer = 0f

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        // Hide system UI for immersive full screen
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
        setupTouchListeners()
        setupButtonListeners()

        // Load config
        val prefs = getSharedPreferences("steering_prefs", MODE_PRIVATE)
        steeringProcessor.maxSteeringAngle = prefs.getInt("steering_angle", 360).toFloat()
        accelSens = prefs.getFloat("accel_sens", 1.0f)
        brakeSens = prefs.getFloat("brake_sens", 1.0f)

        // Observe sensor data
        lifecycleScope.launch {
            sensorEngine.sensorData.collect { data ->
                val processed = steeringProcessor.process(data.steeringAngle)
                if (Math.abs(processed - lastSteer) > 0.05f) {
                    lastSteer = processed
                    tcpClient.sendCommand("A:$processed")
                }
                
                // HUD counter-rotation
                findViewById<View>(R.id.gearContainer)?.rotation = -data.steeringAngle
            }
        }

        // Observe network state
        lifecycleScope.launch {
            tcpClient.connectionState.collect { state ->
                when (state) {
                    is TcpClient.ConnectionState.Connected -> {
                        connectionLabel.text = "CONNECTED"
                        connectionLabel.setTextColor(0xFF4ADE80.toInt())
                        ipDisplay.text = state.ip
                    }
                    is TcpClient.ConnectionState.Disconnected -> {
                        connectionLabel.text = "OFFLINE"
                        connectionLabel.setTextColor(0xFFFF6B6B.toInt())
                        ipDisplay.text = "-.-.-.-"
                    }
                    is TcpClient.ConnectionState.Error -> {
                        connectionLabel.text = "ERROR"
                        connectionLabel.setTextColor(0xFFFF0000.toInt())
                    }
                    is TcpClient.ConnectionState.Connecting -> {
                        connectionLabel.text = "CONNECTING..."
                        connectionLabel.setTextColor(0xFFFFFF00.toInt())
                    }
                }
            }
        }

        // Start discovery
        lifecycleScope.launch {
            val ip = UdpDiscovery.discoverServer()
            if (ip != null) {
                tcpClient.connect(ip)
            } else {
                Toast.makeText(this@SteeringWheelActivity, "PC not found automatically.", Toast.LENGTH_LONG).show()
                // Could implement manual IP dialog here
            }
        }
    }

    private fun initViews() {
        leftSide = findViewById(R.id.left_side)
        rightSide = findViewById(R.id.right_side)
        accelerateIndicator = findViewById(R.id.accelerateIndicator)
        brakeIndicator = findViewById(R.id.brakeIndicator)
        
        gearIndicator = findViewById(R.id.gearIndicator)
        speedValue = findViewById(R.id.speedValue)
        connectionLabel = findViewById(R.id.connectionLabel)
        ipDisplay = findViewById(R.id.ipAddressDisplay)
        
        btnLeftTop = findViewById(R.id.button_left_top)
        btnLeftBottom = findViewById(R.id.button_left_bottom)
        btnRightTop = findViewById(R.id.button_right_top)
        btnRightBottom = findViewById(R.id.button_right_bottom)
    }

    @SuppressLint("ClickableViewAccessibility")
    private fun setupTouchListeners() {
        // Left = Brake (C)
        leftSide.setOnTouchListener { _, event ->
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    brakeIndicator.visibility = View.VISIBLE
                    updateBrake(event.y, event.y) // initial
                }
                MotionEvent.ACTION_MOVE -> {
                    // Could store initial Y to calculate delta, here assuming proportional to screen height
                    updateBrake(event.y, 0f) // simplified
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    brakeIndicator.visibility = View.GONE
                    tcpClient.sendCommand("C:0")
                }
            }
            true
        }

        // Right = Gas (B)
        rightSide.setOnTouchListener { _, event ->
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    accelerateIndicator.visibility = View.VISIBLE
                }
                MotionEvent.ACTION_MOVE -> {
                    updateAccelerate(event.y)
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    accelerateIndicator.visibility = View.GONE
                    tcpClient.sendCommand("B:0")
                }
            }
            true
        }
    }
    
    private fun updateBrake(y: Float, startY: Float) {
        val h = resources.displayMetrics.heightPixels
        // Slide up = more brake. Simple proportional implementation:
        val pct = ((1f - (y / h)) * 100 * brakeSens).toInt().coerceIn(0, 100)
        val lp = brakeIndicator.layoutParams
        lp.height = (h * (pct / 100f)).toInt()
        brakeIndicator.layoutParams = lp
        tcpClient.sendCommand("C:$pct")
    }

    private fun updateAccelerate(y: Float) {
        val h = resources.displayMetrics.heightPixels
        val pct = ((1f - (y / h)) * 100 * accelSens).toInt().coerceIn(0, 100)
        val lp = accelerateIndicator.layoutParams
        lp.height = (h * (pct / 100f)).toInt()
        accelerateIndicator.layoutParams = lp
        tcpClient.sendCommand("B:$pct")
    }

    @SuppressLint("ClickableViewAccessibility")
    private fun setupButtonListeners() {
        // Simple click implementations
        val onClick = View.OnClickListener { v ->
            when (v.id) {
                R.id.button_left_top -> tcpClient.sendCommand("D")
                R.id.button_left_bottom -> tcpClient.sendCommand("E")
                R.id.button_right_top -> tcpClient.sendCommand("F")
                R.id.button_right_bottom -> tcpClient.sendCommand("G")
            }
        }
        btnLeftTop.setOnClickListener(onClick)
        btnLeftBottom.setOnClickListener(onClick)
        btnRightTop.setOnClickListener(onClick)
        btnRightBottom.setOnClickListener(onClick)
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent?): Boolean = when (keyCode) {
        KeyEvent.KEYCODE_VOLUME_UP -> { tcpClient.sendCommand("VOLUME_UP"); true }
        KeyEvent.KEYCODE_VOLUME_DOWN -> { tcpClient.sendCommand("VOLUME_DOWN"); true }
        else -> super.onKeyDown(keyCode, event)
    }

    override fun onResume() {
        super.onResume()
        sensorEngine.register()
        sensorEngine.calibrate() // Auto calibrate on resume
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
