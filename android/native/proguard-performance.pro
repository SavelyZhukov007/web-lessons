# Capacitor plugins/JS bridge are reflection entry points. Keep our native contracts and Workers.
-keepattributes RuntimeVisibleAnnotations,AnnotationDefault
-keep class ru.kipfin.clubs.** { *; }
-keep class * extends com.getcapacitor.Plugin { *; }
-keepclassmembers class * { @android.webkit.JavascriptInterface <methods>; }
