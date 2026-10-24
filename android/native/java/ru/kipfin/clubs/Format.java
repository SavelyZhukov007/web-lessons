package ru.kipfin.clubs;

import java.text.SimpleDateFormat;
import java.util.Locale;

/** Русские подписи дат для уведомлений и виджетов (часовой пояс — Москва). */
public final class Format {
    private static final String[] DAYS = {"", "вс", "пн", "вт", "ср", "чт", "пт", "сб"};
    private static final String[] MONTHS = {"января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"};

    private Format() {}

    static long now = -1; // для тестов

    static long now() { return now >= 0 ? now : System.currentTimeMillis(); }

    /** «Сегодня», «Завтра» или «пн, 27 октября». */
    public static String dayLabel(String date) {
        String today = Store.mskDate(now());
        String tomorrow = Store.mskDate(now() + 86_400_000L);
        if (date.equals(today)) return "Сегодня";
        if (date.equals(tomorrow)) return "Завтра";
        long ms = Store.epoch(date, "12:00");
        java.util.Calendar c = java.util.Calendar.getInstance(Store.MSK, Locale.US);
        c.setTimeInMillis(ms);
        return DAYS[c.get(java.util.Calendar.DAY_OF_WEEK)] + ", " + c.get(java.util.Calendar.DAY_OF_MONTH) + " " + MONTHS[c.get(java.util.Calendar.MONTH)];
    }

    public static String longToday() {
        java.util.Calendar c = java.util.Calendar.getInstance(Store.MSK, Locale.US);
        c.setTimeInMillis(now());
        String[] full = {"", "Воскресенье", "Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"};
        return full[c.get(java.util.Calendar.DAY_OF_WEEK)] + ", " + c.get(java.util.Calendar.DAY_OF_MONTH) + " " + MONTHS[c.get(java.util.Calendar.MONTH)];
    }

    static String hm(long ms) {
        SimpleDateFormat f = new SimpleDateFormat("HH:mm", Locale.US);
        f.setTimeZone(Store.MSK);
        return f.format(ms);
    }
}
