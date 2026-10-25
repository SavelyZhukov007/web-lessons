package ru.kipfin.clubs;

import android.content.Context;

import com.google.firebase.messaging.FirebaseMessaging;

/** Вызывается из Push.refresh через reflection — в сборке без FCM этого класса нет. */
public final class ItcFcm {
    private ItcFcm() {}

    public static void fetchToken(Context c) {
        FirebaseMessaging.getInstance().getToken().addOnSuccessListener(token -> {
            if (token != null && !token.equals(Store.prefs(c).getString(Push.K_TOKEN, ""))) Push.saveToken(c, token);
            Push.registerAsync(c);
        });
    }
}
