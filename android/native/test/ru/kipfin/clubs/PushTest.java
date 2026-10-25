package ru.kipfin.clubs;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class PushTest {
    private static Map<String, String> data(String... kv) {
        Map<String, String> m = new HashMap<>();
        for (int i = 0; i < kv.length; i += 2) m.put(kv[i], kv[i + 1]);
        return m;
    }

    @Test public void announcementKeyMatchesPolling() {
        Push.Msg m = Push.parse(data("type", "announcement", "id", "7", "title", "", "body", "Текст", "url", "https://evil.example"));
        assertEquals("a7", m.key);
        assertEquals(Notifier.CH_ANN, m.channel);
        assertEquals("Объявление", m.title);
        assertEquals("/", m.url);
        assertEquals(Announcements.notificationId(7), m.key.hashCode());
        assertNull(Push.parse(data("type", "announcement", "id", "x")));
    }

    @Test public void changeKeysMatchChangeDetector() {
        Store.Event e = new Store.Event();
        e.key = "12:2026-11-02"; e.date = "2026-11-03"; e.start = "12:00";
        Push.Msg cancel = Push.parse(data("type", "cancel", "session_id", "12", "original_date", "2026-11-02", "title", "Отменено", "club_id", "5"));
        assertEquals(Push.changeKey(new ChangeDetector.Change(e, "cancelled")), cancel.key);
        assertEquals(5, cancel.clubId);
        assertTrue(cancel.sync);
        Push.Msg moved = Push.parse(data("type", "reschedule", "session_id", "12", "original_date", "2026-11-02",
            "new_date", "2026-11-03", "new_start", "12:00", "title", "Перенесено"));
        assertEquals(Push.changeKey(new ChangeDetector.Change(e, "moved")), moved.key);
        assertEquals("c12:2026-11-02moved|2026-11-03|12:00", moved.key);
        assertNull(Push.parse(data("type", "cancel", "title", "x")));
    }

    @Test public void otherTypes() {
        Push.Msg sc = Push.parse(data("type", "schedule-change"));
        assertTrue(sc.sync);
        assertNull(sc.key);
        Push.Msg up = Push.parse(data("type", "update-available", "version", "0.8.0"));
        assertEquals("u0.8.0", up.key);
        assertTrue(up.body.contains("0.8.0"));
        assertNull(Push.parse(data("type", "update-available")));
        assertNull(Push.parse(data("type", "nope")));
        assertNull(Push.parse(null));
    }

    @Test public void respectsSettings() {
        Set<Long> follows = new HashSet<>(Collections.singletonList(5L));
        Push.Msg ch = Push.parse(data("type", "cancel", "session_id", "1", "original_date", "d", "title", "t", "club_id", "5"));
        assertTrue(Push.wanted(ch, true, true, follows));
        assertFalse(Push.wanted(ch, false, true, follows));
        assertFalse(Push.wanted(ch, true, true, new HashSet<>()));
        Push.Msg an = Push.parse(data("type", "announcement", "id", "3"));
        assertFalse(Push.wanted(an, true, false, follows));
        assertFalse(Push.wanted(Push.parse(data("type", "schedule-change")), true, true, follows));
    }

    @Test public void dedupeIsBoundedAndIdempotent() {
        String raw = Push.mark("", "a1");
        assertTrue(Push.seen(raw, "a1"));
        assertFalse(Push.seen(raw, "a2"));
        assertEquals(raw, Push.mark(raw, "a1"));
        for (int i = 0; i < Push.MAX_KEYS + 10; i++) raw = Push.mark(raw, "k" + i);
        assertEquals(Push.MAX_KEYS, Push.keys(raw).size());
        assertFalse(Push.seen(raw, "a1"));
        assertTrue(Push.seen(raw, "k" + (Push.MAX_KEYS + 9)));
    }

    @Test public void registrationBody() {
        String b = Push.body("dev", "tok", "0.7", new HashSet<>(java.util.Arrays.asList(3L, 1L)), true, false);
        assertTrue(b.contains("\"club_ids\":[1,3]"));
        assertTrue(b.contains("\"changes\":false"));
        assertTrue(b.contains("\"platform\":\"android\""));
    }
}
