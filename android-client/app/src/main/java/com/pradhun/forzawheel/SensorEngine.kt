package com.pradhun.forzawheel

import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

data class SensorData(
    val gyroX: Float = 0f, val gyroY: Float = 0f, val gyroZ: Float = 0f,
    val accelX: Float = 0f, val accelY: Float = 0f, val accelZ: Float = 0f,
    val yaw: Float = 0f, val pitch: Float = 0f, val roll: Float = 0f,
    val steeringAngle: Float = 0f
)

/**
 * SensorEngine — steering wheel edition.
 *
 * The user holds the phone in landscape and rotates it like a real steering wheel
 * (the screen normal stays roughly pointing toward the user / ceiling, and the
 * phone rotates around that normal axis).
 *
 * The correct sensor axis for this is AZIMUTH (orientation[0]):
 *   - Azimuth = the direction the phone's long axis is pointing on the horizontal plane
 *   - Turning the phone CW/CCW (steering wheel motion) changes azimuth
 *   - This is true regardless of how tilted the phone is
 *   - NO coordinate remapping is needed
 *
 * We prefer TYPE_GAME_ROTATION_VECTOR (gyro+accel, no magnetic drift) over
 * TYPE_ROTATION_VECTOR.
 */
class SensorEngine(private val sensorManager: SensorManager) : SensorEventListener {

    private val _sensorData = MutableStateFlow(SensorData())
    val sensorData: StateFlow<SensorData> = _sensorData

    // Sensors
    private val gameRotVec = sensorManager.getDefaultSensor(Sensor.TYPE_GAME_ROTATION_VECTOR)
    private val rotVec     = sensorManager.getDefaultSensor(Sensor.TYPE_ROTATION_VECTOR)
    private val accelSensor = sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
    private val gyroSensor  = sensorManager.getDefaultSensor(Sensor.TYPE_GYROSCOPE)

    val hasRotationVector get() = gameRotVec != null || rotVec != null

    // Work buffers
    private val rotMatrix  = FloatArray(9)
    private val orientation = FloatArray(3)

    // Diagnostic
    private var latestGyro  = FloatArray(3)
    private var latestAccel = FloatArray(3)

    // Calibration (azimuth at the time user taps calibrate)
    private var calibrationAngle = 0f
    private var isCalibrated     = false

    // Continuous angle tracking — avoids the ±180° azimuth wraparound
    private var lastRaw    = 0f
    private var continuous = 0f
    private var firstReading = true

    // EMA smoothing (alpha: 0 = no lag, 1 = frozen)
    private var smoothed = 0f
    private val ALPHA = 0.20f

    // ─────────────────────────────────────────────────────────────────────────
    fun register() {
        val primary = gameRotVec ?: rotVec
        primary?.let { sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_GAME) }
        gyroSensor?.let  { sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_GAME) }
        accelSensor?.let { sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_GAME) }
    }

    fun unregister() = sensorManager.unregisterListener(this)

    /** Call when user wants to re-center the steering wheel. */
    fun calibrate() {
        calibrationAngle = continuous
        isCalibrated = true
        smoothed = 0f
    }

    fun resetCalibration() {
        calibrationAngle = 0f
        isCalibrated = false
        continuous = 0f
        firstReading = true
    }

    // ─────────────────────────────────────────────────────────────────────────
    override fun onSensorChanged(event: SensorEvent?) {
        event ?: return
        when (event.sensor.type) {

            Sensor.TYPE_GAME_ROTATION_VECTOR,
            Sensor.TYPE_ROTATION_VECTOR -> {
                // Convert to rotation matrix → orientation angles (no remapping needed)
                SensorManager.getRotationMatrixFromVector(rotMatrix, event.values)
                SensorManager.getOrientation(rotMatrix, orientation)

                // ── orientation[0] = AZIMUTH ──────────────────────────────────────
                // Azimuth is the angle the phone's Y-axis (portrait "up") makes with
                // a fixed world reference on the horizontal plane.
                // When the user rotates the phone like a steering wheel (rotating the
                // long landscape axis), the azimuth changes — CW = increases, CCW = decreases.
                // This works at ANY phone tilt angle — flat, upright, or diagonal.
                val rawDeg = Math.toDegrees(orientation[0].toDouble()).toFloat()
                trackContinuous(rawDeg)

                val relative = if (isCalibrated) continuous - calibrationAngle else 0f
                smoothed = ALPHA * relative + (1f - ALPHA) * smoothed

                _sensorData.value = SensorData(
                    gyroX = latestGyro[0], gyroY = latestGyro[1], gyroZ = latestGyro[2],
                    accelX = latestAccel[0], accelY = latestAccel[1], accelZ = latestAccel[2],
                    yaw   = rawDeg,
                    pitch = Math.toDegrees(orientation[1].toDouble()).toFloat(),
                    roll  = Math.toDegrees(orientation[2].toDouble()).toFloat(),
                    steeringAngle = smoothed
                )
            }

            Sensor.TYPE_ACCELEROMETER -> { latestAccel = event.values.clone() }
            Sensor.TYPE_GYROSCOPE     -> { latestGyro  = event.values.clone() }
        }
    }

    /**
     * Unwrap the angle to be continuous (avoids jumps when crossing ±180°).
     * This lets us track multiple full rotations without discontinuities.
     */
    private fun trackContinuous(rawAngle: Float) {
        if (firstReading) {
            lastRaw = rawAngle
            continuous = rawAngle
            firstReading = false
            return
        }
        var delta = rawAngle - lastRaw
        // Correct for wraparound
        if (delta >  180f) delta -= 360f
        if (delta < -180f) delta += 360f
        continuous += delta
        lastRaw = rawAngle
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}
}
