package ru.kipfin.clubs;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.Bundle;
import android.view.View;
import android.widget.RemoteViews;

import java.util.List;

/** Отрисовка виджетов «Следующее занятие» и «Сегодня». Цвета — Material You (Android 12+) или фирменные; светлая/тёмная тема — ресурсы -night. */
final class Widgets {
    private Widgets() {}

    static void updateAll(Context c) {
        AppWidgetManager m = AppWidgetManager.getInstance(c);
        for (int id : m.getAppWidgetIds(new ComponentName(c, NextClassWidget.class))) renderNext(c, m, id);
        int[] today = m.getAppWidgetIds(new ComponentName(c, TodayWidget.class));
        for (int id : today) renderToday(c, m, id);
        if (today.length > 0) m.notifyAppWidgetViewDataChanged(today, R.id.widget_list);
        scheduleTick(c);
    }

    static boolean requestPin(Context c, Class<?> cls) {
        if (Build.VERSION.SDK_INT < 26) return false;
        AppWidgetManager m = c.getSystemService(AppWidgetManager.class);
        return m != null && m.isRequestPinAppWidgetSupported() && m.requestPinAppWidget(new ComponentName(c, cls), null, null);
    }

    /** Следующее не отменённое занятие, которое ещё не закончилось. */
    static Store.Event next(List<Store.Event> events, long now) {
        for (Store.Event e : events) if (!e.cancelled() && e.endMs > now) return e;
        return null;
    }

    static void renderNext(Context c, AppWidgetManager m, int id) {
        Bundle o = m.getAppWidgetOptions(id);
        int h = o == null ? 110 : o.getInt(AppWidgetManager.OPTION_APPWIDGET_MIN_HEIGHT, 110);
        int w = o == null ? 250 : o.getInt(AppWidgetManager.OPTION_APPWIDGET_MIN_WIDTH, 250);
        boolean compact = h < 100;
        RemoteViews v = new RemoteViews(c.getPackageName(), compact ? R.layout.widget_next_compact : R.layout.widget_next);
        long now = Format.now();
        List<Store.Event> mine = Store.mine(c);
        Store.Event e = next(mine, now);
        boolean all = Store.follows(c).isEmpty();
        if (e == null) {
            v.setTextViewText(R.id.widget_label, all ? "Расписание" : "Мои кружки");
            v.setTextViewText(R.id.widget_title, mine.isEmpty() && Store.prefs(c).getLong("updated", 0) == 0 ? "Откройте приложение, чтобы загрузить расписание" : "Ближайших занятий нет");
            v.setViewVisibility(R.id.widget_when, View.GONE);
            v.setViewVisibility(R.id.widget_status, View.GONE);
            if (!compact) v.setViewVisibility(R.id.widget_room, View.GONE);
            v.setOnClickPendingIntent(R.id.widget_root, Notifier.open(c, "/", id));
        } else {
            boolean live = e.startMs <= now;
            v.setTextViewText(R.id.widget_label, live ? "Идёт сейчас" : (all ? "Следующее занятие" : "Следующее в моих кружках"));
            v.setTextViewText(R.id.widget_title, e.club);
            v.setViewVisibility(R.id.widget_when, View.VISIBLE);
            v.setTextViewText(R.id.widget_when, (live ? "до " + e.end : Format.dayLabel(e.date) + ", " + e.start + "–" + e.end));
            if (!compact) {
                v.setViewVisibility(R.id.widget_room, e.room.isEmpty() ? View.GONE : View.VISIBLE);
                v.setTextViewText(R.id.widget_room, e.room + (w >= 250 && !e.leader.isEmpty() ? " · " + e.leader : ""));
            }
            v.setViewVisibility(R.id.widget_status, e.moved() ? View.VISIBLE : View.GONE);
            v.setTextViewText(R.id.widget_status, "Перенесено");
            v.setInt(R.id.widget_bar, "setBackgroundColor", e.color);
            v.setOnClickPendingIntent(R.id.widget_root, Notifier.open(c, "/club?id=" + e.clubId, id));
        }
        m.updateAppWidget(id, v);
    }

    static void renderToday(Context c, AppWidgetManager m, int id) {
        RemoteViews v = new RemoteViews(c.getPackageName(), R.layout.widget_today);
        boolean all = Store.follows(c).isEmpty();
        v.setTextViewText(R.id.widget_label, all ? "Сегодня" : "Сегодня · мои кружки");
        v.setTextViewText(R.id.widget_date, Format.longToday());
        Intent svc = new Intent(c, TodayWidgetService.class).putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, id);
        svc.setData(android.net.Uri.parse(svc.toUri(Intent.URI_INTENT_SCHEME)));
        v.setRemoteAdapter(R.id.widget_list, svc);
        v.setEmptyView(R.id.widget_list, R.id.widget_empty);
        v.setTextViewText(R.id.widget_empty, Store.prefs(c).getLong("updated", 0) == 0 ? "Откройте приложение, чтобы загрузить расписание" : "Сегодня занятий нет");
        Intent tpl = new Intent(Intent.ACTION_VIEW, android.net.Uri.parse("itckruzhki://open/"), c, MainActivity.class);
        v.setPendingIntentTemplate(R.id.widget_list, PendingIntent.getActivity(c, 7000 + id, tpl, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_MUTABLE));
        v.setOnClickPendingIntent(R.id.widget_header, Notifier.open(c, "/", 8000 + id));
        m.updateAppWidget(id, v);
    }

    /** Перерисовка к ближайшей границе (начало/конец занятия, полночь), неточный будильник — батарею не тратим. */
    static void scheduleTick(Context c) {
        long now = System.currentTimeMillis();
        long at = now + 3_600_000L;
        for (Store.Event e : Store.mine(c)) {
            if (e.startMs > now) { at = Math.min(at, e.startMs); break; }
            if (e.endMs > now) at = Math.min(at, e.endMs);
        }
        long midnight = Store.epoch(Store.mskDate(now + 86_400_000L), "00:00");
        at = Math.min(at, midnight) + 5_000;
        Intent i = new Intent(c, NextClassWidget.class).setAction(NextClassWidget.ACTION_TICK);
        PendingIntent pi = PendingIntent.getBroadcast(c, 9001, i, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        ((AlarmManager) c.getSystemService(Context.ALARM_SERVICE)).set(AlarmManager.RTC, at, pi);
    }
}
