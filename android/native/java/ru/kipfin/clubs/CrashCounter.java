package ru.kipfin.clubs;

import android.content.Context;
import android.content.SharedPreferences;

/**
 * Счётчик нативных падений для анонимной статистики (native_crash): только число и подсистема
 * (webview / storage / net / ui), без стека, текста исключения и данных устройства.
 * Обработчик ставится поверх системного и всегда передаёт падение дальше.
 */
final class CrashCounter {
    static final String COUNT = "crash_count", KIND = "crash_kind";
    private static volatile boolean installed;
    private CrashCounter() {}

    static void install(Context context) {
        if (installed) return;
        installed = true;
        final Context app = context.getApplicationContext();
        final Thread.UncaughtExceptionHandler next = Thread.getDefaultUncaughtExceptionHandler();
        Thread.setDefaultUncaughtExceptionHandler((thread, error) -> {
            try {
                SharedPreferences prefs = Store.prefs(app);
                prefs.edit().putInt(COUNT, prefs.getInt(COUNT, 0) + 1).putString(KIND, kind(error)).commit();
            } catch (Throwable ignored) { /* падение не должно ломать системный обработчик */ }
            if (next != null) next.uncaughtException(thread, error);
        });
    }

    static String kind(Throwable error) {
        for (Throwable t = error; t != null; t = t.getCause()) {
            for (StackTraceElement frame : t.getStackTrace()) {
                String c = frame.getClassName();
                if (c.startsWith("android.webkit") || c.startsWith("org.chromium") || c.startsWith("com.getcapacitor")) return "webview";
                if (c.startsWith("android.database") || c.startsWith("java.io") || c.startsWith("android.content.SharedPreferences")) return "storage";
                if (c.startsWith("java.net") || c.startsWith("javax.net") || c.startsWith("okhttp3")) return "net";
            }
            if (t instanceof java.io.IOException) return "storage";
        }
        return "ui";
    }

    /** Прочитать и обнулить: {count, subsystem}. */
    static int[] takeCount(Context context, String[] kindOut) {
        SharedPreferences prefs = Store.prefs(context);
        int count = prefs.getInt(COUNT, 0);
        kindOut[0] = prefs.getString(KIND, "ui");
        if (count > 0) prefs.edit().remove(COUNT).remove(KIND).apply();
        return new int[]{count};
    }
}
