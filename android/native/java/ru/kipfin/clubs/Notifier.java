package ru.kipfin.clubs;

import android.Manifest;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;

import androidx.core.app.NotificationCompat;
import androidx.core.app.NotificationManagerCompat;
import androidx.core.content.ContextCompat;

/** Локальные уведомления (без FCM/GMS): напоминания, изменения расписания, объявления. */
final class Notifier {
    static final String CH_DIGEST = "itc_digest";
    static final String CH_REMIND = "itc_reminders";
    static final String CH_CHANGES = "itc_changes";
    static final String CH_CANCEL = "itc_cancellations";
    static final String CH_MOVE = "itc_moves";
    static final String CH_ANN = "itc_announcements";

    private Notifier() {}

    static void channels(Context c) {
        if (Build.VERSION.SDK_INT < 26) return;
        NotificationManager nm = c.getSystemService(NotificationManager.class);
        NotificationChannel previous = nm.getNotificationChannel(CH_CHANGES);
        NotificationChannel r = new NotificationChannel(CH_REMIND, "Напоминания о занятиях", NotificationManager.IMPORTANCE_DEFAULT);
        r.setDescription("Перед началом занятий отмеченных кружков");
        NotificationChannel ch = new NotificationChannel(CH_CHANGES, "Возврат в расписание", NotificationManager.IMPORTANCE_HIGH);
        ch.setDescription("Когда отменённое занятие снова появилось в расписании");
        NotificationChannel an = new NotificationChannel(CH_ANN, "Объявления", NotificationManager.IMPORTANCE_DEFAULT);
        an.setDescription("Сообщения от администрации кружков");
        nm.createNotificationChannel(new NotificationChannel(CH_DIGEST,"Утренний дайджест",NotificationManager.IMPORTANCE_DEFAULT));
        nm.createNotificationChannel(r);
        nm.createNotificationChannel(ch);
        nm.createNotificationChannel(an);
        addChangeChannel(nm, previous, CH_CANCEL, "Отмены занятий");
        addChangeChannel(nm, previous, CH_MOVE, "Переносы занятий");
    }

    private static void addChangeChannel(NotificationManager nm, NotificationChannel previous, String id, String title) {
        if (nm.getNotificationChannel(id) != null) return;
        int importance = previous == null ? NotificationManager.IMPORTANCE_HIGH : previous.getImportance();
        NotificationChannel channel = new NotificationChannel(id, title, importance);
        if (previous != null) {
            channel.setSound(previous.getSound(), previous.getAudioAttributes());
            channel.setVibrationPattern(previous.getVibrationPattern());
            channel.enableVibration(previous.shouldVibrate());
            channel.setShowBadge(previous.canShowBadge());
        }
        nm.createNotificationChannel(channel);
    }

    static String changeChannel(String kind) {
        if ("cancelled".equals(kind)) return CH_CANCEL;
        if ("moved".equals(kind)) return CH_MOVE;
        return CH_CHANGES;
    }

    static boolean isChangeChannel(String channel) {
        return CH_CANCEL.equals(channel) || CH_MOVE.equals(channel) || CH_CHANGES.equals(channel);
    }

    static boolean allowed(Context c) {
        if (Build.VERSION.SDK_INT >= 33 && ContextCompat.checkSelfPermission(c, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return false;
        return NotificationManagerCompat.from(c).areNotificationsEnabled();
    }

    static PendingIntent open(Context c, String path, int req) {
        Intent i = new Intent(Intent.ACTION_VIEW, Uri.parse("itckruzhki://open" + path), c, MainActivity.class);
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        return PendingIntent.getActivity(c, req, i, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }

    @SuppressWarnings("MissingPermission")
    static void post(Context c, String channel, int id, String title, String text, String path) {
        channels(c);
        if (!allowed(c)) return;
        if(Store.quietEnd(c,System.currentTimeMillis())>0){PersonalNotifications.defer(c,channel,id,title,text,path);return;}
        String group="ru.kipfin.clubs."+channel;
        NotificationCompat.Builder b = new NotificationCompat.Builder(c, channel)
            .setSmallIcon(R.drawable.ic_stat_itc)
            .setColor(0xFFB83B29)
            .setContentTitle(title)
            .setContentText(text)
            .setStyle(new NotificationCompat.BigTextStyle().bigText(text))
            .setGroup(group)
            .setGroupAlertBehavior(NotificationCompat.GROUP_ALERT_CHILDREN)
            .setAutoCancel(true)
            .setCategory(CH_REMIND.equals(channel) ? NotificationCompat.CATEGORY_REMINDER : NotificationCompat.CATEGORY_EVENT)
            .setPriority(isChangeChannel(channel) ? NotificationCompat.PRIORITY_HIGH : NotificationCompat.PRIORITY_DEFAULT)
            .setContentIntent(open(c, path, id));
        NotificationManagerCompat.from(c).notify(id, b.build());
        if(Build.VERSION.SDK_INT>=24){
            int count=0;for(android.service.notification.StatusBarNotification n:c.getSystemService(NotificationManager.class).getActiveNotifications())if(group.equals(n.getNotification().getGroup())&&(n.getNotification().flags&android.app.Notification.FLAG_GROUP_SUMMARY)==0)count++;
            if(count>1)NotificationManagerCompat.from(c).notify(("summary:"+group).hashCode(),new NotificationCompat.Builder(c,channel).setSmallIcon(R.drawable.ic_stat_itc).setContentTitle("KipClub · "+count).setContentText("Уведомления сгруппированы").setGroup(group).setGroupSummary(true).setGroupAlertBehavior(NotificationCompat.GROUP_ALERT_CHILDREN).setAutoCancel(true).setContentIntent(open(c,"/",group.hashCode())).build());
        }
    }
}
