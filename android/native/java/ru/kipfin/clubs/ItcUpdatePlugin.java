package ru.kipfin.clubs;

import android.content.Intent;
import android.content.pm.PackageInfo;
import android.net.Uri;
import android.os.Build;

import androidx.core.content.FileProvider;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.ByteArrayOutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.MessageDigest;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Обновление приложения внутри приложения (без магазина): проверка GET /api/app/android (нативный HTTP, без CORS),
 * скачивание APK с прогрессом, проверка sha256 и запуск системного установщика через FileProvider.
 * Тот же applicationId и ключ подписи → ставится поверх, данные сохраняются. Ошибки сети — тихие (JS решает, что показать).
 * Плюс «splashReady»: веб-экран загрузки отрисован → системный SplashScreen можно убрать без мигания.
 */
@CapacitorPlugin(name = "ItcUpdate")
public class ItcUpdatePlugin extends Plugin {
    private static final AtomicBoolean downloading = new AtomicBoolean(false);

    @PluginMethod
    public void splashReady(PluginCall call) {
        MainActivity.webReady = true;
        call.resolve();
    }

    @PluginMethod
    public void appInfo(PluginCall call) {
        JSObject r = new JSObject();
        try {
            PackageInfo pi = getContext().getPackageManager().getPackageInfo(getContext().getPackageName(), 0);
            r.put("versionName", pi.versionName);
            r.put("versionCode", Build.VERSION.SDK_INT >= 28 ? (int) pi.getLongVersionCode() : pi.versionCode);
        } catch (Exception e) { r.put("versionCode", 0); }
        r.put("packageName", getContext().getPackageName());
        r.put("canInstall", Build.VERSION.SDK_INT < 26 || getContext().getPackageManager().canRequestPackageInstalls());
        call.resolve(r);
    }

    /** GET url → {status, body}. Таймауты короткие: проверка не должна мешать запуску. */
    @PluginMethod
    public void check(PluginCall call) {
        final String url = call.getString("url", "");
        new Thread(() -> {
            HttpURLConnection c = null;
            try {
                c = (HttpURLConnection) new URL(url).openConnection();
                c.setConnectTimeout(5000); c.setReadTimeout(8000);
                c.setRequestProperty("Accept", "application/json");
                int code = c.getResponseCode();
                InputStream in = code < 400 ? c.getInputStream() : c.getErrorStream();
                ByteArrayOutputStream out = new ByteArrayOutputStream();
                byte[] buf = new byte[8192]; int n; long total = 0;
                while (in != null && (n = in.read(buf)) > 0 && total < 256 * 1024) { out.write(buf, 0, n); total += n; }
                JSObject r = new JSObject();
                r.put("status", code);
                r.put("body", out.toString("UTF-8"));
                call.resolve(r);
            } catch (Exception e) {
                call.reject("network", e);
            } finally { if (c != null) c.disconnect(); }
        }).start();
    }

    /** url, sha256 (hex), size → скачивает в cache/updates/update.apk, события «progress» {loaded,total}. */
    @PluginMethod
    public void download(PluginCall call) {
        final String url = call.getString("url", "");
        final String sha = call.getString("sha256", "").toLowerCase();
        // без контрольной суммы не ставим (только https/http — без file:/content:)
        if (!sha.matches("[0-9a-f]{64}")) { call.reject("sha256 missing"); return; }
        if (!url.startsWith("https://") && !url.startsWith("http://")) { call.reject("bad url"); return; }
        if (!downloading.compareAndSet(false, true)) { call.reject("busy"); return; }
        new Thread(() -> {
            HttpURLConnection c = null;
            File dir = new File(getContext().getCacheDir(), "updates");
            File tmp = new File(dir, "update.apk.part"), apk = new File(dir, "update.apk");
            try {
                dir.mkdirs(); apk.delete(); tmp.delete();
                c = (HttpURLConnection) new URL(url).openConnection();
                c.setConnectTimeout(10000); c.setReadTimeout(20000);
                if (c.getResponseCode() != 200) throw new Exception("HTTP " + c.getResponseCode());
                long total = c.getContentLengthLong();
                if (total <= 0) total = call.getLong("size", 0L);
                MessageDigest md = MessageDigest.getInstance("SHA-256");
                long loaded = 0, lastEmit = 0;
                try (InputStream in = c.getInputStream(); FileOutputStream out = new FileOutputStream(tmp)) {
                    byte[] buf = new byte[64 * 1024]; int n;
                    while ((n = in.read(buf)) > 0) {
                        out.write(buf, 0, n); md.update(buf, 0, n); loaded += n;
                        long now = System.currentTimeMillis();
                        if (now - lastEmit > 120) { lastEmit = now; emit(loaded, total); }
                    }
                }
                emit(loaded, total);
                String got = hex(md.digest());
                if (!sha.equals(got)) { tmp.delete(); throw new Exception("sha256"); }
                if (!tmp.renameTo(apk)) throw new Exception("rename");
                JSObject r = new JSObject(); r.put("path", apk.getAbsolutePath()); r.put("sha256", got); r.put("size", loaded);
                call.resolve(r);
            } catch (Exception e) {
                call.reject(e.getMessage() == null ? "download" : e.getMessage(), e);
            } finally { if (c != null) c.disconnect(); downloading.set(false); }
        }).start();
    }

    /** Запускает установщик. Нет разрешения «Установка из этого источника» → открывает его настройку ({needsPermission:true}). */
    @PluginMethod
    public void install(PluginCall call) {
        File apk = new File(new File(getContext().getCacheDir(), "updates"), "update.apk");
        JSObject r = new JSObject();
        if (!apk.isFile()) { call.reject("no-file"); return; }
        if (Build.VERSION.SDK_INT >= 26 && !getContext().getPackageManager().canRequestPackageInstalls()) {
            Intent s = new Intent(android.provider.Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:" + getContext().getPackageName()));
            s.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            getContext().startActivity(s);
            r.put("needsPermission", true);
            call.resolve(r);
            return;
        }
        Uri uri = FileProvider.getUriForFile(getContext(), getContext().getPackageName() + ".fileprovider", apk);
        Intent i = new Intent(Intent.ACTION_VIEW).setDataAndType(uri, "application/vnd.android.package-archive");
        i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
        getContext().startActivity(i);
        r.put("started", true);
        call.resolve(r);
    }

    /** Открыть ссылку во внешнем браузере (запасной путь: /android/download). */
    @PluginMethod
    public void openExternal(PluginCall call) {
        Intent i = new Intent(Intent.ACTION_VIEW, Uri.parse(call.getString("url", ""))).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        try { getContext().startActivity(i); call.resolve(); } catch (Exception e) { call.reject("no-browser"); }
    }

    private void emit(long loaded, long total) {
        JSObject p = new JSObject(); p.put("loaded", loaded); p.put("total", total);
        notifyListeners("progress", p);
    }

    static String hex(byte[] b) {
        StringBuilder s = new StringBuilder();
        for (byte x : b) s.append(String.format("%02x", x));
        return s.toString();
    }
}
