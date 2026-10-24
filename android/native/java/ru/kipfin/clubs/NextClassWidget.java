package ru.kipfin.clubs;

import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.Context;
import android.content.Intent;
import android.os.Bundle;

/** Виджет «Следующее занятие» (2×1 … 4×2, меняет раскладку по размеру). */
public class NextClassWidget extends AppWidgetProvider {
    static final String ACTION_TICK = "ru.kipfin.clubs.WIDGET_TICK";

    @Override
    public void onReceive(Context c, Intent intent) {
        if (ACTION_TICK.equals(intent.getAction())) { Widgets.updateAll(c); return; }
        super.onReceive(c, intent);
    }

    @Override
    public void onUpdate(Context c, AppWidgetManager m, int[] ids) { Widgets.updateAll(c); }

    @Override
    public void onAppWidgetOptionsChanged(Context c, AppWidgetManager m, int id, Bundle o) { Widgets.renderNext(c, m, id); }
}
