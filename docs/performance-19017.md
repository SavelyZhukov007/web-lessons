# 1.9.017 — «Сегодня» и адаптивная плавность Android

## Изменения
- «Сегодня» не исчезает; активное состояние и aria-pressed, одинаково в web/PWA/APK.
- Android: максимальный поддерживаемый режим той же геометрии экрана, с уважением к энергосбережению; аппаратный WebView без принудительной огромной cached layer.
- full/light/none материал: память, ядра, reduced transparency, power saver и runtime RAF/Window FrameMetrics. Нет постоянного FPS polling; деградация в пределах сессии, без колебаний вверх-вниз.
- Лента: одна отменяемая transform-пружина, геометрия через ResizeObserver; без scrollIntoView/scrollLeft в цикле. При смене дня удерживается высота списка и убраны конкурирующие анимации.
- Во время движения blur выключен; passive input и rAF batching; content-visibility для длинного списка. R8/shrinkResources с keep для native/FCM/Workers.

## Проверка на телефоне
TECNO BF7n, Android 12/API 31, WebView 156, 720×1612, единственный режим **60 Гц**, saver выключен.
Одинаковый сценарий: 6 подтверждённых пар Пн→Вт→Сегодня, прокрутка длинного списка, 3 открытия/закрытия фильтров; приложение оставалось foreground. Измерение после запуска процесса и gfxinfo reset.

| Метрика | 1.9.016 | 1.9.017 исправленная |
|---|---:|---:|
| gfxinfo frames/janky | 376/376 | 848/173 |
| janky | 100% | 20.40% |
| histogram p90/p95, ms | 150/250 | 42/61 |
| raw FrameCompleted−IntendedVsync p90/p95, ms | 612.89/881.72 | 358.38/437.34 |

Raw — последние 120 валидных samples OEM ring buffer; histogram — весь сценарий. Это **не** измерение полного compositor FPS WebView и не подтверждение 120 FPS на Pixel.

## Найденная регрессия и её устранение
В промежуточной сборке raw p95 был 1101.96 ms. На Tecno native RAM≈2.74 GB ошибочно допускала light blur. A/B в одном диагностическом APK: light blur p95≈1000 ms, none≈348 ms; задержки приходились на RenderThread/GPU, не JS/layout. RAF-probe пропускал stalls≥250 ms и первое запоздавшее событие. Теперь ≤3.25 GB получает none, motion снимает blur синхронно, долгие foreground stalls учитываются; Window FrameMetrics страхует GPU-задержки. Повторный signed release p95=437.34 ms, регрессия устранена.

API 30–34: обычный WebView не отдаёт собственный публичный Surface; используются Window preferredDisplayModeId/preferredRefreshRate. API35+: дополнительно View.setRequestedFrameRate. Принудительные системные настройки частоты не меняются.

Тесты: backend416, frontend123, e2e46, PWA55, responsive658, Android Node17, native UI108, JVM22. Старый legacy App-F runner сохранён без изменений; отдельный новый performance runner не подменяет его.
