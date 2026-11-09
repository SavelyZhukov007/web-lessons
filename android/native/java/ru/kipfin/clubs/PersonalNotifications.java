package ru.kipfin.clubs;
import android.app.AlarmManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import org.json.JSONArray;
import org.json.JSONObject;

/** Persistent bounded quiet-hour queue and one opt-in cached daily digest. */
final class PersonalNotifications {
    static final String FLUSH="ru.kipfin.clubs.QUIET_FLUSH", DIGEST="ru.kipfin.clubs.DIGEST";
    static PendingIntent alarm(Context c,String action){return PendingIntent.getBroadcast(c,action.hashCode(),new Intent(c,ReminderReceiver.class).setAction(action),PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);}
    static void at(Context c,String action,long time){
        AlarmManager am=(AlarmManager)c.getSystemService(Context.ALARM_SERVICE);if(am==null)return;
        PendingIntent pi=alarm(c,action);am.cancel(pi);if(time<=0)return;
        if(Build.VERSION.SDK_INT<31 || am.canScheduleExactAlarms())try{am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP,time,pi);return;}catch(SecurityException ignored){}
        am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP,time,pi);
    }
    static JSONArray queue(Context c){try{return new JSONArray(Store.prefs(c).getString("quiet_queue","[]"));}catch(Exception e){return new JSONArray();}}
    static synchronized void defer(Context c,String channel,int id,String title,String text,String path){
        if(Notifier.CH_REMIND.equals(channel))return; // never wake someone with an expired class reminder
        JSONArray old=queue(c),next=new JSONArray();long now=System.currentTimeMillis();
        for(int i=Math.max(0,old.length()-99);i<old.length();i++){JSONObject row=old.optJSONObject(i);if(row!=null&&row.optInt("id")!=id&&row.optLong("expires")>now)next.put(row);}
        long clubId=0;try{String idText=android.net.Uri.parse(path).getQueryParameter("id");if(idText!=null)clubId=Long.parseLong(idText);}catch(Exception ignored){}
        try{next.put(new JSONObject().put("club_id",clubId).put("channel",channel).put("id",id).put("title",title).put("text",text).put("path",path).put("expires",now+2*NotificationTime.DAY));}catch(Exception ignored){}
        Store.prefs(c).edit().putString("quiet_queue",next.toString()).commit();at(c,FLUSH,Store.quietEnd(c,now));
    }
    static synchronized void flush(Context c){
        long now=System.currentTimeMillis(),end=Store.quietEnd(c,now);if(end>0){at(c,FLUSH,end);return;}
        JSONArray rows=queue(c);Store.prefs(c).edit().putString("quiet_queue","[]").commit();
        for(int i=0;i<rows.length();i++){JSONObject row=rows.optJSONObject(i);if(row==null||row.optLong("expires")<=now)continue;String channel=row.optString("channel");
            long clubId=row.optLong("club_id");if(clubId>0&&!Store.follows(c).contains(clubId))continue;
            if(Notifier.isChangeChannel(channel)&&!Store.notifyChange(c,channel))continue;
            if(Notifier.CH_ANN.equals(channel)&&!Store.notifyAnnouncements(c))continue;
            Notifier.post(c,channel,row.optInt("id"),row.optString("title"),row.optString("text"),row.optString("path","/"));
        }
    }
    static void schedule(Context c){
        long now=System.currentTimeMillis();if(queue(c).length()>0){long end=Store.quietEnd(c,now);at(c,FLUSH,end>0?end:now+1000);}
        if(!Store.prefs(c).getBoolean("digest_enabled",false)||Store.follows(c).isEmpty()){at(c,DIGEST,0);return;}
        int minute;try{minute=NotificationTime.minute(Store.prefs(c).getString("digest_time","08:00"));}catch(IllegalArgumentException e){minute=480;}
        long next=NotificationTime.next(now,minute),quiet=Store.quietEnd(c,next);at(c,DIGEST,quiet>0?quiet:next);
    }
    static synchronized void digest(Context c){
        long now=System.currentTimeMillis();if(!Store.prefs(c).getBoolean("digest_enabled",false)||Store.follows(c).isEmpty()){schedule(c);return;}
        if(Store.quietEnd(c,now)>0){at(c,DIGEST,Store.quietEnd(c,now));return;}
        String day=Store.mskDate(now);if(day.equals(Store.prefs(c).getString("digest_last_day",""))){schedule(c);return;}
        StringBuilder text=new StringBuilder();int count=0;
        for(Store.Event e:Store.mine(c))if(day.equals(e.date)&&!e.cancelled()&&e.endMs>now){count++;if(text.length()<400){if(text.length()>0)text.append(" · ");text.append(e.start).append(" ").append(e.club);}}
        if(count>0&&Notifier.allowed(c)){Store.prefs(c).edit().putString("digest_last_day",day).commit();Notifier.post(c,Notifier.CH_DIGEST,("digest:"+day).hashCode(),"Сегодня в «Моих кружках»: "+count,text.toString(),"/my");}
        schedule(c);
    }
}
