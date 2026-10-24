package ru.kipfin.clubs;

import android.content.Context;
import android.content.Intent;
import android.graphics.Paint;
import android.view.View;
import android.widget.RemoteViews;
import android.widget.RemoteViewsService;

import java.util.ArrayList;
import java.util.List;

public class TodayWidgetService extends RemoteViewsService {
    @Override
    public RemoteViewsFactory onGetViewFactory(Intent intent) { return new Factory(getApplicationContext()); }

    static List<Store.Event> today(Context c) {
        String day = Store.mskDate(Format.now());
        List<Store.Event> out = new ArrayList<>();
        for (Store.Event e : Store.mine(c)) if (day.equals(e.date) || (e.cancelled() && day.equals(e.originalDate))) out.add(e);
        return out;
    }

    static final class Factory implements RemoteViewsFactory {
        private final Context c;
        private List<Store.Event> items = new ArrayList<>();
        Factory(Context c) { this.c = c; }
        @Override public void onCreate() { }
        @Override public void onDataSetChanged() { items = today(c); }
        @Override public void onDestroy() { items.clear(); }
        @Override public int getCount() { return items.size(); }
        @Override public RemoteViews getLoadingView() { return null; }
        @Override public int getViewTypeCount() { return 1; }
        @Override public long getItemId(int i) { return items.get(i).key.hashCode(); }
        @Override public boolean hasStableIds() { return true; }

        @Override
        public RemoteViews getViewAt(int i) {
            Store.Event e = items.get(i);
            long now = Format.now();
            RemoteViews v = new RemoteViews(c.getPackageName(), R.layout.widget_today_row);
            v.setTextViewText(R.id.row_start, e.start);
            v.setTextViewText(R.id.row_end, e.end);
            v.setTextViewText(R.id.row_title, e.club);
            v.setTextViewText(R.id.row_room, e.room);
            v.setInt(R.id.row_bar, "setBackgroundColor", e.color);
            int flags = e.cancelled() ? Paint.STRIKE_THRU_TEXT_FLAG | Paint.ANTI_ALIAS_FLAG : Paint.ANTI_ALIAS_FLAG;
            v.setInt(R.id.row_title, "setPaintFlags", flags);
            String badge = e.cancelled() ? "Отменено" : e.moved() ? "Перенесено" : (e.startMs <= now && e.endMs > now ? "Идёт" : null);
            v.setViewVisibility(R.id.row_status, badge == null ? View.GONE : View.VISIBLE);
            if (badge != null) v.setTextViewText(R.id.row_status, badge);
            boolean dim = e.endMs < now || e.cancelled();
            v.setTextColor(R.id.row_title, c.getColor(dim ? R.color.widget_muted : R.color.widget_fg));
            v.setTextColor(R.id.row_start, c.getColor(dim ? R.color.widget_muted : R.color.widget_fg));
            Intent fill = new Intent().setData(android.net.Uri.parse("itckruzhki://open/club?id=" + e.clubId));
            v.setOnClickFillInIntent(R.id.row_container, fill);
            return v;
        }
    }
}
