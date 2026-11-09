package ru.kipfin.clubs;
import org.junit.Test;
import static org.junit.Assert.*;
public class NotificationTimeTest {
    private long at(String time){return java.time.Instant.parse("2026-11-09T"+time+":00Z").toEpochMilli();}
    @Test public void clockValidation(){assertEquals(1439,NotificationTime.minute("23:59"));for(String s:new String[]{"24:00","9:00","xx:yy","22:60"})try{NotificationTime.minute(s);fail();}catch(IllegalArgumentException expected){}}
    @Test public void overnightStartInclusiveEndExclusive(){assertEquals(at("05:00")+NotificationTime.DAY,NotificationTime.quietEnd(at("19:00"),true,1320,480));assertEquals(at("05:00"),NotificationTime.quietEnd(at("04:59"),true,1320,480));assertEquals(0,NotificationTime.quietEnd(at("05:00"),true,1320,480));}
    @Test public void daytimeWindow(){assertEquals(at("12:00"),NotificationTime.quietEnd(at("11:00"),true,13*60,15*60));assertEquals(0,NotificationTime.quietEnd(at("12:00"),true,13*60,15*60));}
    @Test public void disabledAndEqual(){assertEquals(0,NotificationTime.quietEnd(at("23:00"),false,1320,480));assertEquals(0,NotificationTime.quietEnd(at("23:00"),true,1,1));}
    @Test public void nextAlwaysFuture(){assertEquals(at("05:00"),NotificationTime.next(at("04:00"),480));assertEquals(at("05:00")+NotificationTime.DAY,NotificationTime.next(at("05:00"),480));}
    @Test public void moscowDayNotDeviceZone(){assertEquals(at("21:00")-NotificationTime.DAY,NotificationTime.today(at("20:59"),0));assertEquals(at("21:00"),NotificationTime.today(at("21:00"),0));}
}
