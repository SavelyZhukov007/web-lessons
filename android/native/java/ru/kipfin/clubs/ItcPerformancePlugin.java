package ru.kipfin.clubs;

import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

/** Read-only capability/power state. No polling, permissions or device settings writes. */
@CapacitorPlugin(name = "ItcPerformance")
public class ItcPerformancePlugin extends Plugin {
    @PluginMethod public void getState(PluginCall call) {
        getActivity().runOnUiThread(() -> {
            if (getActivity() instanceof MainActivity) call.resolve(((MainActivity) getActivity()).performanceState());
            else call.reject("Activity unavailable");
        });
    }
}
