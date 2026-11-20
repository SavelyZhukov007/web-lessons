package ru.kipfin.clubs;

import android.hardware.Sensor;
import android.hardware.SensorEvent;
import android.hardware.SensorEventListener;
import android.hardware.SensorManager;
import android.os.SystemClock;

/** «Встряхнуть, чтобы сообщить об ошибке»: два рывка сильнее 2.7g за 600 мс, не чаще раза в 3 с. */
final class ShakeDetector implements SensorEventListener {
    interface Listener { void onShake(); }
    private static final float THRESHOLD_G = 2.7f;
    private final Listener listener;
    private long firstPeak, lastShake;
    ShakeDetector(Listener listener) { this.listener = listener; }

    static boolean isShake(float x, float y, float z) {
        float g = (float) Math.sqrt(x * x + y * y + z * z) / SensorManager.GRAVITY_EARTH;
        return g > THRESHOLD_G;
    }

    @Override public void onSensorChanged(SensorEvent event) {
        if (!isShake(event.values[0], event.values[1], event.values[2])) return;
        long now = SystemClock.uptimeMillis();
        if (now - lastShake < 3000) return;
        if (firstPeak == 0 || now - firstPeak > 600) { firstPeak = now; return; }
        firstPeak = 0; lastShake = now;
        listener.onShake();
    }

    @Override public void onAccuracyChanged(Sensor sensor, int accuracy) { }
}
