package ru.kipfin.clubs;

/** Session-latched GPU/RenderThread pressure. One isolated hitch never changes the material. */
final class FrameBudget {
    private int samples, slow, severe;
    private boolean overloaded;
    boolean record(long nanos, float hz) {
        if (overloaded || nanos <= 0) return overloaded;
        samples++;
        if (nanos > 1_650_000_000.0 / Math.max(1, hz)) slow++;
        if (nanos >= 250_000_000L) severe++;
        overloaded = (samples >= 8 && severe >= 2) || (samples >= 30 && slow > samples * .22);
        if (!overloaded && samples >= 30) { samples = 0; slow = 0; severe = 0; }
        return overloaded;
    }
}
