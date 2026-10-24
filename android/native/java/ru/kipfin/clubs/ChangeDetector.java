package ru.kipfin.clubs;

import org.json.JSONException;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Set;

/** Сравнивает прошлый «снимок» статусов занятий с новым расписанием и возвращает изменения (отмена / перенос / возврат). Чистая логика — покрыта JUnit. */
public final class ChangeDetector {
    public static final class Change {
        public final Store.Event event;
        public final String kind; // cancelled | moved | restored
        Change(Store.Event e, String k) { event = e; kind = k; }
    }

    public static final class Result {
        public final List<Change> changes = new ArrayList<>();
        public String snapshot = "{}";
    }

    private ChangeDetector() {}

    static String fingerprint(Store.Event e) { return e.status + "|" + e.date + "|" + e.start + "|" + e.end; }

    /**
     * @param previous JSON {"key": "status|date|start|end", ...} — прошлый снимок (только отслеживаемые кружки)
     * @param events   новое расписание (окно синхронизации)
     * @param follows  отслеживаемые кружки; уведомляем только о них
     * @param nowMs    прошедшие занятия не интересны
     */
    public static Result diff(String previous, List<Store.Event> events, Set<Long> follows, long nowMs) {
        Result r = new Result();
        JSONObject prev;
        try { prev = new JSONObject(previous == null || previous.isEmpty() ? "{}" : previous); } catch (JSONException e) { prev = new JSONObject(); }
        JSONObject next = new JSONObject();
        boolean firstRun = prev.length() == 0;
        for (Store.Event e : events) {
            if (!follows.contains(e.clubId)) continue;
            String fp = fingerprint(e);
            try { next.put(e.key, fp); } catch (JSONException ignored) { }
            if (firstRun || e.endMs < nowMs) continue;
            String old = prev.optString(e.key, null);
            if (old == null) {
                // новое занятие в окне: сообщаем, только если оно сразу пришло отменённым/перенесённым и кружок уже отслеживался
                if (!e.status.equals("scheduled") && clubKnown(prev, e.clubId)) r.changes.add(new Change(e, e.status));
                continue;
            }
            if (old.equals(fp)) continue;
            String oldStatus = old.split("\\|", 2)[0];
            if (e.cancelled() && !"cancelled".equals(oldStatus)) r.changes.add(new Change(e, "cancelled"));
            else if (e.moved()) r.changes.add(new Change(e, "moved"));
            else if ("scheduled".equals(e.status) && !"scheduled".equals(oldStatus)) r.changes.add(new Change(e, "restored"));
        }
        // клубы, которые знаем (чтобы отличать «новый кружок в избранном» от «новой отмены»)
        try {
            Iterator<String> it = prev.keys();
            while (it.hasNext()) {
                String k = it.next();
                if (k.startsWith("club:") && follows.contains(Long.parseLong(k.substring(5)))) next.put(k, "1");
            }
            for (Long id : follows) next.put("club:" + id, "1");
        } catch (JSONException | NumberFormatException ignored) { }
        r.snapshot = next.toString();
        return r;
    }

    private static boolean clubKnown(JSONObject prev, long clubId) { return prev.has("club:" + clubId); }

    /** Текст уведомления на русском. */
    public static String[] text(Change c) {
        Store.Event e = c.event;
        String when = Format.dayLabel(e.date) + ", " + e.start + "–" + e.end;
        switch (c.kind) {
            case "cancelled": return new String[]{"Отменено: " + e.club, Format.dayLabel(e.originalDate) + ", " + e.start + suffix(e.comment)};
            case "moved": return new String[]{"Перенесено: " + e.club, "Новое время: " + when + (e.room.isEmpty() ? "" : ", " + e.room) + suffix(e.comment)};
            default: return new String[]{"Занятие состоится: " + e.club, when + (e.room.isEmpty() ? "" : ", " + e.room)};
        }
    }

    private static String suffix(String comment) { return comment == null || comment.isEmpty() ? "" : " — " + comment; }
}
