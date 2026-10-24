package ru.kipfin.clubs;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** Срабатывание напоминания; после перезагрузки/обновления приложения — восстанавливает будильники и виджеты. */
public class ReminderReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context c, Intent intent) {
        String a = intent.getAction();
        if (Reminders.ACTION.equals(a)) {
            String key = intent.getStringExtra("key");
            // занятие могли отменить после постановки будильника — сверяемся с актуальными данными
            for (Store.Event e : Store.events(c)) {
                if (e.key.equals(key) && e.cancelled()) return;
            }
            int minutes = Store.reminderMinutes(c);
            String when = minutes >= 60 ? "через " + (minutes / 60) + " ч" : "через " + minutes + " мин";
            Notifier.post(c, Notifier.CH_REMIND, ("n" + key).hashCode(), intent.getStringExtra("title") + " — " + when,
                intent.getStringExtra("text"), "/club?id=" + intent.getLongExtra("club_id", 0));
            return;
        }
        // BOOT_COMPLETED / MY_PACKAGE_REPLACED / TIME_SET / TIMEZONE_CHANGED
        Reminders.reschedule(c);
        Widgets.updateAll(c);
        SyncWorker.schedule(c);
    }
}
