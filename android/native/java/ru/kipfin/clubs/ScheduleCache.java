package ru.kipfin.clubs;

import org.json.JSONArray;
import org.json.JSONObject;
import java.io.*;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.text.SimpleDateFormat;
import java.util.*;

/** Small public-week store outside WebView eviction; no sessions, auth or preferences. */
final class ScheduleCache {
    static final String DIRECTORY = "schedule-v1";
    static final long MAX_AGE = 48L * 3600 * 1000;
    static final int LIMIT = 12, MAX_BYTES = 4 * 1024 * 1024;
    private ScheduleCache() { }
    static String prefix(String origin) throws Exception {
        URI uri = new URI(origin);
        if (!("http".equals(uri.getScheme()) || "https".equals(uri.getScheme())) || uri.getHost() == null
                || uri.getUserInfo() != null || uri.getQuery() != null || uri.getFragment() != null
                || !(uri.getPath().isEmpty() || "/".equals(uri.getPath()))) throw new IllegalArgumentException("Invalid origin");
        byte[] hash = MessageDigest.getInstance("SHA-256").digest(origin.getBytes(StandardCharsets.UTF_8));
        StringBuilder result = new StringBuilder(); for (byte b : hash) result.append(String.format(Locale.US, "%02x", b & 255));
        return result + "-";
    }
    static String key(String origin, String week) throws Exception {
        if (week == null || !week.matches("[0-9]{4}-[0-9]{2}-[0-9]{2}")) throw new IllegalArgumentException("Invalid week");
        SimpleDateFormat format = new SimpleDateFormat("yyyy-MM-dd", Locale.US); format.setLenient(false); format.parse(week);
        return prefix(origin) + week + ".json";
    }
    static boolean fresh(long saved, long now) { return saved > 0 && saved <= now + 60_000 && now - saved <= MAX_AGE; }
    static synchronized JSONObject read(File directory, String origin, String week, long now) throws Exception {
        File file = new File(directory, key(origin, week));
        File backup = new File(directory, file.getName() + ".bak");
        if (!file.isFile() && backup.isFile()) backup.renameTo(file);
        if (!file.isFile() || file.length() > MAX_BYTES) return null;
        try (InputStream in = new FileInputStream(file); ByteArrayOutputStream bytes = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[8192]; int count;
            while ((count = in.read(buffer)) != -1) { bytes.write(buffer, 0, count); if (bytes.size() > MAX_BYTES) return null; }
            JSONObject row = new JSONObject(bytes.toString("UTF-8"));
            if (row.optInt("schema") != 1 || !origin.equals(row.optString("origin")) || !week.equals(row.optString("week"))
                    || !fresh(row.optLong("savedAt"), now) || !(row.opt("events") instanceof JSONArray)) return null;
            return row;
        } catch (Exception ignored) { return null; } // corrupt/evicted data never prevents network startup
    }
    static synchronized void write(File directory, String origin, String week, JSONArray events, long saved, long now) throws Exception {
        String name = key(origin, week);
        if (!fresh(saved, now) || events == null || events.length() > 5000) throw new IllegalArgumentException("Invalid record");
        JSONObject row = new JSONObject().put("schema", 1).put("origin", origin).put("week", week).put("savedAt", saved).put("events", events);
        byte[] bytes = row.toString().getBytes(StandardCharsets.UTF_8);
        if (bytes.length > MAX_BYTES) throw new IllegalArgumentException("Record too large");
        if (!directory.isDirectory() && !directory.mkdirs()) throw new IOException("Cannot create cache");
        File target = new File(directory, name), temp = new File(directory, name + ".new");
        try {
            try (FileOutputStream stream = new FileOutputStream(temp)) { stream.write(bytes); stream.getFD().sync(); }
            if (!temp.renameTo(target)) {
                // Android/POSIX replace is atomic; Windows JVM tests need a recoverable backup fallback.
                File backup = new File(directory, name + ".bak");
                if (backup.exists() && !backup.delete()) throw new IOException("Cannot remove old backup");
                if (target.exists() && !target.renameTo(backup)) throw new IOException("Cannot back up week");
                if (!temp.renameTo(target)) { backup.renameTo(target); throw new IOException("Cannot replace week"); }
                backup.delete();
            }
            target.setLastModified(saved);
        } finally { if (temp.exists()) temp.delete(); }
        File[] files = directory.listFiles((dir, file) -> file.endsWith(".json"));
        if (files != null) {
            Arrays.sort(files, (a, b) -> Long.compare(b.lastModified(), a.lastModified()));
            for (int i = 0; i < files.length; i++) if (i >= LIMIT || !fresh(files[i].lastModified(), now)) files[i].delete();
        }
    }
    static synchronized void clear(File directory, String origin) throws Exception {
        String prefix = prefix(origin);
        File[] files = directory.listFiles((dir, name) -> name.startsWith(prefix) && name.endsWith(".json"));
        if (files != null) for (File file : files) file.delete();
    }
}
