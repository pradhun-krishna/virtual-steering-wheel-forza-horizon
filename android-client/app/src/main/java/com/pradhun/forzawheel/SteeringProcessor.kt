package com.pradhun.forzawheel

/**
 * SteeringProcessor
 * Handles dead zones, response curves, and normalization for the steering angle.
 */
class SteeringProcessor {
    
    // Configurable parameters
    var maxSteeringAngle: Float = 360f // Total angle lock-to-lock (±180 defaults)
    var deadzonePercent: Float = 0.02f // 2% deadzone
    
    // Output protocol max (Android sends -10 to +10)
    private val protocolMax = 10f
    
    fun process(rawAngle: Float): Float {
        // 1. Clamp to max physical angle (half of lock-to-lock)
        val maxAngleHalf = maxSteeringAngle / 2f
        val clamped = rawAngle.coerceIn(-maxAngleHalf, maxAngleHalf)
        
        // 2. Normalize to -1..1
        var normalized = clamped / maxAngleHalf
        
        // 3. Apply deadzone
        if (Math.abs(normalized) < deadzonePercent) {
            return 0f
        }
        
        // 4. Re-scale outside deadzone to 0..1
        val sign = Math.signum(normalized)
        val activeRange = 1f - deadzonePercent
        val deadzoned = (Math.abs(normalized) - deadzonePercent) / activeRange
        
        // 5. Apply response curve (optional, currently linear)
        val curved = deadzoned // e.g., Math.pow(deadzoned, 1.2) for non-linear
        
        // 6. Scale to protocol format
        return sign * curved * protocolMax
    }
}
