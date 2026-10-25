package ru.kipfin.clubs;

import android.content.Context;
import android.content.SharedPreferences;

import androidx.work.OneTimeWorkRequest;
import androidx.work.WorkManager;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

/**
 * Push через FCM (если APK собран с google-services.json) — поверх опроса, который остаётся резервным путём.
 * Сервер шлёт только data-сообщения; здесь они превращаются в уведомления через те же каналы Notifier.
 * Дедупликация общая с опросом (Sync / Announcements): один и тот же ключ события показывается один раз.
 * Чистая логика (parse, ключи, dedupe) покрыта JUnit; без Firebase-классов — компилируется и без FCM.
 */
final class Push {
    static final String K_SHOWN = "shown_keys";
    static final String K_TOKEN = "fcm_token";
    static final String K_REG_SIG = "fcm_reg_sig";
    static final String K_REG_AT = "fcm_reg_at";
    static final int MAX_KEYS = 200;
    static final long REREGISTER_MS = 24L * 3600 * 1000;

    private Push() {}

    // ---------- ключи событий (одинаковые для FCM и опроса) ----------

    static String announcementKey(long id) { return "a" + id; }

    /** kind: cancelled | moved | restored (как в ChangeDetector). Для переноса в ключ входит новое время — повторный перенос не «проглатывается». */
    static String changeKey(String eventKey, String kind, String date, String start) {
        return "c" + eventKey + kind + ("moved".equals(kind) ? "|" + date + "|" + start : "");
    }

    static String changeKey(ChangeDetector.Change ch) { return changeKey(ch.event.key, ch.kind, ch.event.date, ch.event.start); }

    // ---------- dedupe: последние MAX_KEYS показанных ключей ----------

    static List<String> keys(String raw) {
        List<String> out = new ArrayList<>();
        if (raw == null || raw.isEmpty()) return out;
        out.addAll(Arrays.asList(raw.split("\n")));
        out.remove("");
        return out;
    }

    /** Новое содержимое списка после отметки key (старые ключи вытесняются). */
    static String mark(String raw, String key) {
        List<String> k = keys(raw);
        k.remove(key);
        k.add(key);
        while (k.size() > MAX_KEYS) k.remove(0);
        StringBuilder sb = new StringBuilder(); // String.join — только с API 26, а minSdk 24
        for (String x : k) { if (sb.length() > 0) sb.append('\n'); sb.append(x); }
        return sb.toString();
    }

    static boolean seen(String raw, String key) { return keys(raw).contains(key); }

    /** true — показываем (и запоминаем); false — уже показано другим путём. */
    static synchronized boolean claim(Context c, String key) {
        SharedPreferences p = Store.prefs(c);
        String raw = p.getString(K_SHOWN, "");
        if (seen(raw, key)) return false;
        p.edit().putString(K_SHOWN, mark(raw, key)).commit();
        return true;
    }

    // ---------- разбор data-сообщения ----------

    static final class Msg {
        String type, key, channel, title, body, url;
        long clubId;
        boolean sync; // освежить расписание (виджеты/напоминания) после сообщения
    }

    static String safeUrl(String u) { return u != null && u.startsWith("/") && !u.startsWith("//") ? u : "/"; }

    private static String s(Map<String, String> d, String k) { String v = d.get(k); return v == null ? "" : v.trim(); }

    private static long num(String v) { try { return Long.parseLong(v); } catch (NumberFormatException e) { return 0; } }

    /** null — сообщение не распознано. */
    static Msg parse(Map<String, String> d) {
        if (d == null) return null;
        Msg m = new Msg();
        m.type = s(d, "type");
        m.title = s(d, "title");
        m.body = s(d, "body");
        m.url = safeUrl(s(d, "url"));
        m.clubId = num(s(d, "club_id"));
        switch (m.type) {
            case "announcement": {
                long id = num(s(d, "id"));
                if (id <= 0) return null;
                m.key = announcementKey(id);
                m.channel = Notifier.CH_ANN;
                if (m.title.isEmpty()) m.title = "Объявление";
                return m;
            }
            case "cancel":
            case "reschedule": {
                String sid = s(d, "session_id"), od = s(d, "original_date");
                if (sid.isEmpty() || od.isEmpty() || m.title.isEmpty()) return null;
                boolean moved = "reschedule".equals(m.type);
                m.key = changeKey(sid + ":" + od, moved ? "moved" : "cancelled", s(d, "new_date"), s(d, "new_start"));
                m.channel = Notifier.CH_CHANGES;
                m.sync = true;
                return m;
            }
            case "schedule-change":
                m.sync = true; // само уведомление (если нужно) покажет ChangeDetector после синхронизации
                return m;
            case "update-available": {
                String v = s(d, "version");
                if (v.isEmpty()) return null;
                m.key = "u" + v;
                m.channel = Notifier.CH_ANN;
                if (m.title.isEmpty()) m.title = "Доступно обновление KipClub";
                if (m.body.isEmpty()) m.body = "Версия " + v + ". Откройте приложение, чтобы обновить.";
                return m;
            }
            default:
                return null;
        }
    }

    /** Показывать ли с учётом настроек пользователя (как при опросе). */
    static boolean wanted(Msg m, boolean changesOn, boolean annOn, Set<Long> follows) {
        if (m.key == null) return false;
        if (Notifier.CH_CHANGES.equals(m.channel)) return changesOn && follows.contains(m.clubId);
        if ("announcement".equals(m.type)) return annOn;
        return true;
    }

    // ---------- Android ----------

    /** Обработка входящего data-сообщения (вызывает ItcMessagingService). */
    static void handle(Context c, Map<String, String> data) {
        Msg m = parse(data);
        if (m == null || Store.demo(c)) return;
        if (wanted(m, Store.notifyChanges(c), Store.notifyAnnouncements(c), Store.follows(c)) && claim(c, m.key)) {
            Notifier.post(c, m.channel, m.key.hashCode(), m.title, m.body, m.url);
        }
        if (m.sync) {
            try { WorkManager.getInstance(c).enqueue(new OneTimeWorkRequest.Builder(SyncWorker.class).build()); }
            catch (Exception ignored) { }
        }
    }

    static void saveToken(Context c, String token) {
        Store.prefs(c).edit().putString(K_TOKEN, token == null ? "" : token).remove(K_REG_SIG).apply();
    }

    /** Запросить токен у Firebase, если APK собран с FCM (класс ItcFcm есть только в такой сборке). */
    static void refresh(Context c) {
        if (Store.demo(c) || Store.server(c).isEmpty()) return;
        try {
            Class.forName("ru.kipfin.clubs.ItcFcm").getMethod("fetchToken", Context.class).invoke(null, c.getApplicationContext());
        } catch (ClassNotFoundException e) {
            // сборка без FCM — работает опрос
        } catch (Exception ignored) { }
    }

    static String body(String device, String token, String version, Set<Long> follows, boolean ann, boolean changes) {
        try {
            JSONObject o = new JSONObject();
            o.put("device_id", device);
            o.put("token", token);
            o.put("platform", "android");
            o.put("app_version", version);
            JSONArray a = new JSONArray();
            for (Long id : new TreeSet<>(follows)) a.put(id);
            o.put("club_ids", a);
            o.put("announcements", ann);
            o.put("changes", changes);
            return o.toString();
        } catch (org.json.JSONException e) { throw new IllegalStateException(e); }
    }

    /** POST /api/app/devices в фоне; повторно — только если что-то изменилось или раз в сутки. */
    static void registerAsync(Context c) {
        Context app = c.getApplicationContext();
        new Thread(() -> { try { register(app); } catch (Exception ignored) { } }, "itc-fcm-register").start();
    }

    static synchronized void register(Context c) throws Exception {
        SharedPreferences p = Store.prefs(c);
        String token = p.getString(K_TOKEN, "");
        String server = Store.server(c).replaceAll("/+$", "");
        if (token.isEmpty() || server.isEmpty() || Store.demo(c)) return;
        String version;
        try { version = c.getPackageManager().getPackageInfo(c.getPackageName(), 0).versionName; } catch (Exception e) { version = ""; }
        String json = body(Announcements.installId(c), token, version == null ? "" : version, Store.follows(c),
            Store.notifyAnnouncements(c), Store.notifyChanges(c));
        String sig = server + "|" + json;
        long now = System.currentTimeMillis();
        if (sig.equals(p.getString(K_REG_SIG, "")) && now - p.getLong(K_REG_AT, 0) < REREGISTER_MS) return;
        HttpURLConnection con = (HttpURLConnection) new URL(server + "/api/app/devices").openConnection();
        con.setConnectTimeout(10_000);
        con.setReadTimeout(15_000);
        con.setRequestMethod("POST");
        con.setDoOutput(true);
        con.setRequestProperty("Content-Type", "application/json; charset=utf-8");
        try {
            try (OutputStream out = con.getOutputStream()) { out.write(json.getBytes(StandardCharsets.UTF_8)); }
            int code = con.getResponseCode();
            if (code >= 200 && code < 300) p.edit().putString(K_REG_SIG, sig).putLong(K_REG_AT, now).apply();
        } finally { con.disconnect(); }
    }
}
