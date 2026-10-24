package ru.kipfin.clubs;

import android.Manifest;
import android.content.Intent;

import androidx.activity.result.ActivityResult;

import com.getcapacitor.JSObject;
import com.getcapacitor.PermissionState;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.ActivityCallback;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;

/**
 * Полноэкранный сканер QR (CameraX + ML Kit, модель встроена в APK — без Google Play-сервисов).
 *  scan({hint}) → {text} | {cancelled:true};  ошибки: "camera-denied", "no-camera".
 */
@CapacitorPlugin(name = "ItcScanner", permissions = { @Permission(strings = { Manifest.permission.CAMERA }, alias = "camera") })
public class ItcScannerPlugin extends Plugin {
    @PluginMethod
    public void scan(PluginCall call) {
        if (getPermissionState("camera") != PermissionState.GRANTED) { requestPermissionForAlias("camera", call, "onPerm"); return; }
        start(call);
    }

    @PermissionCallback
    private void onPerm(PluginCall call) {
        if (getPermissionState("camera") == PermissionState.GRANTED) start(call);
        else call.reject("Нет доступа к камере", "camera-denied");
    }

    private void start(PluginCall call) {
        Intent i = new Intent(getContext(), ScanActivity.class);
        i.putExtra("hint", call.getString("hint", "Наведите камеру на QR-код преподавателя"));
        startActivityForResult(call, i, "onResult");
    }

    @ActivityCallback
    private void onResult(PluginCall call, ActivityResult r) {
        if (call == null) return;
        JSObject o = new JSObject();
        Intent d = r.getData();
        if (r.getResultCode() == android.app.Activity.RESULT_OK && d != null && d.getStringExtra("text") != null) o.put("text", d.getStringExtra("text"));
        else if (d != null && "no-camera".equals(d.getStringExtra("error"))) { call.reject("Камера не найдена", "no-camera"); return; }
        else o.put("cancelled", true);
        call.resolve(o);
    }
}
