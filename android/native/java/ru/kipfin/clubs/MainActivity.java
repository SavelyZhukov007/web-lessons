package ru.kipfin.clubs;

import android.os.Bundle;
import android.os.SystemClock;

import androidx.core.splashscreen.SplashScreen;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    /** Веб-экран загрузки уже отрисован (ItcUpdate.splashReady) — системный сплэш можно убирать. */
    static volatile boolean webReady = false;
    private static final long MAX_SPLASH_MS = 2500;

    @Override
    public void onCreate(Bundle savedInstanceState) {
        // Android 12+ SplashScreen API (на 6–11 — compat): держим системный сплэш, пока WebView не нарисует
        // такой же брендовый экран (тот же фон и иконка) — без двойного сплэша и белой/чёрной вспышки.
        SplashScreen splash = SplashScreen.installSplashScreen(this);
        webReady = false;
        final long start = SystemClock.uptimeMillis();
        splash.setKeepOnScreenCondition(() -> !webReady && SystemClock.uptimeMillis() - start < MAX_SPLASH_MS);
        registerPlugin(ItcNativePlugin.class);
        registerPlugin(ItcUpdatePlugin.class);
        registerPlugin(ItcDiscoveryPlugin.class);
        super.onCreate(savedInstanceState);
    }
}
