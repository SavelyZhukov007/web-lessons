package ru.kipfin.clubs;

import android.content.Context;

import androidx.annotation.NonNull;
import androidx.work.Constraints;
import androidx.work.ExistingPeriodicWorkPolicy;
import androidx.work.NetworkType;
import androidx.work.PeriodicWorkRequest;
import androidx.work.WorkManager;
import androidx.work.Worker;
import androidx.work.WorkerParameters;

import org.json.JSONArray;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.concurrent.TimeUnit;

/** Фоновая проверка расписания раз в ~30 минут (WorkManager, без GMS): обновляет виджеты, напоминания, сообщает об отменах/переносах и объявлениях. */
public class SyncWorker extends Worker {
    static final String NAME = "itc-schedule-sync";

    public SyncWorker(@NonNull Context c, @NonNull WorkerParameters p) { super(c, p); }

    static void schedule(Context c) {
        WorkManager wm = WorkManager.getInstance(c);
        if (Store.demo(c) || Store.server(c).isEmpty()) { wm.cancelUniqueWork(NAME); return; }
        PeriodicWorkRequest req = new PeriodicWorkRequest.Builder(SyncWorker.class, 30, TimeUnit.MINUTES)
            .setConstraints(new Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .build();
        wm.enqueueUniquePeriodicWork(NAME, ExistingPeriodicWorkPolicy.KEEP, req);
    }

    @NonNull
    @Override
    public Result doWork() {
        Context c = getApplicationContext();
        String server = Store.server(c).replaceAll("/+$", "");
        if (Store.demo(c) || server.isEmpty()) return Result.success();
        try {
            long now = System.currentTimeMillis();
            JSONArray all = new JSONArray();
            for (int w = 0; w < 2; w++) {
                JSONArray week = new JSONArray(get(server + "/api/schedule?week=" + Store.mondayOf(now, w)));
                for (int i = 0; i < week.length(); i++) all.put(week.get(i));
            }
            Sync.apply(c, all.toString());
            Announcements.check(c);
            try { Push.register(c); } catch (Exception ignored) { } // FCM: продлить регистрацию (не чаще раза в сутки)
            return Result.success();
        } catch (Exception e) {
            return getRunAttemptCount() < 3 ? Result.retry() : Result.success();
        }
    }

    private static String get(String url) throws Exception {
        HttpURLConnection con = (HttpURLConnection) new URL(url).openConnection();
        con.setConnectTimeout(10_000);
        con.setReadTimeout(15_000);
        con.setRequestProperty("Accept", "application/json");
        try {
            if (con.getResponseCode() != 200) throw new IllegalStateException("HTTP " + con.getResponseCode());
            try (InputStream in = con.getInputStream(); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
                byte[] buf = new byte[8192];
                for (int n; (n = in.read(buf)) > 0; ) out.write(buf, 0, n);
                return out.toString("UTF-8");
            }
        } finally { con.disconnect(); }
    }
}
