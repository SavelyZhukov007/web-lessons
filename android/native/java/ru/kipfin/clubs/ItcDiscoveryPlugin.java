package ru.kipfin.clubs;

import android.content.Context;
import android.net.ConnectivityManager;
import android.net.LinkAddress;
import android.net.LinkProperties;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.net.nsd.NsdManager;
import android.net.nsd.NsdServiceInfo;

import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.URL;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Поиск тестового сервера в локальной сети (только демо-сборка, без сервисов Google):
 *  - nsd({timeoutMs}): mDNS/DNS-SD через NsdManager, тип _itc-kruzhki._tcp → [{host, port, name}];
 *  - wifi(): IPv4 и префикс активной Wi‑Fi/Ethernet-сети;
 *  - scan({ports, timeoutMs, concurrency}): перебор /24 своей сети, GET http://ip:port/api/app/info,
 *    события «scan» {done,total} и «found» {base, info}; cancelScan() — остановка.
 *  - probe({url, timeoutMs}): один GET (без CORS) → {status, body}.
 */
@CapacitorPlugin(name = "ItcDiscovery")
public class ItcDiscoveryPlugin extends Plugin {
    private static final String TYPE = "_itc-kruzhki._tcp";
    private final AtomicBoolean cancel = new AtomicBoolean(false);
    private volatile ExecutorService pool;

    private static String get(String url, int timeout, int max) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        try {
            c.setConnectTimeout(timeout); c.setReadTimeout(timeout); c.setInstanceFollowRedirects(false);
            c.setRequestProperty("Accept", "application/json");
            if (c.getResponseCode() != 200) return null;
            try (InputStream in = c.getInputStream()) {
                ByteArrayOutputStream out = new ByteArrayOutputStream(); byte[] b = new byte[4096]; int n;
                while ((n = in.read(b)) > 0) { out.write(b, 0, n); if (out.size() > max) return null; }
                return out.toString("UTF-8");
            }
        } finally { c.disconnect(); }
    }

    @PluginMethod
    public void probe(PluginCall call) {
        String url = call.getString("url", ""); int t = call.getInt("timeoutMs", 4000);
        if (!url.startsWith("http://") && !url.startsWith("https://")) { call.reject("bad url"); return; }
        new Thread(() -> {
            try { String body = get(url, t, 65536); JSObject r = new JSObject(); r.put("status", body == null ? 0 : 200); r.put("body", body == null ? "" : body); call.resolve(r); }
            catch (Exception e) { call.reject(e.getClass().getSimpleName() + ": " + e.getMessage()); }
        }).start();
    }

    @PluginMethod
    public void wifi(PluginCall call) {
        JSObject r = new JSObject();
        try {
            ConnectivityManager cm = (ConnectivityManager) getContext().getSystemService(Context.CONNECTIVITY_SERVICE);
            Network n = cm.getActiveNetwork();
            NetworkCapabilities caps = n == null ? null : cm.getNetworkCapabilities(n);
            LinkProperties lp = n == null ? null : cm.getLinkProperties(n);
            boolean lan = caps != null && (caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) || caps.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET));
            r.put("lan", lan);
            if (lp != null) for (LinkAddress la : lp.getLinkAddresses()) {
                if (la.getAddress() instanceof Inet4Address) { r.put("ip", la.getAddress().getHostAddress()); r.put("prefix", la.getPrefixLength()); break; }
            }
        } catch (Exception e) { r.put("error", e.getMessage()); }
        call.resolve(r);
    }

    @PluginMethod
    public void nsd(PluginCall call) {
        final int timeout = call.getInt("timeoutMs", 4000);
        final NsdManager nsd = (NsdManager) getContext().getSystemService(Context.NSD_SERVICE);
        final Map<String, JSObject> found = new ConcurrentHashMap<>();
        final List<NsdServiceInfo> queue = new ArrayList<>();
        final AtomicBoolean resolving = new AtomicBoolean(false);
        final NsdManager.DiscoveryListener[] holder = new NsdManager.DiscoveryListener[1];
        final Runnable[] next = new Runnable[1];
        next[0] = () -> {
            NsdServiceInfo s;
            synchronized (queue) { if (queue.isEmpty() || !resolving.compareAndSet(false, true)) return; s = queue.remove(0); }
            try {
                nsd.resolveService(s, new NsdManager.ResolveListener() {
                    @Override public void onResolveFailed(NsdServiceInfo i, int code) { resolving.set(false); next[0].run(); }
                    @Override public void onServiceResolved(NsdServiceInfo i) {
                        InetAddress h = i.getHost();
                        if (h instanceof Inet4Address) {
                            JSObject o = new JSObject(); o.put("host", h.getHostAddress()); o.put("port", i.getPort()); o.put("name", i.getServiceName());
                            found.put(h.getHostAddress() + ":" + i.getPort(), o);
                        }
                        resolving.set(false); next[0].run();
                    }
                });
            } catch (Exception e) { resolving.set(false); }
        };
        holder[0] = new NsdManager.DiscoveryListener() {
            @Override public void onStartDiscoveryFailed(String t, int c) { finish(call, found); }
            @Override public void onStopDiscoveryFailed(String t, int c) {}
            @Override public void onDiscoveryStarted(String t) {}
            @Override public void onDiscoveryStopped(String t) {}
            @Override public void onServiceFound(NsdServiceInfo s) { synchronized (queue) { queue.add(s); } next[0].run(); }
            @Override public void onServiceLost(NsdServiceInfo s) {}
        };
        try { nsd.discoverServices(TYPE, NsdManager.PROTOCOL_DNS_SD, holder[0]); }
        catch (Exception e) { finish(call, found); return; }
        new Thread(() -> {
            try { Thread.sleep(timeout); } catch (InterruptedException ignored) {}
            try { nsd.stopServiceDiscovery(holder[0]); } catch (Exception ignored) {}
            finish(call, found);
        }).start();
    }

    private final Map<PluginCall, Boolean> done = new ConcurrentHashMap<>();
    private void finish(PluginCall call, Map<String, JSObject> found) {
        if (done.putIfAbsent(call, true) != null) return;
        JSArray a = new JSArray(); for (JSObject o : found.values()) a.put(o);
        JSObject r = new JSObject(); r.put("services", a); call.resolve(r); done.remove(call);
    }

    @PluginMethod
    public void scan(PluginCall call) {
        final String ip = call.getString("ip", "");
        final int timeout = call.getInt("timeoutMs", 700), conc = Math.max(4, Math.min(64, call.getInt("concurrency", 32)));
        final List<Integer> ports = new ArrayList<>();
        try { JSArray p = call.getArray("ports"); for (int i = 0; i < p.length(); i++) ports.add(p.getInt(i)); } catch (Exception e) { ports.add(8000); }
        final String[] parts = ip.split("\\.");
        if (parts.length != 4) { call.reject("no ipv4"); return; }
        final String net = parts[0] + "." + parts[1] + "." + parts[2] + ".";
        cancel.set(false);
        final ExecutorService ex = Executors.newFixedThreadPool(conc); pool = ex;
        final int total = 254 * ports.size(); final AtomicInteger cnt = new AtomicInteger();
        final JSArray hits = new JSArray();
        for (int port : ports) for (int h = 1; h <= 254; h++) {
            final String base = (port == 443 ? "https://" : "http://") + net + h + (port == 80 || port == 443 ? "" : ":" + port);
            ex.submit(() -> {
                if (cancel.get()) return;
                try {
                    String body = get(base + "/api/app/info", timeout, 8192);
                    if (body != null) {
                        JSONObject j = new JSONObject(body);
                        if ("itc-kruzhki".equals(j.optString("app"))) {
                            JSObject o = new JSObject(); o.put("base", base); o.put("info", JSObject.fromJSONObject(j));
                            synchronized (hits) { hits.put(o); } notifyListeners("found", o);
                        }
                    }
                } catch (Exception ignored) {}
                int d = cnt.incrementAndGet();
                if (d % 16 == 0 || d == total) { JSObject p = new JSObject(); p.put("done", d); p.put("total", total); notifyListeners("scan", p); }
            });
        }
        ex.shutdown();
        new Thread(() -> {
            try { ex.awaitTermination(120, TimeUnit.SECONDS); } catch (InterruptedException ignored) {}
            JSObject r = new JSObject(); r.put("found", hits); r.put("cancelled", cancel.get()); call.resolve(r);
        }).start();
    }

    @PluginMethod
    public void cancelScan(PluginCall call) {
        cancel.set(true); ExecutorService p = pool; if (p != null) p.shutdownNow(); call.resolve();
    }
}
