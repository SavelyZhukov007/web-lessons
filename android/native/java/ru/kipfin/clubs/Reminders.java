package ru.kipfin.clubs;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;

import java.util.HashSet;
import java.util.List;
import java.util.Set;

/** Напоминания за N минут до занятий «моих» кружков на ближайшие дни: AlarmManager (работает без Google Play Services). */
final class Reminders {
    static final String ACTION = "ru.kipfin.clubs.REMIND";
    private static final long WINDOW = 8L * 86_400_000L;

    private Reminders() {}

    static int requestCode(Store.Event e) { return ("r" + e.key).hashCode(); }

    static void reschedule(Context c) {
        AlarmManager am = (AlarmManager) c.getSystemService(Context.ALARM_SERVICE);
        SharedPreferences p = Store.prefs(c);
        // снимаем прошлые
        for (String code : p.getStringSet("alarm_codes", new HashSet<>())) {
            try { am.cancel(pending(c, Integer.parseInt(code), null)); } catch (NumberFormatException ignored) { }
        }
        Set<String> codes = new HashSet<>();
        int minutes = Store.reminderMinutes(c);
        if (minutes > 0 && !Store.follows(c).isEmpty()) {
            long now = System.currentTimeMillis();
            List<Store.Event> mine = Store.mine(c);
            for (Store.Event e : mine) {
                if (e.cancelled()) continue;
                long at = e.startMs - minutes * 60_000L;
                if (at <= now || at > now + WINDOW) continue;
                int code = requestCode(e);
                PendingIntent pi = pending(c, code, e);
                boolean exact = Build.VERSION.SDK_INT < 31 || am.canScheduleExactAlarms();
                if (exact && Build.VERSION.SDK_INT >= 23) am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pi);
                else if (Build.VERSION.SDK_INT >= 23) am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pi); // точность ±10 мин без разрешения на точные будильники
                else am.set(AlarmManager.RTC_WAKEUP, at, pi);
                codes.add(String.valueOf(code));
            }
        }
        p.edit().putStringSet("alarm_codes", codes).apply();
    }

    private static PendingIntent pending(Context c, int code, Store.Event e) {
        Intent i = new Intent(c, ReminderReceiver.class).setAction(ACTION);
        if (e != null) {
            i.putExtra("key", e.key);
            i.putExtra("club_id", e.clubId);
            i.putExtra("title", e.club);
            i.putExtra("text", e.start + "–" + e.end + (e.room.isEmpty() ? "" : " · " + e.room) + (e.moved() ? " (перенесено)" : ""));
        }
        return PendingIntent.getBroadcast(c, code, i, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }
}
