package ru.kipfin.clubs;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** Срабатывание напоминания; после перезагрузки/обновления приложения — восстанавливает будильники и виджеты. */
public class ReminderReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context c, Intent intent) {
        String a = intent.getAction();
        if(PersonalNotifications.FLUSH.equals(a)){PersonalNotifications.flush(c);return;}
        if(PersonalNotifications.DIGEST.equals(a)){PersonalNotifications.digest(c);return;}
        if (Reminders.ACTION.equals(a)) {
            String key=intent.getStringExtra("key");long now=System.currentTimeMillis();
            if(Store.reminderMinutes(c)<=0)return;
            for(Store.Event e:Store.events(c))if(e.key.equals(key)){
                if(e.cancelled()||!Store.follows(c).contains(e.clubId)||e.startMs<=now)return;
                if(e.startMs-Store.reminderMinutes(c)*60000L>now+60000){Reminders.reschedule(c);return;}
                long minutes=Math.max(1,(e.startMs-now+59999)/60000);
                Notifier.post(c,Notifier.CH_REMIND,("n"+key).hashCode(),e.club+" — через "+minutes+" мин",e.start+"–"+e.end+(e.room.isEmpty()?"":" · "+e.room),"/club?id="+e.clubId);return;
            }
            return;
        }
        // BOOT_COMPLETED / MY_PACKAGE_REPLACED / TIME_SET / TIMEZONE_CHANGED
        Reminders.reschedule(c);
        Widgets.updateAll(c);
        SyncWorker.schedule(c);
    }
}
