package ru.kipfin.clubs;

import android.Manifest;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;

import com.getcapacitor.JSObject;
import com.getcapacitor.PermissionState;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;

import org.json.JSONArray;

/** Мост WebView ↔ нативная часть: «мои кружки», расписание для виджетов/напоминаний, настройки уведомлений. */
@CapacitorPlugin(name = "ItcNative", permissions = {
    @Permission(alias = "notifications", strings = {Manifest.permission.POST_NOTIFICATIONS})
})
public class ItcNativePlugin extends Plugin {

    @Override
    public void load() {
        Notifier.channels(getContext());
        try { // ярлык «Мой QR» из версий с посещаемостью
            androidx.core.content.pm.ShortcutManagerCompat.removeDynamicShortcuts(getContext(), java.util.Collections.singletonList("teacher_qr"));
        } catch (Exception ignored) { }
    }

    /** config: follows[], server, demo, reminderMinutes, notifyChanges, notifyAnnouncements. */
    @PluginMethod
    public void configure(PluginCall call) {
        android.content.SharedPreferences.Editor e = Store.prefs(getContext()).edit();
        JSONArray follows = call.getArray("follows", null);
        if (follows != null) e.putString("follows", follows.toString());
        if (call.hasOption("server")) e.putString("server", call.getString("server", ""));
        if (call.hasOption("demo")) e.putBoolean("demo", Boolean.TRUE.equals(call.getBoolean("demo", false)));
        if (call.hasOption("reminderMinutes")) e.putInt("reminder_minutes", call.getInt("reminderMinutes", 30));
        if (call.hasOption("notifyChanges")) e.putBoolean("notify_changes", Boolean.TRUE.equals(call.getBoolean("notifyChanges", true)));
        if (call.hasOption("notifyAnnouncements")) e.putBoolean("notify_announcements", Boolean.TRUE.equals(call.getBoolean("notifyAnnouncements", true)));
        e.apply();
        Reminders.reschedule(getContext());
        Widgets.updateAll(getContext());
        SyncWorker.schedule(getContext());
        Push.refresh(getContext()); // FCM-токен + регистрация на сервере (только в сборке с FCM)
        Push.registerAsync(getContext());
        call.resolve(state());
    }

    /** events: массив занятий /api/schedule (текущая и следующая недели). */
    @PluginMethod
    public void sync(PluginCall call) {
        JSONArray events = call.getArray("events", new com.getcapacitor.JSArray());
        int n = Sync.apply(getContext(), events.toString());
        JSObject r = state();
        r.put("notified", n);
        call.resolve(r);
    }

    /** Проверить объявления сейчас (при открытии приложения). Сеть — в фоновом потоке. */
    @PluginMethod
    public void checkAnnouncements(PluginCall call) {
        android.content.Context c = getContext().getApplicationContext();
        new Thread(() -> {
            JSObject r = new JSObject();
            r.put("shown", Announcements.check(c));
            call.resolve(r);
        }, "itc-announcements").start();
    }

    @PluginMethod
    public void getState(PluginCall call) { call.resolve(state()); }

    private JSObject state() {
        JSObject r = new JSObject();
        r.put("notificationsAllowed", Notifier.allowed(getContext()));
        r.put("updated", Store.prefs(getContext()).getLong("updated", 0));
        r.put("reminderMinutes", Store.reminderMinutes(getContext()));
        r.put("notifyChanges", Store.notifyChanges(getContext()));
        r.put("notifyAnnouncements", Store.notifyAnnouncements(getContext()));
        r.put("exactAlarms", Build.VERSION.SDK_INT < 31 || ((android.app.AlarmManager) getContext().getSystemService(android.content.Context.ALARM_SERVICE)).canScheduleExactAlarms());
        return r;
    }

    @PluginMethod
    public void requestNotifications(PluginCall call) {
        if (Build.VERSION.SDK_INT < 33 || getPermissionState("notifications") == PermissionState.GRANTED) { call.resolve(state()); return; }
        requestPermissionForAlias("notifications", call, "onNotifPermission");
    }

    @PermissionCallback
    private void onNotifPermission(PluginCall call) { call.resolve(state()); }

    /** Системные настройки уведомлений приложения (если пользователь запретил). */
    @PluginMethod
    public void openNotificationSettings(PluginCall call) {
        Intent i;
        if (Build.VERSION.SDK_INT >= 26) i = new Intent(android.provider.Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(android.provider.Settings.EXTRA_APP_PACKAGE, getContext().getPackageName());
        else i = new Intent(android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:" + getContext().getPackageName()));
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        getContext().startActivity(i);
        call.resolve();
    }

    /** Предложить закрепить виджет на рабочем столе (Android 8+, если лаунчер поддерживает). */
    @PluginMethod
    public void pinWidget(PluginCall call) {
        boolean ok = Widgets.requestPin(getContext(), "today".equals(call.getString("kind")) ? TodayWidget.class : NextClassWidget.class);
        JSObject r = new JSObject();
        r.put("requested", ok);
        call.resolve(r);
    }
}
