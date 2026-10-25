package ru.kipfin.clubs;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;
import java.util.UUID;

/**
 * Объявления от администрации для APK (без FCM/GMS): опрос GET /api/announcements при открытии
 * приложения и в SyncWorker (~раз в 30 минут). Последний показанный id хранится в Store —
 * одно объявление не приходит дважды; на первом запуске только запоминаем id, старые не показываем.
 */
final class Announcements {
    static final String K_LAST = "ann_last_id";
    static final String K_INSTALL = "install_id";

    private Announcements() {}

    static final class Item {
        long id;
        String title, body, url;
    }

    /** Ответ сервера: {items:[{id,title,body,url}], last_id}. */
    static final class Feed {
        final List<Item> items = new ArrayList<>();
        long lastId;
    }

    static Feed parse(String json) {
        Feed f = new Feed();
        if (json == null || json.isEmpty()) return f;
        try {
            JSONObject o = new JSONObject(json);
            f.lastId = o.optLong("last_id", 0);
            JSONArray a = o.optJSONArray("items");
            for (int i = 0; a != null && i < a.length(); i++) {
                JSONObject x = a.optJSONObject(i);
                if (x == null || x.optLong("id", 0) <= 0) continue;
                Item it = new Item();
                it.id = x.getLong("id");
                it.title = x.optString("title", "").trim();
                it.body = x.optString("body", "").trim();
                String u = x.optString("url", "/");
                it.url = u.startsWith("/") && !u.startsWith("//") ? u : "/"; // только внутренние ссылки
                if (it.title.isEmpty()) it.title = "Объявление";
                f.items.add(it);
            }
        } catch (JSONException ignored) { /* битый ответ — как пустой */ }
        return f;
    }

    /** Что показать: только новее уже показанного; на первом запуске (seen < 0) — ничего. */
    static List<Item> fresh(Feed f, long seen) {
        List<Item> out = new ArrayList<>();
        if (seen < 0) return out;
        for (Item it : f.items) if (it.id > seen) out.add(it);
        return out;
    }

    /** Новое значение «последнего показанного». */
    static long nextSeen(Feed f, long seen) {
        long m = Math.max(seen, f.lastId);
        for (Item it : f.items) m = Math.max(m, it.id);
        return m;
    }

    static int notificationId(long id) { return Push.announcementKey(id).hashCode(); }

    static String installId(Context c) {
        SharedPreferences p = Store.prefs(c);
        String id = p.getString(K_INSTALL, "");
        if (id.length() < 16) {
            id = UUID.randomUUID().toString().replace("-", "");
            p.edit().putString(K_INSTALL, id).apply();
        }
        return id;
    }

    static String query(long since, Set<Long> clubs, String device, boolean off) {
        StringBuilder cs = new StringBuilder();
        for (Long id : new TreeSet<>(clubs)) { if (cs.length() > 0) cs.append(','); cs.append(id); }
        try {
            return "/api/announcements?since=" + Math.max(0, since) + "&clubs=" + URLEncoder.encode(cs.toString(), "UTF-8")
                + "&device=" + device + "&off=" + (off ? 1 : 0);
        } catch (java.io.UnsupportedEncodingException e) { throw new IllegalStateException(e); }
    }

    /** Синхронный запрос — вызывать не из главного потока. Возвращает число показанных уведомлений. */
    static synchronized int check(Context c) {
        String server = Store.server(c).replaceAll("/+$", "");
        if (Store.demo(c) || server.isEmpty()) return 0;
        SharedPreferences p = Store.prefs(c);
        long seen = p.getLong(K_LAST, -1);
        boolean off = !Store.notifyAnnouncements(c);
        Feed f;
        try { f = parse(get(server + query(seen, Store.follows(c), installId(c), off))); }
        catch (Exception e) { return 0; }
        int shown = 0;
        if (!off) {
            for (Item it : fresh(f, seen)) {
                if (!Push.claim(c, Push.announcementKey(it.id))) continue; // уже пришло через FCM
                Notifier.post(c, Notifier.CH_ANN, notificationId(it.id), it.title, it.body, it.url);
                shown++;
            }
        }
        p.edit().putLong(K_LAST, nextSeen(f, seen)).apply(); // выключенный переключатель — тоже «прочитано»: при включении старое не всплывёт
        return shown;
    }

    private static String get(String url) throws Exception {
        HttpURLConnection con = (HttpURLConnection) new URL(url).openConnection();
        con.setConnectTimeout(10_000);
        con.setReadTimeout(15_000);
        con.setRequestProperty("Accept", "application/json");
        try {
            if (con.getResponseCode() != 200) throw new IllegalStateException("HTTP " + con.getResponseCode());
            try (InputStream in = con.getInputStream(); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
                byte[] buf = new byte[8192];
                for (int n; (n = in.read(buf)) > 0; ) out.write(buf, 0, n);
                return out.toString("UTF-8");
            }
        } finally { con.disconnect(); }
    }
}
