package ru.kipfin.clubs;
import org.junit.Test;
import static org.junit.Assert.*;
public class FrameBudgetTest {
    @Test public void normal60HzDoesNotDowngrade() {
        FrameBudget b = new FrameBudget(); for(int i=0;i<90;i++) assertFalse(b.record(16_670_000L,60));
    }
    @Test public void actual120HzBudgetIsUsed() {
        FrameBudget b = new FrameBudget(); for(int i=0;i<29;i++) assertFalse(b.record(16_670_000L,120));
        assertTrue(b.record(16_670_000L,120));
    }
    @Test public void oneHitchIsNotEnough() {
        FrameBudget b = new FrameBudget(); assertFalse(b.record(600_000_000L,60));
        for(int i=0;i<29;i++) assertFalse(b.record(16_670_000L,60));
    }
    @Test public void twoSevereFramesLatchAndNeverSilentlyUpgrade() {
        FrameBudget b = new FrameBudget(); for(int i=0;i<6;i++) assertFalse(b.record(16_670_000L,60));
        assertFalse(b.record(300_000_000L,60)); assertTrue(b.record(400_000_000L,60));
        assertTrue(b.record(8_330_000L,120));
    }
    @Test public void invalidSamplesDoNotCount() {
        FrameBudget b = new FrameBudget(); for(int i=0;i<100;i++) assertFalse(b.record(0,60));
        for(int i=0;i<7;i++) assertFalse(b.record(40_000_000L,60));
    }
}
