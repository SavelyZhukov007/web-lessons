package ru.kipfin.clubs;

import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import java.nio.charset.StandardCharsets;
import java.security.KeyStore;

import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/**
 * Шифрование локальных данных ученика (профиль: ФИО + группа) ключом AES-256-GCM из Android Keystore.
 * Ключ неизвлекаемый и не покидает Keystore; JS получает только шифртекст base64(iv|ct) и хранит его в localStorage.
 *  - encrypt({plain}) → {ct};  decrypt({ct}) → {plain};  wipe() — удалить ключ (данные станут нечитаемыми).
 */
@CapacitorPlugin(name = "ItcSecure")
public class ItcSecurePlugin extends Plugin {
    private static final String ALIAS = "itc_profile_v1";

    private static SecretKey key() throws Exception {
        KeyStore ks = KeyStore.getInstance("AndroidKeyStore");
        ks.load(null);
        if (ks.containsAlias(ALIAS)) return ((KeyStore.SecretKeyEntry) ks.getEntry(ALIAS, null)).getSecretKey();
        KeyGenerator g = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
        g.init(new KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build());
        return g.generateKey();
    }

    @PluginMethod
    public void encrypt(PluginCall call) {
        String plain = call.getString("plain");
        if (plain == null) { call.reject("plain required"); return; }
        try {
            Cipher c = Cipher.getInstance("AES/GCM/NoPadding");
            c.init(Cipher.ENCRYPT_MODE, key());
            byte[] iv = c.getIV();
            byte[] ct = c.doFinal(plain.getBytes(StandardCharsets.UTF_8));
            byte[] out = new byte[iv.length + ct.length];
            System.arraycopy(iv, 0, out, 0, iv.length);
            System.arraycopy(ct, 0, out, iv.length, ct.length);
            JSObject r = new JSObject();
            r.put("ct", Base64.encodeToString(out, Base64.NO_WRAP));
            call.resolve(r);
        } catch (Exception e) {
            call.reject("encrypt failed: " + e.getClass().getSimpleName());
        }
    }

    @PluginMethod
    public void decrypt(PluginCall call) {
        String ct = call.getString("ct");
        if (ct == null) { call.reject("ct required"); return; }
        try {
            byte[] raw = Base64.decode(ct, Base64.NO_WRAP);
            if (raw.length < 12 + 16) throw new IllegalArgumentException();
            Cipher c = Cipher.getInstance("AES/GCM/NoPadding");
            c.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, raw, 0, 12));
            byte[] p = c.doFinal(raw, 12, raw.length - 12);
            JSObject r = new JSObject();
            r.put("plain", new String(p, StandardCharsets.UTF_8));
            call.resolve(r);
        } catch (Exception e) {
            call.reject("decrypt failed: " + e.getClass().getSimpleName());
        }
    }

    @PluginMethod
    public void wipe(PluginCall call) {
        try {
            KeyStore ks = KeyStore.getInstance("AndroidKeyStore");
            ks.load(null);
            if (ks.containsAlias(ALIAS)) ks.deleteEntry(ALIAS);
            call.resolve();
        } catch (Exception e) {
            call.reject("wipe failed");
        }
    }
}
