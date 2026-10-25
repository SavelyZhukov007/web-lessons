package ru.kipfin.clubs;

import androidx.annotation.NonNull;

import com.google.firebase.messaging.FirebaseMessagingService;
import com.google.firebase.messaging.RemoteMessage;

/** Приём FCM (только в сборке с google-services.json). Вся логика — в Push (общая с опросом дедупликация). */
public class ItcMessagingService extends FirebaseMessagingService {
    @Override
    public void onMessageReceived(@NonNull RemoteMessage message) {
        Push.handle(getApplicationContext(), message.getData());
    }

    @Override
    public void onNewToken(@NonNull String token) {
        Push.saveToken(getApplicationContext(), token);
        Push.registerAsync(getApplicationContext());
    }
}
