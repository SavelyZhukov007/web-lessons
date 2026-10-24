package ru.kipfin.clubs;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.text.ParseException;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Calendar;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.TimeZone;

/** Общее состояние нативной части: события «моих» кружков, настройки уведомлений, адрес сервера. Без Google Play Services. */
public final class Store {
    static final String PREFS = "itc_native";
    static final TimeZone MSK = TimeZone.getTimeZone("Europe/Moscow");

    private Store() {}

    static SharedPreferences prefs(Context c) { return c.getSharedPreferences(PREFS, Context.MODE_PRIVATE); }

    /** Одно занятие (occurrence) из /api/schedule. */
    public static final class Event {
        public String key;        // session_id:original_date — стабильный ключ для сравнения
        public long sessionId;
        public long clubId;
        public String club, room, leader, status, date, start, end, originalDate, comment;
        public int color;
        public long startMs, endMs;

        public boolean cancelled() { return "cancelled".equals(status); }
        public boolean moved() { return "moved".equals(status); }

        static Event from(JSONObject o) throws JSONException {
            Event e = new Event();
            e.sessionId = o.getLong("session_id");
            e.clubId = o.getLong("club_id");
            e.club = o.optString("club_name", "Занятие");
            e.room = o.optString("room_name", "");
            e.leader = o.optString("leader_name", "");
            e.status = o.optString("status", "scheduled");
            e.date = o.getString("date");
            e.start = o.getString("start_time");
            e.end = o.getString("end_time");
            e.originalDate = o.optString("original_date", e.date);
            e.comment = o.optString("comment", "");
            e.key = e.sessionId + ":" + e.originalDate;
            e.color = parseColor(o.optString("category_color", ""));
            e.startMs = epoch(e.date, e.start);
            e.endMs = epoch(e.date, e.end);
            return e;
        }
    }

    static int parseColor(String hex) {
        if (hex != null && hex.matches("#[0-9a-fA-F]{6}")) return 0xFF000000 | Integer.parseInt(hex.substring(1), 16);
        return 0xFF606963;
    }

    static long epoch(String date, String hm) {
        SimpleDateFormat f = new SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.US);
        f.setTimeZone(MSK);
        try { return f.parse(date + " " + hm).getTime(); } catch (ParseException e) { return 0; }
    }

    static String mskDate(long ms) {
        SimpleDateFormat f = new SimpleDateFormat("yyyy-MM-dd", Locale.US);
        f.setTimeZone(MSK);
        return f.format(ms);
    }

    static String mondayOf(long ms, int plusWeeks) {
        Calendar c = Calendar.getInstance(MSK, Locale.US);
        c.setTimeInMillis(ms);
        int dow = c.get(Calendar.DAY_OF_WEEK); // 1=вс
        c.add(Calendar.DAY_OF_MONTH, -((dow + 5) % 7) + 7 * plusWeeks);
        return mskDate(c.getTimeInMillis());
    }

    public static List<Event> parse(String json) {
        List<Event> out = new ArrayList<>();
        if (json == null || json.isEmpty()) return out;
        try {
            JSONArray a = new JSONArray(json);
            for (int i = 0; i < a.length(); i++) {
                try { out.add(Event.from(a.getJSONObject(i))); } catch (JSONException ignored) { /* битая запись */ }
            }
        } catch (JSONException ignored) { /* пусто */ }
        Collections.sort(out, (x, y) -> Long.compare(x.startMs, y.startMs));
        return out;
    }

    static List<Event> events(Context c) { return parse(prefs(c).getString("events", "[]")); }

    static Set<Long> follows(Context c) {
        Set<Long> s = new HashSet<>();
        try {
            JSONArray a = new JSONArray(prefs(c).getString("follows", "[]"));
            for (int i = 0; i < a.length(); i++) s.add(a.getLong(i));
        } catch (JSONException ignored) { }
        return s;
    }

    /** События для виджетов/напоминаний: «мои» кружки; если ничего не отмечено — всё расписание. */
    static List<Event> mine(Context c) {
        Set<Long> f = follows(c);
        List<Event> all = events(c);
        if (f.isEmpty()) return all;
        List<Event> out = new ArrayList<>();
        for (Event e : all) if (f.contains(e.clubId)) out.add(e);
        return out;
    }

    static int reminderMinutes(Context c) { return prefs(c).getInt("reminder_minutes", 15); }
    static boolean notifyChanges(Context c) { return prefs(c).getBoolean("notify_changes", true); }
    static String server(Context c) { return prefs(c).getString("server", ""); }
    static boolean demo(Context c) { return prefs(c).getBoolean("demo", false); }
}
