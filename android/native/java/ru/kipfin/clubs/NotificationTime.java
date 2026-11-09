package ru.kipfin.clubs;
/** Pure Moscow-time policy (UTC+3, independent of the phone timezone). */
final class NotificationTime {
    static final long DAY=86400000L, OFFSET=10800000L;
    static int minute(String s) { if(s==null || !s.matches("(?:[01]\\d|2[0-3]):[0-5]\\d"))throw new IllegalArgumentException("HH:mm");return Integer.parseInt(s.substring(0,2))*60+Integer.parseInt(s.substring(3)); }
    static long today(long now,int minute){return Math.floorDiv(now+OFFSET,DAY)*DAY-OFFSET+minute*60000L;}
    static long quietEnd(long now,boolean enabled,int a,int b){
        int m=(int)Math.floorMod(Math.floorDiv(now+OFFSET,60000L),1440L);
        if(!enabled || a==b || !(a<b ? m>=a&&m<b : m>=a||m<b))return 0;
        long end=today(now,b);return end<=now?end+DAY:end;
    }
    static long next(long now,int minute){long at=today(now,minute);return at<=now?at+DAY:at;}
}
