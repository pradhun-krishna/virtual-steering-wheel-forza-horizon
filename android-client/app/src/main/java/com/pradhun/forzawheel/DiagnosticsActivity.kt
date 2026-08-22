package com.pradhun.forzawheel

import android.content.Context
import android.hardware.SensorManager
import android.os.Bundle
import android.widget.Button
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch

class DiagnosticsActivity : AppCompatActivity() {

    private lateinit var sensorEngine: SensorEngine

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_diagnostics)

        val sm = getSystemService(Context.SENSOR_SERVICE) as SensorManager
        sensorEngine = SensorEngine(sm)

        val tvStatus = findViewById<TextView>(R.id.tv_sensor_status)
        val tvData = findViewById<TextView>(R.id.tv_sensor_data)
        
        tvStatus.text = "Rotation Vector Support: ${if (sensorEngine.hasRotationVector) "YES" else "NO (Fallback)"}"

        lifecycleScope.launch {
            sensorEngine.sensorData.collect { data ->
                val str = """
                    Raw Roll: ${String.format("%.2f", data.roll)}
                    Raw Pitch: ${String.format("%.2f", data.pitch)}
                    Raw Yaw: ${String.format("%.2f", data.yaw)}
                    
                    Processed Steering: ${String.format("%.2f", data.steeringAngle)}
                    
                    Accel (X,Y,Z): 
                    ${String.format("%.2f", data.accelX)}, ${String.format("%.2f", data.accelY)}, ${String.format("%.2f", data.accelZ)}
                    
                    Gyro (X,Y,Z):
                    ${String.format("%.2f", data.gyroX)}, ${String.format("%.2f", data.gyroY)}, ${String.format("%.2f", data.gyroZ)}
                """.trimIndent()
                tvData.text = str
            }
        }
        
        findViewById<Button>(R.id.btn_calibrate).setOnClickListener {
            sensorEngine.calibrate()
        }
        
        findViewById<Button>(R.id.btn_back).setOnClickListener {
            finish()
        }
    }

    override fun onResume() {
        super.onResume()
        sensorEngine.register()
    }

    override fun onPause() {
        super.onPause()
        sensorEngine.unregister()
    }
}
