package ru.kipfin.clubs;

import android.content.Context;
import android.os.PowerManager;
import androidx.annotation.NonNull;
import androidx.webkit.WebViewCompat;
import androidx.webkit.WebViewOutcomeReceiver;
import androidx.webkit.WebViewStartUpConfig;
import androidx.webkit.WebViewStartUpResult;
import androidx.webkit.WebViewStartupException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

/** Supported background-capable provider warmup, never a second hidden WebView. */
final class WebViewWarmup {
    private static final AtomicBoolean started = new AtomicBoolean();
    static void start(Context context) {
        PowerManager power = (PowerManager) context.getSystemService(Context.POWER_SERVICE);
        if (power != null && power.isPowerSaveMode()) return;
        if (!started.compareAndSet(false, true)) return;
        ExecutorService executor = Executors.newSingleThreadExecutor(r -> {
            Thread thread = new Thread(() -> { android.os.Process.setThreadPriority(android.os.Process.THREAD_PRIORITY_BACKGROUND); r.run(); }, "kipclub-webview-warmup");
            return thread;
        });
        try {
            WebViewCompat.startUpWebView(context.getApplicationContext(), new WebViewStartUpConfig.Builder(executor)
                .setShouldRunUiThreadStartUpTasks(false).build(),
                new WebViewOutcomeReceiver<WebViewStartUpResult, WebViewStartupException>() {
                    @Override public void onResult(@NonNull WebViewStartUpResult result) { executor.shutdown(); }
                    @Override public void onError(@NonNull WebViewStartupException error) { executor.shutdown(); }
                });
        } catch (RuntimeException | LinkageError ignored) { executor.shutdown(); } // normal BridgeActivity initialization remains the fallback
    }
}
