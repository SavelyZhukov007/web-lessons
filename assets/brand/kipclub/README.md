# KipClub — ресурсы бренда

Цвета комплекта: фон `#B83B29`, знак `#FFF8F4`. Описание исходных экспортов и их ограничений находится в [source/README.txt](source/README.txt).

- [`source/`](source/) — векторные исходники и экспортированные PNG/ICO для веба, PWA, iOS и Android.
- [`android/res/`](android/res/) — готовые Android-ресурсы: adaptive icons (включая monochrome), legacy mipmap и splash-экраны.
- Android-сборка копирует launcher-иконки и splash-ресурсы в генерируемый проект через [`android/scripts/patch-android.mjs`](../../../android/scripts/patch-android.mjs). Не редактируйте копии в сгенерированном `android/android/`; меняйте исходные файлы в этом каталоге.
- Рабочие веб-иконки и favicon находятся в [`frontend/icons/`](../../../frontend/icons/) и [`frontend/favicon.ico`](../../../frontend/favicon.ico).
