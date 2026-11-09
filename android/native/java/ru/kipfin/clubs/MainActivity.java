package ru.kipfin.clubs;

import android.app.ActivityManager;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.hardware.display.DisplayManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.Looper;
import android.os.PowerManager;
import android.os.SystemClock;
import android.view.Display;
import android.view.FrameMetrics;
import android.view.Window;
import android.view.View;
import android.view.WindowManager;
import androidx.core.splashscreen.SplashScreen;
import com.getcapacitor.BridgeActivity;
import com.getcapacitor.JSObject;
import com.getcapacitor.WebViewListener;

/** Display hints, not a forced system setting: power saver/OEM/thermal policy always wins. */
public class MainActivity extends BridgeActivity implements DisplayManager.DisplayListener {
    static volatile boolean webReady = false;
    private static final long MAX_SPLASH_MS = 2500;
    private DisplayManager displays;
    private volatile boolean observing;
    private HandlerThread frameThread;
    private final FrameBudget frameBudget = new FrameBudget();
    private volatile boolean nativeGpuOverloaded;
    private volatile float actualHz = 60;
    private long performanceStartedAt;
    private boolean recordedStartup;
    private final Window.OnFrameMetricsAvailableListener gpuFrames = (window, metrics, dropped) -> {
        // Ignore cold-start/first-draw work; this signal covers GPU/RenderThread waits invisible to JS RAF.
        if (!observing || nativeGpuOverloaded || SystemClock.uptimeMillis() - performanceStartedAt < 5000
                || metrics.getMetric(FrameMetrics.FIRST_DRAW_FRAME) != 0) return;
        if (frameBudget.record(metrics.getMetric(FrameMetrics.TOTAL_DURATION), actualHz)) {
            nativeGpuOverloaded = true;
            runOnUiThread(() -> { if (observing && !isDestroyed()) publishPerformanceState(); });
        }
    };
    private float requestedHz;
    private final BroadcastReceiver powerChange = new BroadcastReceiver() {
        @Override public void onReceive(Context context, Intent intent) { refreshDisplayPolicy(); }
    };

    @Override public void onCreate(Bundle state) {
        SplashScreen splash = SplashScreen.installSplashScreen(this);
        WebViewWarmup.start(getApplicationContext());
        webReady = false;
        final long start = SystemClock.uptimeMillis();
        performanceStartedAt = start;
        splash.setKeepOnScreenCondition(() -> !webReady && SystemClock.uptimeMillis() - start < MAX_SPLASH_MS);
        getWindow().setFlags(WindowManager.LayoutParams.FLAG_HARDWARE_ACCELERATED,
                WindowManager.LayoutParams.FLAG_HARDWARE_ACCELERATED);
        registerPlugin(ItcNativePlugin.class);
        registerPlugin(ItcUpdatePlugin.class);
        registerPlugin(ItcDiscoveryPlugin.class);
        registerPlugin(ItcPerformancePlugin.class);
        super.onCreate(state);
        NotificationReceipts.opened(this, getIntent());
        displays = (DisplayManager) getSystemService(Context.DISPLAY_SERVICE);
        frameThread = new HandlerThread("kipclub-frame-budget", android.os.Process.THREAD_PRIORITY_BACKGROUND);
        frameThread.start();
        // NONE means the normal accelerated WebView pipeline, not a giant cached hardware texture.
        if (bridge != null) {
            bridge.getWebView().setLayerType(View.LAYER_TYPE_NONE, null);
            // First committed pixels, not requestAnimationFrame behind a held native pre-draw.
            bridge.addWebViewListener(new WebViewListener() {
                @Override public void onPageCommitVisible(android.webkit.WebView view, String url) {
                    webReady = true;
                    if (!recordedStartup) {
                        recordedStartup = true;
                        android.util.Log.i("KipClubStartup", "firstVisualMs=" + (SystemClock.uptimeMillis() - performanceStartedAt));
                    }
                }
            });
        }
    }

    @Override public void onResume() {
        super.onResume();
        if (!observing && displays != null) {
            displays.registerDisplayListener(this, new Handler(Looper.getMainLooper()));
            IntentFilter filter = new IntentFilter(PowerManager.ACTION_POWER_SAVE_MODE_CHANGED);
            if (Build.VERSION.SDK_INT >= 33) registerReceiver(powerChange, filter, Context.RECEIVER_NOT_EXPORTED);
            else registerReceiver(powerChange, filter);
            observing = true;
            getWindow().addOnFrameMetricsAvailableListener(gpuFrames, new Handler(frameThread.getLooper()));
        }
        refreshDisplayPolicy();
    }
    @Override public void onPause() {
        if (observing) { observing = false; getWindow().removeOnFrameMetricsAvailableListener(gpuFrames); displays.unregisterDisplayListener(this); unregisterReceiver(powerChange); }
        super.onPause();
    }
    @Override public void onDestroy() {
        if (frameThread != null) frameThread.quitSafely();
        super.onDestroy();
    }
    @Override public void onDisplayAdded(int id) { }
    @Override public void onDisplayRemoved(int id) { }
    @Override public void onDisplayChanged(int id) {
        Display d = getWindowManager().getDefaultDisplay();
        if (d != null && d.getDisplayId() == id) refreshDisplayPolicy();
    }
    private boolean saving() {
        PowerManager p = (PowerManager) getSystemService(Context.POWER_SERVICE);
        return p != null && p.isPowerSaveMode();
    }
    void refreshDisplayPolicy() {
        Display d = getWindowManager().getDefaultDisplay();
        if (d == null) return;
        actualHz = d.getRefreshRate();
        Display.Mode current = d.getMode(), best = current;
        for (Display.Mode mode : d.getSupportedModes()) {
            if (mode.getPhysicalWidth() == current.getPhysicalWidth()
                    && mode.getPhysicalHeight() == current.getPhysicalHeight()
                    && mode.getRefreshRate() > best.getRefreshRate()) best = mode;
        }
        boolean save = saving();
        requestedHz = save ? 0f : best.getRefreshRate();
        WindowManager.LayoutParams a = getWindow().getAttributes();
        int modeId = save ? 0 : best.getModeId();
        if (a.preferredDisplayModeId != modeId || Math.abs(a.preferredRefreshRate - requestedHz) > .1f) {
            a.preferredDisplayModeId = modeId;
            // Window hint works with WebView; it does not own a public Surface on API 30–34.
            a.preferredRefreshRate = requestedHz;
            getWindow().setAttributes(a);
        }
        if (Build.VERSION.SDK_INT >= 35 && bridge != null) {
            getWindow().getDecorView().setRequestedFrameRate(requestedHz);
            bridge.getWebView().setRequestedFrameRate(requestedHz);
        }
        publishPerformanceState();
    }
    private void publishPerformanceState() {
        if (bridge != null) bridge.getWebView().evaluateJavascript(
            "window.dispatchEvent(new CustomEvent('itc:performance',{detail:" + performanceState().toString() + "}))", null);
    }
    JSObject performanceState() {
        JSObject r = new JSObject();
        ActivityManager a = (ActivityManager) getSystemService(Context.ACTIVITY_SERVICE);
        ActivityManager.MemoryInfo memory = new ActivityManager.MemoryInfo();
        if (a != null) a.getMemoryInfo(memory);
        Display d = getWindowManager().getDefaultDisplay();
        r.put("nativeGpuOverloaded", nativeGpuOverloaded);
        r.put("powerSave", saving()); r.put("lowRam", a != null && a.isLowRamDevice());
        r.put("memoryGB", memory.totalMem / 1073741824.0);
        r.put("cores", Runtime.getRuntime().availableProcessors());
        r.put("refreshRate", d == null ? 60 : d.getRefreshRate()); r.put("requestedHz", requestedHz);
        r.put("hardwareAccelerated", bridge != null && bridge.getWebView().isHardwareAccelerated());
        return r;
    }
    @Override public void onNewIntent(Intent intent) {
        super.onNewIntent(intent); setIntent(intent);
        NotificationReceipts.opened(this, intent);
    }
}
