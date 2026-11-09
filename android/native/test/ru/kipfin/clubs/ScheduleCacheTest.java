package ru.kipfin.clubs;
import org.junit.Test;
import org.junit.Rule;
import org.junit.rules.TemporaryFolder;
import org.json.JSONArray;
import java.io.File;
import java.io.FileOutputStream;
import static org.junit.Assert.*;
public class ScheduleCacheTest {
    @Rule public TemporaryFolder folder = new TemporaryFolder();
    final String host="https://club.kipfin.ru", week="2026-11-09";
    @Test public void roundTripSurvivesNewReader() throws Exception {
        long now=System.currentTimeMillis(); File dir=folder.newFolder();
        ScheduleCache.write(dir,host,week,new JSONArray("[{\"event_id\":\"1:2026-11-09\"}]"),now,now);
        assertEquals("1:2026-11-09",ScheduleCache.read(dir,host,week,now).getJSONArray("events").getJSONObject(0).getString("event_id"));
    }
    @Test public void expiredAndFutureAreNotCurrent() { long now=System.currentTimeMillis(); assertFalse(ScheduleCache.fresh(now-49L*3600*1000,now)); assertFalse(ScheduleCache.fresh(now+120_000,now)); assertTrue(ScheduleCache.fresh(now,now)); }
    @Test public void originsAreIsolatedAndClearIsScoped() throws Exception {
        File dir=folder.newFolder(); long now=System.currentTimeMillis(); String test="http://lekora.ru:7443";
        ScheduleCache.write(dir,host,week,new JSONArray(),now,now); ScheduleCache.write(dir,test,week,new JSONArray(),now,now);
        ScheduleCache.clear(dir,host); assertNull(ScheduleCache.read(dir,host,week,now)); assertNotNull(ScheduleCache.read(dir,test,week,now));
    }
    @Test public void corruptionDoesNotBreakStartup() throws Exception {
        File dir=folder.newFolder(); File f=new File(dir,ScheduleCache.key(host,week)); try(FileOutputStream out=new FileOutputStream(f)){out.write("broken".getBytes());}
        assertNull(ScheduleCache.read(dir,host,week,System.currentTimeMillis()));
    }
    @Test public void rejectsTraversalAndPrivateUrls() throws Exception {
        for(String bad:new String[]{"../../x","file:///tmp","https://a.test/api/admin","https://user@a.test"}) {
            try {ScheduleCache.key(bad,week); fail(bad);} catch(Exception expected) { }
        }
        try {ScheduleCache.key(host,"../../x"); fail();} catch(Exception expected) { }
        try {ScheduleCache.key(host,"2026-02-31"); fail();} catch(Exception expected) { }
    }
    @Test public void boundedAndAtomicReplacement() throws Exception {
        File dir=folder.newFolder(); long now=System.currentTimeMillis();
        for(int i=1;i<=15;i++) ScheduleCache.write(dir,host,"2026-11-"+String.format("%02d",i),new JSONArray(),now+i,now+100);
        assertEquals(12,dir.listFiles((d,n)->n.endsWith(".json")).length);
        ScheduleCache.write(dir,host,week,new JSONArray("[1]"),now+101,now+101);
        ScheduleCache.write(dir,host,week,new JSONArray("[2]"),now+102,now+102);
        assertEquals(2,ScheduleCache.read(dir,host,week,now+103).getJSONArray("events").getInt(0));
        assertEquals(0,dir.listFiles((d,n)->n.endsWith(".new")).length);
    }
}
