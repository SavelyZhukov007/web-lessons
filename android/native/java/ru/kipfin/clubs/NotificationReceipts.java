package ru.kipfin.clubs;

import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;

/** Best-effort anonymous client display/open acknowledgements, never a claim about transport delivery. */
final class NotificationReceipts {
    private static final Executor EXECUTOR = new ThreadPoolExecutor(1, 1, 0, TimeUnit.SECONDS,
        new ArrayBlockingQueue<Runnable>(50), new ThreadPoolExecutor.DiscardPolicy());
    private NotificationReceipts() {}
    static void opened(Context context, Intent intent) {
        if (intent == null || intent.getData() == null) return;
        Uri uri = intent.getData();
        if (!"itckruzhki".equals(uri.getScheme()) || !"open".equals(uri.getHost())) return;
        mark(context, uri.toString(), "opened");
    }
    static void mark(Context context, String path, String kind) {
        final long id;
        try { id = Long.parseLong(Uri.parse(path).getQueryParameter("bc")); }
        catch (Exception ignored) { return; }
        if (id <= 0 || id >= (1L << 53)) return;
        final Context app = context.getApplicationContext();
        if (Store.demo(app)) return;
        final String server = Store.server(app).replaceAll("/+$", "");
        if (server.isEmpty()) return;
        EXECUTOR.execute(() -> {
            HttpURLConnection connection = null;
            try {
                connection = (HttpURLConnection)new URL(server + "/api/announcements/" + id + "/receipt").openConnection();
                connection.setConnectTimeout(3000); connection.setReadTimeout(3000); connection.setRequestMethod("POST");
                connection.setRequestProperty("Content-Type", "application/json"); connection.setDoOutput(true);
                String payload = new org.json.JSONObject().put("install_id", Announcements.installId(app))
                    .put("channel", "android").put("kind", kind).toString();
                try (java.io.OutputStream output = connection.getOutputStream()) { output.write(payload.getBytes(StandardCharsets.UTF_8)); }
                connection.getResponseCode();
            } catch (Exception ignored) { /* offline/adblock/OS suspension: metrics deliberately undercount */ }
            finally { if (connection != null) connection.disconnect(); }
        });
    }
}
