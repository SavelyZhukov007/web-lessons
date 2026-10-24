package ru.kipfin.clubs;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import org.junit.Before;
import org.junit.Test;

import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class ChangeDetectorTest {
    private static final long NOW = Store.epoch("2026-10-24", "10:00");
    private final Set<Long> follows = new HashSet<>(Collections.singletonList(1L));

    @Before
    public void fixClock() { Format.now = NOW; }

    private static String ev(long session, long club, String date, String start, String status, String original) {
        return "{\"event_id\":\"" + session + "-" + date + "\",\"session_id\":" + session + ",\"club_id\":" + club
            + ",\"club_name\":\"Робототехника\",\"category_color\":\"#2266aa\",\"room_name\":\"Ауд. 214\",\"leader_name\":\"Иванова\""
            + ",\"date\":\"" + date + "\",\"start_time\":\"" + start + "\",\"end_time\":\"17:00\",\"status\":\"" + status
            + "\",\"original_date\":\"" + original + "\",\"comment\":\"\"}";
    }

    private static List<Store.Event> list(String... items) { return Store.parse("[" + String.join(",", items) + "]"); }

    @Test public void firstRunOnlyRemembers() {
        ChangeDetector.Result r = ChangeDetector.diff("{}", list(ev(5, 1, "2026-10-25", "15:30", "cancelled", "2026-10-25")), follows, NOW);
        assertTrue(r.changes.isEmpty());
        assertTrue(r.snapshot.contains("5:2026-10-25"));
    }

    @Test public void detectsCancelMoveAndRestore() {
        String base = ChangeDetector.diff("{}", list(ev(5, 1, "2026-10-25", "15:30", "scheduled", "2026-10-25"),
            ev(6, 1, "2026-10-26", "15:30", "scheduled", "2026-10-26")), follows, NOW).snapshot;
        ChangeDetector.Result r = ChangeDetector.diff(base, list(ev(5, 1, "2026-10-25", "15:30", "cancelled", "2026-10-25"),
            ev(6, 1, "2026-10-27", "16:00", "moved", "2026-10-26")), follows, NOW);
        assertEquals(2, r.changes.size());
        assertEquals("cancelled", r.changes.get(0).kind);
        assertEquals("moved", r.changes.get(1).kind);
        assertEquals("Отменено: Робототехника", ChangeDetector.text(r.changes.get(0))[0]);
        assertTrue(ChangeDetector.text(r.changes.get(1))[1].startsWith("Новое время: вт, 27 октября, 16:00–17:00"));
        ChangeDetector.Result back = ChangeDetector.diff(r.snapshot, list(ev(5, 1, "2026-10-25", "15:30", "scheduled", "2026-10-25"),
            ev(6, 1, "2026-10-27", "16:00", "moved", "2026-10-26")), follows, NOW);
        assertEquals(1, back.changes.size());
        assertEquals("restored", back.changes.get(0).kind);
    }

    @Test public void ignoresUnfollowedAndPast() {
        String base = ChangeDetector.diff("{}", list(ev(5, 1, "2026-10-23", "15:30", "scheduled", "2026-10-23"),
            ev(7, 2, "2026-10-25", "15:30", "scheduled", "2026-10-25")), follows, NOW).snapshot;
        ChangeDetector.Result r = ChangeDetector.diff(base, list(ev(5, 1, "2026-10-23", "15:30", "cancelled", "2026-10-23"),
            ev(7, 2, "2026-10-25", "15:30", "cancelled", "2026-10-25")), follows, NOW);
        assertTrue(r.changes.isEmpty());
    }

    @Test public void newCancelledOccurrenceOfKnownClub() {
        String base = ChangeDetector.diff("{}", list(ev(5, 1, "2026-10-25", "15:30", "scheduled", "2026-10-25")), follows, NOW).snapshot;
        ChangeDetector.Result r = ChangeDetector.diff(base, list(ev(5, 1, "2026-10-25", "15:30", "scheduled", "2026-10-25"),
            ev(5, 1, "2026-11-01", "15:30", "cancelled", "2026-11-01")), follows, NOW);
        assertEquals(1, r.changes.size());
    }

    @Test public void dayLabelsAndWeeks() {
        assertEquals("Сегодня", Format.dayLabel("2026-10-24"));
        assertEquals("Завтра", Format.dayLabel("2026-10-25"));
        assertEquals("пн, 26 октября", Format.dayLabel("2026-10-26"));
        assertEquals("2026-10-19", Store.mondayOf(NOW, 0));
        assertEquals("2026-10-26", Store.mondayOf(NOW, 1));
    }
}
