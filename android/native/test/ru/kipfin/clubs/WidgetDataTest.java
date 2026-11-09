package ru.kipfin.clubs;
import org.junit.Test;
import static org.junit.Assert.*;
import java.util.*;
public class WidgetDataTest {
 static Store.Event event(long id,long start,long end) {Store.Event e=new Store.Event();e.clubId=id;e.startMs=start;e.endMs=end;e.status="scheduled";e.club="Кружок";e.date="2026-11-09";e.start="10:00";e.end="11:00";e.room="101";e.leader="Иван";return e;}
 @Test public void favoritesUnionDoesNotWidenUnmatched(){Store.Event a=event(1,0,60000),b=event(2,0,60000),c=event(3,0,60000);b.roomIds.add(11L);c.leaderIds.add(22L);List<Store.Event> all=Arrays.asList(a,b,c);assertEquals(3,WidgetData.filter(all,Set.of(1L),Set.of(11L),Set.of(22L)).size());assertEquals(List.of(b),WidgetData.filter(all,Set.of(),Set.of(11L),Set.of()));assertSame(all,WidgetData.filter(all,Set.of(),Set.of(),Set.of()));}
 @Test public void progressClampsAndCancellationHasNone(){Store.Event e=event(1,1000,61000);assertEquals(0,WidgetData.progress(e,0));assertEquals(50,WidgetData.progress(e,31000));assertEquals(100,WidgetData.progress(e,100000));e.status="cancelled";assertEquals(0,WidgetData.progress(e,31000));}
 @Test public void phasesAndAccessibleName(){Store.Event e=event(1,900000,1800000);assertEquals("Через 15 мин",WidgetData.phase(e,0));assertEquals("Идёт сейчас",WidgetData.phase(e,900000));assertTrue(WidgetData.accessible(e,0).contains("101. Иван. Через 15 мин"));e.status="cancelled";assertEquals("Отменено",WidgetData.phase(e,0));e.status="moved";assertEquals("Перенесено",WidgetData.phase(e,-3600000));}
 @Test public void tickOnlyNearLiveAndSoon(){Store.Event e=event(1,7200000,9000000);assertEquals(3600000,WidgetData.nextTick(List.of(e),0));assertEquals(6360000,WidgetData.nextTick(List.of(e),6300000));e.status="cancelled";assertEquals(9900000,WidgetData.nextTick(List.of(e),6300000));}
 @Test public void duplicateCrossWeekOccurrencesAreDeduplicatedAndMultiRoomsPreserved(){String e="{\"session_id\":1,\"club_id\":2,\"date\":\"2026-11-09\",\"original_date\":\"2026-11-02\",\"start_time\":\"10:00\",\"end_time\":\"11:00\",\"room_ids\":[7,8],\"room_names\":[\"101\",\"102\"],\"leader_ids\":[3,4],\"leader_names\":[\"Иван\",\"Анна\"]}";List<Store.Event> rows=Store.parse("["+e+","+e+"]");assertEquals(1,rows.size());assertEquals("101, 102",rows.get(0).room);assertEquals(Set.of(3L,4L),rows.get(0).leaderIds);assertTrue(Store.parse("garbage").isEmpty());}
}
