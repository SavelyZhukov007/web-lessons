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
    static final String CH_REMIND = "itc_reminders";
    static final String CH_CHANGES = "itc_changes";
    static final String CH_ANN = "itc_announcements";

    private Notifier() {}

    static void channels(Context c) {
        if (Build.VERSION.SDK_INT < 26) return;
        NotificationManager nm = c.getSystemService(NotificationManager.class);
        NotificationChannel r = new NotificationChannel(CH_REMIND, "Напоминания о занятиях", NotificationManager.IMPORTANCE_DEFAULT);
        r.setDescription("Перед началом занятий отмеченных кружков");
        NotificationChannel ch = new NotificationChannel(CH_CHANGES, "Переносы и отмены", NotificationManager.IMPORTANCE_HIGH);
        ch.setDescription("Когда занятие отмечённого кружка отменили или перенесли");
        NotificationChannel an = new NotificationChannel(CH_ANN, "Объявления", NotificationManager.IMPORTANCE_DEFAULT);
        an.setDescription("Сообщения от администрации кружков");
        nm.createNotificationChannel(r);
        nm.createNotificationChannel(ch);
        nm.createNotificationChannel(an);
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
        NotificationCompat.Builder b = new NotificationCompat.Builder(c, channel)
            .setSmallIcon(R.drawable.ic_stat_itc)
            .setColor(0xFFB83B29)
            .setContentTitle(title)
            .setContentText(text)
            .setStyle(new NotificationCompat.BigTextStyle().bigText(text))
            .setAutoCancel(true)
            .setCategory(CH_REMIND.equals(channel) ? NotificationCompat.CATEGORY_REMINDER : NotificationCompat.CATEGORY_EVENT)
            .setPriority(CH_CHANGES.equals(channel) ? NotificationCompat.PRIORITY_HIGH : NotificationCompat.PRIORITY_DEFAULT)
            .setContentIntent(open(c, path, id));
        NotificationManagerCompat.from(c).notify(id, b.build());
    }
}
