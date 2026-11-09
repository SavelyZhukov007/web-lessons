package ru.kipfin.clubs;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;

/** Pure widget view-model; does not alter notification follows or schedule background network work. */
final class WidgetData {
    private WidgetData() {}
    static List<Store.Event> filter(List<Store.Event> events, Set<Long> clubs, Set<Long> rooms, Set<Long> leaders) {
        if (clubs.isEmpty() && rooms.isEmpty() && leaders.isEmpty()) return events;
        List<Store.Event> result = new ArrayList<>();
        for (Store.Event e : events) if (clubs.contains(e.clubId) || overlaps(rooms,e.roomIds) || overlaps(leaders,e.leaderIds)) result.add(e);
        return result;
    }
    private static boolean overlaps(Set<Long> a,Set<Long> b) {for(Long id:b)if(a.contains(id))return true;return false;}
    static int progress(Store.Event e,long now) {
        if(e.cancelled() || e.endMs<=e.startMs)return 0;
        return (int)Math.min(100,Math.max(0,(now-e.startMs)*100/(e.endMs-e.startMs)));
    }
    static String phase(Store.Event e,long now) {
        if(e.cancelled())return "Отменено";
        if(e.startMs<=now && e.endMs>now)return "Идёт сейчас";
        long minutes=(e.startMs-now+59999)/60000;
        if(minutes>0 && minutes<=15)return "Через " + minutes + " мин";
        return e.moved()?"Перенесено":"По расписанию";
    }
    static String accessible(Store.Event e,long now) {
        return e.club + ". " + e.date + ", " + e.start + "–" + e.end + ". " + e.room + ". " + e.leader + ". " + phase(e,now) + ". Открыть кружок";
    }
    static long nextTick(List<Store.Event> events,long now) {
        long next=now+3600000L;
        for(Store.Event e:events) {
            if(e.cancelled())continue;
            long soon=e.startMs-900000L;
            if(soon>now)next=Math.min(next,soon);
            if(e.startMs>now)next=Math.min(next,e.startMs);
            if(e.endMs>now)next=Math.min(next,e.endMs);
            if(e.endMs>now && e.startMs-now<=900000L)next=Math.min(next,now+60000L);
        }
        return next;
    }
}
