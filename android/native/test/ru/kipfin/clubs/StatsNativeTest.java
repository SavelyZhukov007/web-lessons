package ru.kipfin.clubs;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public class StatsNativeTest {
    private static Throwable at(String cls) {
        Throwable t = new RuntimeException("x");
        t.setStackTrace(new StackTraceElement[]{new StackTraceElement(cls, "m", "F.java", 1)});
        return t;
    }

    @Test public void crashSubsystemHasNoTextOrStack() {
        assertEquals("webview", CrashCounter.kind(at("org.chromium.content.Foo")));
        assertEquals("storage", CrashCounter.kind(at("android.database.sqlite.SQLiteDatabase")));
        assertEquals("net", CrashCounter.kind(at("java.net.Socket")));
        assertEquals("ui", CrashCounter.kind(at("ru.kipfin.clubs.MainActivity")));
        assertEquals("net", CrashCounter.kind(new IllegalStateException(at("javax.net.ssl.SSLSocket"))));
    }

    @Test public void shakeNeedsStrongJerk() {
        assertFalse(ShakeDetector.isShake(0f, 0f, 9.81f));
        assertFalse(ShakeDetector.isShake(15f, 10f, 9.81f));
        assertTrue(ShakeDetector.isShake(25f, 10f, 9.81f));
    }
}
