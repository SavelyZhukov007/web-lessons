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

    private java.io.File weekDirectory() { return new java.io.File(getContext().getNoBackupFilesDir(), ScheduleCache.DIRECTORY); }

    @PluginMethod
    public void readWeek(PluginCall call) {
        try {
            org.json.JSONObject row = ScheduleCache.read(weekDirectory(), call.getString("origin", ""), call.getString("week", ""), System.currentTimeMillis());
            call.resolve(row == null ? new JSObject() : new JSObject(row.toString()));
        } catch (Exception ignored) { call.resolve(new JSObject()); }
    }
    @PluginMethod
    public void writeWeek(PluginCall call) {
        try {
            ScheduleCache.write(weekDirectory(), call.getString("origin", ""), call.getString("week", ""), call.getArray("events"),
                call.getLong("savedAt", System.currentTimeMillis()), System.currentTimeMillis());
            call.resolve();
        } catch (Exception error) { call.reject("Не удалось сохранить публичное расписание", error); }
    }
    @PluginMethod
    public void clearWeeks(PluginCall call) {
        try { ScheduleCache.clear(weekDirectory(), call.getString("origin", "")); call.resolve(); }
        catch (Exception error) { call.reject("Не удалось очистить кэш расписания", error); }
    }

    /** config: follows[], server, demo, reminderMinutes, notifyChanges, notifyAnnouncements. */
    @PluginMethod
    public void configure(PluginCall call) {
        for(String name:new String[]{"quietStart","quietEnd","digestTime"}) {
            if(call.hasOption(name))try {NotificationTime.minute(call.getString(name));}catch(IllegalArgumentException error){call.reject("Ожидается время HH:mm");return;}
        }
        if(Boolean.TRUE.equals(call.getBoolean("quietEnabled",false)) && call.getString("quietStart","22:00").equals(call.getString("quietEnd","08:00"))){call.reject("Начало и конец тихих часов должны отличаться");return;}
        android.content.SharedPreferences.Editor e = Store.prefs(getContext()).edit();
        JSONArray follows = call.getArray("follows", null);
        if (follows != null) e.putString("follows", follows.toString());
        if (call.hasOption("server")) e.putString("server", call.getString("server", ""));
        if (call.hasOption("demo")) e.putBoolean("demo", Boolean.TRUE.equals(call.getBoolean("demo", false)));
        if (call.hasOption("reminderMinutes")) e.putInt("reminder_minutes", Math.max(0,Math.min(120,call.getInt("reminderMinutes",15))));
        if (call.hasOption("notifyChanges")) e.putBoolean("notify_changes", Boolean.TRUE.equals(call.getBoolean("notifyChanges", true)));
        if (call.hasOption("notifyCancellations")) e.putBoolean("notify_cancellations", Boolean.TRUE.equals(call.getBoolean("notifyCancellations", true)));
        if (call.hasOption("notifyMoves")) e.putBoolean("notify_moves", Boolean.TRUE.equals(call.getBoolean("notifyMoves", true)));
        if (call.hasOption("notifyAnnouncements")) e.putBoolean("notify_announcements", Boolean.TRUE.equals(call.getBoolean("notifyAnnouncements", true)));
        if(call.hasOption("quietEnabled"))e.putBoolean("quiet_enabled",Boolean.TRUE.equals(call.getBoolean("quietEnabled",false)));
        if(call.hasOption("digestEnabled"))e.putBoolean("digest_enabled",Boolean.TRUE.equals(call.getBoolean("digestEnabled",false)));
        if(call.hasOption("quietStart"))e.putString("quiet_start",call.getString("quietStart"));
        if(call.hasOption("quietEnd"))e.putString("quiet_end",call.getString("quietEnd"));
        if(call.hasOption("digestTime"))e.putString("digest_time",call.getString("digestTime"));
        for(String key:new String[]{"favoriteRooms","favoriteLeaders"}) {
            JSONArray values=call.getArray(key,null);if(values!=null)e.putString(key.equals("favoriteRooms")?"widget_rooms":"widget_leaders",new JSONArray(Store.ids(values)).toString());
        }
        e.apply();
        Reminders.reschedule(getContext());
        Widgets.updateAll(getContext());
        SyncWorker.schedule(getContext());
        Push.refresh(getContext()); // FCM-токен + регистрация на сервере (только в сборке с FCM)
        Push.registerAsync(getContext());
        call.resolve(state());
    }

    @PluginMethod
    public void configureWidgets(PluginCall call) {
        android.content.SharedPreferences.Editor edit=Store.prefs(getContext()).edit();
        for(String key:new String[]{"favoriteRooms","favoriteLeaders"}) {
            JSONArray values=call.getArray(key,null);if(values!=null)edit.putString(key.equals("favoriteRooms")?"widget_rooms":"widget_leaders",new JSONArray(Store.ids(values)).toString());
        }
        edit.apply();Widgets.updateAll(getContext());call.resolve();
    }

    /** Opens the system editor; insertion requires the user's confirmation in Calendar. */
    @PluginMethod
    public void addToCalendar(PluginCall call) {
        long start=call.getData().optLong("start",0),end=call.getData().optLong("end",0);
        String title=call.getString("title","");
        if(start<=0 || end<=start || title.trim().isEmpty() || title.length()>255){call.reject("Некорректное занятие");return;}
        android.content.Intent intent=new android.content.Intent(android.content.Intent.ACTION_INSERT)
            .setData(android.provider.CalendarContract.Events.CONTENT_URI)
            .putExtra(android.provider.CalendarContract.EXTRA_EVENT_BEGIN_TIME,start)
            .putExtra(android.provider.CalendarContract.EXTRA_EVENT_END_TIME,end)
            .putExtra(android.provider.CalendarContract.Events.TITLE,title)
            .putExtra(android.provider.CalendarContract.Events.EVENT_TIMEZONE,"Europe/Moscow")
            .putExtra(android.provider.CalendarContract.Events.EVENT_LOCATION,call.getString("location",""))
            .putExtra(android.provider.CalendarContract.Events.DESCRIPTION,call.getString("description",""));
        getActivity().runOnUiThread(()->{try{getActivity().startActivity(intent);call.resolve();}catch(android.content.ActivityNotFoundException error){call.reject("Приложение календаря не найдено");}});
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
        r.put("notifyCancellations", Store.notifyCancellations(getContext()));
        r.put("notifyMoves", Store.notifyMoves(getContext()));
        r.put("changeChannels", Build.VERSION.SDK_INT >= 26);
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

    /** Системные настройки приложения или звук и вибрация отдельной категории. */
    @PluginMethod
    public void openNotificationSettings(PluginCall call) {
        String kind = call.getString("kind", "");
        String channel = Notifier.changeChannel(kind);
        Intent i = new Intent(android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:" + getContext().getPackageName()));
        if (Build.VERSION.SDK_INT >= 26) {
            boolean specific = Notifier.CH_CANCEL.equals(channel) || Notifier.CH_MOVE.equals(channel);
            i = new Intent(specific ? android.provider.Settings.ACTION_CHANNEL_NOTIFICATION_SETTINGS : android.provider.Settings.ACTION_APP_NOTIFICATION_SETTINGS)
                .putExtra(android.provider.Settings.EXTRA_APP_PACKAGE, getContext().getPackageName());
            if (specific) i.putExtra(android.provider.Settings.EXTRA_CHANNEL_ID, channel);
        }
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        try {
            getContext().startActivity(i);
            call.resolve();
        } catch (android.content.ActivityNotFoundException e) {
            call.reject("Не удалось открыть системные настройки уведомлений", e);
        }
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
