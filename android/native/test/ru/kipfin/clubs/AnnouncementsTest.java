package ru.kipfin.clubs;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;

public class AnnouncementsTest {
    private static final String FEED = "{\"items\":["
        + "{\"id\":7,\"title\":\"Занятия переносятся\",\"body\":\"В пятницу кружков нет\",\"url\":\"/clubs.html\"},"
        + "{\"id\":9,\"title\":\"  \",\"body\":\"Текст\",\"url\":\"https://evil.example/\"},"
        + "{\"id\":0,\"title\":\"битая\"}],\"last_id\":12}";

    @Test public void parsesItemsAndLastId() {
        Announcements.Feed f = Announcements.parse(FEED);
        assertEquals(12, f.lastId);
        assertEquals(2, f.items.size());
        assertEquals("Занятия переносятся", f.items.get(0).title);
        assertEquals("/clubs.html", f.items.get(0).url);
        assertEquals("Объявление", f.items.get(1).title);   // пустой заголовок
        assertEquals("/", f.items.get(1).url);              // внешние ссылки не открываем
    }

    @Test public void brokenJsonIsEmpty() {
        assertEquals(0, Announcements.parse("<html>").items.size());
        assertEquals(0, Announcements.parse(null).lastId);
    }

    @Test public void firstRunShowsNothingButRemembers() {
        Announcements.Feed f = Announcements.parse(FEED);
        assertTrue(Announcements.fresh(f, -1).isEmpty());
        assertEquals(12, Announcements.nextSeen(f, -1));
    }

    @Test public void onlyNewerThanSeen() {
        List<Announcements.Item> out = Announcements.fresh(Announcements.parse(FEED), 7);
        assertEquals(1, out.size());
        assertEquals(9, out.get(0).id);
        assertEquals(12, Announcements.nextSeen(Announcements.parse("{\"items\":[],\"last_id\":3}"), 12)); // не откатываемся назад
    }

    @Test public void stableNotificationIdAndQuery() {
        assertEquals(Announcements.notificationId(5), Announcements.notificationId(5));
        assertTrue(Announcements.notificationId(5) != Announcements.notificationId(6));
        assertEquals("/api/announcements?since=4&clubs=2%2C10&device=abc&off=0",
            Announcements.query(4, new HashSet<>(Arrays.asList(10L, 2L)), "abc", false));
        assertEquals("/api/announcements?since=0&clubs=&device=abc&off=1",
            Announcements.query(-1, Collections.<Long>emptySet(), "abc", true));
    }
}
