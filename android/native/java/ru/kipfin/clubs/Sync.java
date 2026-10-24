package ru.kipfin.clubs;

import android.content.Context;
import android.content.SharedPreferences;

import java.util.List;

/** Единая точка применения нового расписания (из WebView или из фонового воркера). */
final class Sync {
    private Sync() {}

    static synchronized int apply(Context c, String eventsJson) {
        SharedPreferences p = Store.prefs(c);
        List<Store.Event> events = Store.parse(eventsJson);
        int notified = 0;
        ChangeDetector.Result r = ChangeDetector.diff(p.getString("snapshot", "{}"), events, Store.follows(c), System.currentTimeMillis());
        if (Store.notifyChanges(c)) {
            for (ChangeDetector.Change ch : r.changes) {
                String[] t = ChangeDetector.text(ch);
                Notifier.post(c, Notifier.CH_CHANGES, ("c" + ch.event.key + ch.kind).hashCode(), t[0], t[1], "/club?id=" + ch.event.clubId);
                notified++;
            }
        }
        p.edit().putString("events", eventsJson).putString("snapshot", r.snapshot).putLong("updated", System.currentTimeMillis()).apply();
        Reminders.reschedule(c);
        Widgets.updateAll(c);
        return notified;
    }
}
