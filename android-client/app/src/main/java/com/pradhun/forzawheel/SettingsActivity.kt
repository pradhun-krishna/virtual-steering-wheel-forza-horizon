package com.pradhun.forzawheel

import android.os.Bundle
import android.widget.Button
import android.widget.SeekBar
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

class SettingsActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_settings)

        val prefs = getSharedPreferences("steering_prefs", MODE_PRIVATE)
        val editor = prefs.edit()

        val angleBar = findViewById<SeekBar>(R.id.steering_angle)
        val angleText = findViewById<TextView>(R.id.steering_angle_value)
        
        val accelBar = findViewById<SeekBar>(R.id.accelerator_sensitivity)
        val accelText = findViewById<TextView>(R.id.accelerator_value)

        val brakeBar = findViewById<SeekBar>(R.id.brake_sensitivity)
        val brakeText = findViewById<TextView>(R.id.brake_value)

        // Initialize values
        val currentAngle = prefs.getInt("steering_angle", 360)
        angleBar.progress = currentAngle
        angleText.text = "$currentAngle°"

        val currentAccel = prefs.getFloat("accel_sens", 1.0f)
        accelBar.progress = (currentAccel * 10).toInt()
        accelText.text = String.format("%.1f", currentAccel)

        val currentBrake = prefs.getFloat("brake_sens", 1.0f)
        brakeBar.progress = (currentBrake * 10).toInt()
        brakeText.text = String.format("%.1f", currentBrake)

        // Listeners
        angleBar.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                angleText.text = "$progress°"
                editor.putInt("steering_angle", progress).apply()
            }
            override fun onStartTrackingTouch(seekBar: SeekBar?) {}
            override fun onStopTrackingTouch(seekBar: SeekBar?) {}
        })

        accelBar.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                val v = progress / 10f
                accelText.text = String.format("%.1f", v)
                editor.putFloat("accel_sens", v).apply()
            }
            override fun onStartTrackingTouch(seekBar: SeekBar?) {}
            override fun onStopTrackingTouch(seekBar: SeekBar?) {}
        })
        
        brakeBar.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                val v = progress / 10f
                brakeText.text = String.format("%.1f", v)
                editor.putFloat("brake_sens", v).apply()
            }
            override fun onStartTrackingTouch(seekBar: SeekBar?) {}
            override fun onStopTrackingTouch(seekBar: SeekBar?) {}
        })

        findViewById<Button>(R.id.button_back).setOnClickListener { finish() }
    }
}
