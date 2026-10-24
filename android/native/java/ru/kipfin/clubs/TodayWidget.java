package ru.kipfin.clubs;

import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.Context;

/** Виджет «Сегодня» 4×2 (растягивается): список занятий дня с отменами и переносами. */
public class TodayWidget extends AppWidgetProvider {
    @Override
    public void onUpdate(Context c, AppWidgetManager m, int[] ids) { Widgets.updateAll(c); }
}
