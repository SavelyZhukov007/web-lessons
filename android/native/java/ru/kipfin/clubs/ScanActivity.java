package ru.kipfin.clubs;

import android.content.Intent;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.PorterDuff;
import android.graphics.PorterDuffXfermode;
import android.graphics.RectF;
import android.os.Bundle;
import android.util.Size;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.FrameLayout;
import android.widget.ImageButton;
import android.widget.TextView;

import androidx.annotation.NonNull;
import androidx.appcompat.app.AppCompatActivity;
import androidx.camera.core.Camera;
import androidx.camera.core.CameraSelector;
import androidx.camera.core.ImageAnalysis;
import androidx.camera.core.Preview;
import androidx.camera.lifecycle.ProcessCameraProvider;
import androidx.camera.view.PreviewView;
import androidx.core.content.ContextCompat;
import androidx.core.graphics.Insets;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowInsetsCompat;

import com.google.common.util.concurrent.ListenableFuture;
import com.google.mlkit.vision.barcode.BarcodeScanner;
import com.google.mlkit.vision.barcode.BarcodeScannerOptions;
import com.google.mlkit.vision.barcode.BarcodeScanning;
import com.google.mlkit.vision.barcode.common.Barcode;
import com.google.mlkit.vision.common.InputImage;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

/** Экран сканера: превью камеры, затемнение вокруг рамки с уголками, фонарик, закрыть. */
public class ScanActivity extends AppCompatActivity {
    private final ExecutorService exec = Executors.newSingleThreadExecutor();
    private final AtomicBoolean done = new AtomicBoolean(false);
    private Camera camera;
    private boolean torch;
    private BarcodeScanner scanner;

    private int dp(float v) { return (int) TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, getResources().getDisplayMetrics()); }

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        getWindow().setStatusBarColor(Color.BLACK);
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.BLACK);
        PreviewView preview = new PreviewView(this);
        preview.setImplementationMode(PreviewView.ImplementationMode.COMPATIBLE);
        root.addView(preview, new FrameLayout.LayoutParams(-1, -1));
        root.addView(new Overlay(), new FrameLayout.LayoutParams(-1, -1));

        TextView hint = new TextView(this);
        hint.setText(getIntent().getStringExtra("hint"));
        hint.setTextColor(Color.WHITE); hint.setTextSize(16); hint.setGravity(Gravity.CENTER);
        hint.setPadding(dp(24), 0, dp(24), 0);
        FrameLayout.LayoutParams hp = new FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM);
        hp.bottomMargin = dp(140);
        root.addView(hint, hp);

        ImageButton close = roundButton(android.R.drawable.ic_menu_close_clear_cancel, "Закрыть");
        close.setOnClickListener(v -> finishWith(null));
        FrameLayout.LayoutParams cp = new FrameLayout.LayoutParams(dp(48), dp(48), Gravity.TOP | Gravity.START);
        cp.leftMargin = dp(16); cp.topMargin = dp(16);
        root.addView(close, cp);

        ImageButton flash = roundButton(android.R.drawable.ic_menu_view, "Фонарик");
        flash.setOnClickListener(v -> {
            if (camera == null || !camera.getCameraInfo().hasFlashUnit()) return;
            torch = !torch; camera.getCameraControl().enableTorch(torch);
            flash.setAlpha(torch ? 1f : .75f);
            flash.getBackground().setTint(torch ? Color.WHITE : 0x66000000);
            flash.setColorFilter(torch ? Color.BLACK : Color.WHITE);
        });
        FrameLayout.LayoutParams fp = new FrameLayout.LayoutParams(dp(64), dp(64), Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL);
        fp.bottomMargin = dp(48);
        root.addView(flash, fp);

        ViewCompat.setOnApplyWindowInsetsListener(root, (v, ins) -> {
            Insets s = ins.getInsets(WindowInsetsCompat.Type.systemBars());
            cp.topMargin = dp(16) + s.top; close.setLayoutParams(cp);
            fp.bottomMargin = dp(48) + s.bottom; flash.setLayoutParams(fp);
            hp.bottomMargin = dp(140) + s.bottom; hint.setLayoutParams(hp);
            return ins;
        });
        setContentView(root);

        scanner = BarcodeScanning.getClient(new BarcodeScannerOptions.Builder().setBarcodeFormats(Barcode.FORMAT_QR_CODE).build());
        ListenableFuture<ProcessCameraProvider> f = ProcessCameraProvider.getInstance(this);
        f.addListener(() -> {
            try {
                ProcessCameraProvider p = f.get();
                if (!p.hasCamera(CameraSelector.DEFAULT_BACK_CAMERA)) { Intent d = new Intent(); d.putExtra("error", "no-camera"); setResult(RESULT_CANCELED, d); finish(); return; }
                Preview pv = new Preview.Builder().build();
                pv.setSurfaceProvider(preview.getSurfaceProvider());
                ImageAnalysis an = new ImageAnalysis.Builder().setTargetResolution(new Size(1280, 720))
                        .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST).build();
                an.setAnalyzer(exec, proxy -> {
                    @SuppressWarnings("UnsafeOptInUsageError") android.media.Image img = proxy.getImage();
                    if (img == null || done.get()) { proxy.close(); return; }
                    scanner.process(InputImage.fromMediaImage(img, proxy.getImageInfo().getRotationDegrees()))
                            .addOnSuccessListener(list -> { for (Barcode bc : list) if (bc.getRawValue() != null) { finishWith(bc.getRawValue()); break; } })
                            .addOnCompleteListener(t -> proxy.close());
                });
                p.unbindAll();
                camera = p.bindToLifecycle(this, CameraSelector.DEFAULT_BACK_CAMERA, pv, an);
                flash.setVisibility(camera.getCameraInfo().hasFlashUnit() ? View.VISIBLE : View.GONE);
            } catch (Exception e) { finishWith(null); }
        }, ContextCompat.getMainExecutor(this));
    }

    private ImageButton roundButton(int icon, String label) {
        ImageButton b = new ImageButton(this);
        b.setImageResource(icon); b.setContentDescription(label); b.setColorFilter(Color.WHITE);
        android.graphics.drawable.GradientDrawable bg = new android.graphics.drawable.GradientDrawable();
        bg.setShape(android.graphics.drawable.GradientDrawable.OVAL); bg.setColor(0x66000000);
        b.setBackground(bg); b.setScaleType(ImageButton.ScaleType.CENTER);
        return b;
    }

    private void finishWith(String text) {
        if (!done.compareAndSet(false, true)) return;
        runOnUiThread(() -> {
            if (text != null) { Intent d = new Intent(); d.putExtra("text", text); setResult(RESULT_OK, d); }
            else setResult(RESULT_CANCELED);
            finish();
        });
    }

    @Override protected void onDestroy() { super.onDestroy(); exec.shutdown(); if (scanner != null) scanner.close(); }

    /** Затемнение вне квадратной рамки + белые уголки. */
    private class Overlay extends View {
        private final Paint dim = new Paint(), clear = new Paint(Paint.ANTI_ALIAS_FLAG), line = new Paint(Paint.ANTI_ALIAS_FLAG);
        Overlay() {
            super(ScanActivity.this);
            setLayerType(LAYER_TYPE_HARDWARE, null);
            dim.setColor(0x99000000);
            clear.setXfermode(new PorterDuffXfermode(PorterDuff.Mode.CLEAR));
            line.setColor(Color.WHITE); line.setStyle(Paint.Style.STROKE); line.setStrokeWidth(dp(4)); line.setStrokeCap(Paint.Cap.ROUND);
        }
        @Override protected void onDraw(@NonNull Canvas c) {
            float w = getWidth(), h = getHeight(), s = Math.min(w, h) * 0.68f, l = (w - s) / 2, t = (h - s) / 2 - dp(24), r = dp(20), k = dp(28);
            c.drawRect(0, 0, w, h, dim);
            RectF box = new RectF(l, t, l + s, t + s);
            c.drawRoundRect(box, r, r, clear);
            Path p = new Path();
            p.moveTo(l, t + k); p.lineTo(l, t + r); p.quadTo(l, t, l + r, t); p.lineTo(l + k, t);
            p.moveTo(l + s - k, t); p.lineTo(l + s - r, t); p.quadTo(l + s, t, l + s, t + r); p.lineTo(l + s, t + k);
            p.moveTo(l + s, t + s - k); p.lineTo(l + s, t + s - r); p.quadTo(l + s, t + s, l + s - r, t + s); p.lineTo(l + s - k, t + s);
            p.moveTo(l + k, t + s); p.lineTo(l + r, t + s); p.quadTo(l, t + s, l, t + s - r); p.lineTo(l, t + s - k);
            c.drawPath(p, line);
        }
    }
}
