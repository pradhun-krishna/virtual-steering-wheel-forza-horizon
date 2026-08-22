package com.pradhun.forzawheel

import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/**
 * SensorEngine — reads TYPE_ROTATION_VECTOR for stable, drift-free orientation.
 *
 * Falls back to accelerometer-only method (like MobilWheel) if rotation vector
 * is unavailable.
 *
 * Exposes:
 *   - steeringAngle (degrees from -180..+180 relative to calibration center)
 *   - rawSensorData  (for diagnostics screen)
 */
data class SensorData(
    val gyroX: Float = 0f, val gyroY: Float = 0f, val gyroZ: Float = 0f,
    val accelX: Float = 0f, val accelY: Float = 0f, val accelZ: Float = 0f,
    val yaw: Float = 0f, val pitch: Float = 0f, val roll: Float = 0f,
    val steeringAngle: Float = 0f  // final processed steering in degrees
)

class SensorEngine(private val sensorManager: SensorManager) : SensorEventListener {

    // ── Published state ──────────────────────────────────────────────────────
    private val _sensorData  = MutableStateFlow(SensorData())
    val sensorData: StateFlow<SensorData> = _sensorData

    // ── Calibration ──────────────────────────────────────────────────────────
    private var calibrationRoll = 0f
    private var isCalibrated    = false

    // ── Sensors ──────────────────────────────────────────────────────────────
    private val rotationVector  = sensorManager.getDefaultSensor(Sensor.TYPE_ROTATION_VECTOR)
    private val accelerometer   = sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
    private val gyroscope       = sensorManager.getDefaultSensor(Sensor.TYPE_GYROSCOPE)
    val hasRotationVector get() = rotationVector != null

    // ── Raw gyro/accel for diagnostics ───────────────────────────────────────
    private var latestGyro  = FloatArray(3)
    private var latestAccel = FloatArray(3)

    // ── Rotation matrix work buffers ─────────────────────────────────────────
    private val rotMatrix    = FloatArray(9)
    private val orientation  = FloatArray(3)

    // ── Smoothing (EMA) ──────────────────────────────────────────────────────
    private var smoothedRoll = 0f
    private val SMOOTH_ALPHA = 0.25f   // 0 = no smoothing, 1 = full (sluggish)

    // ── Continuous rotation (prevents ±180 wraparound jumps) ─────────────────
    private var lastRaw = 0f
    private var continuous = 0f
    private var firstReading = true

    fun register() {
        if (rotationVector != null) {
            sensorManager.registerListener(this, rotationVector, SensorManager.SENSOR_DELAY_GAME)
        } else {
            sensorManager.registerListener(this, accelerometer, SensorManager.SENSOR_DELAY_GAME)
        }
        // Always register gyro + accel for diagnostics readout
        gyroscope?.let  { sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_GAME) }
        accelerometer?.let { sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_GAME) }
    }

    fun unregister() {
        sensorManager.unregisterListener(this)
    }

    fun calibrate() {
        calibrationRoll = continuous
        isCalibrated    = true
        smoothedRoll    = 0f
        firstReading    = true
    }

    fun resetCalibration() {
        calibrationRoll = 0f
        isCalibrated    = false
        continuous      = 0f
        firstReading    = true
    }

    override fun onSensorChanged(event: SensorEvent?) {
        event ?: return
        when (event.sensor.type) {

            Sensor.TYPE_ROTATION_VECTOR -> {
                // Extract rotation matrix from quaternion (OS Kalman-fused)
                SensorManager.getRotationMatrixFromVector(rotMatrix, event.values)
                SensorManager.getOrientation(rotMatrix, orientation)

                // orientation[2] = roll (rotation around Z, the axis we care about in landscape)
                val rawRollRad = orientation[2]
                val rawRollDeg = Math.toDegrees(rawRollRad.toDouble()).toFloat()

                updateContinuousAngle(rawRollDeg)
                publishData(
                    yaw   = Math.toDegrees(orientation[0].toDouble()).toFloat(),
                    pitch = Math.toDegrees(orientation[1].toDouble()).toFloat(),
                    roll  = rawRollDeg
                )
            }

            Sensor.TYPE_ACCELEROMETER -> {
                latestAccel = event.values.clone()
                if (rotationVector == null) {
                    // Fallback: use atan2 like MobilWheel
                    val rawAngle = Math.toDegrees(
                        Math.atan2(event.values[1].toDouble(), event.values[0].toDouble())
                    ).toFloat()
                    updateContinuousAngle(rawAngle)
                    publishData(yaw = 0f, pitch = event.values[1], roll = rawAngle)
                }
            }

            Sensor.TYPE_GYROSCOPE -> {
                latestGyro = event.values.clone()
            }
        }
    }

    private fun updateContinuousAngle(rawAngle: Float) {
        if (firstReading) {
            lastRaw    = rawAngle
            continuous = rawAngle
            firstReading = false
        } else {
            var delta = rawAngle - lastRaw
            if (delta >  180f) delta -= 360f
            if (delta < -180f) delta += 360f
            continuous += delta
            lastRaw = rawAngle
        }
    }

    private fun publishData(yaw: Float, pitch: Float, roll: Float) {
        // Subtract calibration center
        val relative = if (isCalibrated) continuous - calibrationRoll else continuous

        // EMA smoothing
        smoothedRoll = SMOOTH_ALPHA * relative + (1f - SMOOTH_ALPHA) * smoothedRoll

        _sensorData.value = SensorData(
            gyroX  = latestGyro[0],  gyroY  = latestGyro[1],  gyroZ  = latestGyro[2],
            accelX = latestAccel[0], accelY = latestAccel[1], accelZ = latestAccel[2],
            yaw = yaw, pitch = pitch, roll = roll,
            steeringAngle = smoothedRoll
        )
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}
}
