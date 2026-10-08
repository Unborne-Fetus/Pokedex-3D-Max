package com.unbornefetus.pokedex3dmax.desktop;

import com.sun.net.httpserver.HttpServer;
import javax.swing.JOptionPane;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;

/** Serves the exact index shipped with the web build in a Chromium app window. */
public final class SharedApp {
    private static Path pack;
    private static volatile long lastHeartbeat = System.currentTimeMillis();
    private static String desktopManifest = "";

    public static void main(String[] args) {
        HttpServer server = null;
        try {
            pack = findPack();
            desktopManifest = manifest();
            server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
            server.createContext("/", exchange -> {
                try {
                    String path = exchange.getRequestURI().getPath();
                    if (path.equals("/heartbeat")) {
                        lastHeartbeat = System.currentTimeMillis();
                        exchange.sendResponseHeaders(204, -1);
                        return;
                    }
                    if (!Set.of("GET", "HEAD").contains(exchange.getRequestMethod())) {
                        exchange.sendResponseHeaders(405, -1); return;
                    }
                    if (path.equals("/")) path = "/index.html";
                    byte[] bytes;
                    if (path.equals("/web/desktop-models.js")) {
                        bytes = desktopManifest.getBytes(StandardCharsets.UTF_8);
                    } else if (path.startsWith("/offline/")) {
                        Path file = pack == null ? null : pack.resolve(path.substring(9)).normalize();
                        if (file == null || !file.startsWith(pack) || !Files.isRegularFile(file)
                            || !file.toRealPath().startsWith(pack.toRealPath())) {
                            exchange.sendResponseHeaders(404, -1); return;
                        }
                        exchange.getResponseHeaders().set("Content-Type", mime(path));
                        exchange.sendResponseHeaders(200, Files.size(file));
                        if (!exchange.getRequestMethod().equals("HEAD"))
                            Files.copy(file, exchange.getResponseBody());
                        return;
                    } else {
                        if (path.contains("..") || path.contains("\\")) {
                            exchange.sendResponseHeaders(400, -1); return;
                        }
                        try (InputStream input = SharedApp.class.getResourceAsStream("/shared-web" + path)) {
                            if (input == null) { exchange.sendResponseHeaders(404, -1); return; }
                            bytes = input.readAllBytes();
                        }
                    }
                    exchange.getResponseHeaders().set("Content-Type", mime(path));
                    exchange.getResponseHeaders().set("Cache-Control", "no-cache");
                    exchange.sendResponseHeaders(200, bytes.length);
                    if (!exchange.getRequestMethod().equals("HEAD")) exchange.getResponseBody().write(bytes);
                } finally { exchange.close(); }
            });
            server.setExecutor(Executors.newCachedThreadPool(r -> {
                Thread thread = new Thread(r); thread.setDaemon(true); return thread;
            }));
            server.start();
            String url = "http://127.0.0.1:" + server.getAddress().getPort() + "/index.html?desktop=1";
            Path browser = findBrowser();
            if (browser == null) throw new IOException("Microsoft Edge or Google Chrome is required. Install either browser and reopen Pokedex 3D Max.");
            Path profile = Paths.get(System.getenv().getOrDefault("LOCALAPPDATA", System.getProperty("user.home")), "Pokedex3DMax", "browser-profile");
            Files.createDirectories(profile);
            new ProcessBuilder(browser.toString(), "--app=" + url, "--user-data-dir=" + profile,
                "--no-first-run", "--no-default-browser-check", "--autoplay-policy=no-user-gesture-required").start();
            // Chromium may hand the new window to its existing profile process.
            // Page heartbeats, rather than that launcher process, own server lifetime.
            while (System.currentTimeMillis() - lastHeartbeat < 90000) Thread.sleep(1000);
        } catch (Exception error) {
            error.printStackTrace();
            JOptionPane.showMessageDialog(null, error.getMessage(), "Pokedex 3D Max", JOptionPane.ERROR_MESSAGE);
        } finally { if (server != null) server.stop(0); }
    }

    private static Path findBrowser() {
        for (String base : List.of("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")) {
            String root = System.getenv(base);
            if (root == null) continue;
            for (String relative : List.of("Microsoft/Edge/Application/msedge.exe", "Google/Chrome/Application/chrome.exe")) {
                Path path = Paths.get(root, relative);
                if (Files.isRegularFile(path)) return path;
            }
        }
        return null;
    }

    private static Path findPack() {
        List<Path> roots = new ArrayList<>();
        String custom = System.getenv("POKEDEX_3D_MAX_MODELS"), local = System.getenv("LOCALAPPDATA");
        if (custom != null && !custom.isBlank()) roots.add(Paths.get(custom));
        if (local != null) roots.add(Paths.get(local, "Pokedex3DMax", "offline-models"));
        roots.add(Paths.get("offline-models"));
        roots.add(Paths.get(System.getProperty("user.home"), "Pokedex3DMax", "offline-models"));
        for (Path root : roots) if (Files.isRegularFile(root.resolve("model_catalog.tsv"))) return root.toAbsolutePath().normalize();
        return null;
    }

    private static String quote(String value) {
        StringBuilder out = new StringBuilder("\"");
        for (char c : value.toCharArray()) {
            if (c == '"' || c == '\\') out.append('\\').append(c);
            else if (c < 32) out.append(String.format("\\u%04x", (int)c));
            else out.append(c);
        }
        return out.append('"').toString();
    }

    private static String manifest() throws IOException {
        List<String> entries = new ArrayList<>();
        if (pack != null) for (String line : Files.readAllLines(pack.resolve("model_catalog.tsv"))) {
            String[] cells = line.split("\t");
            if (cells.length < 4 || !cells[0].matches("[0-9]+")) continue;
            Path file = pack.resolve(cells[3]).normalize();
            if (!file.startsWith(pack) || !Files.isRegularFile(file)) continue;
            String relative = pack.relativize(file).toString().replace('\\', '/');
            String encoded = Arrays.stream(relative.split("/")).map(part -> URLEncoder.encode(part, StandardCharsets.UTF_8).replace("+", "%20")).reduce((a,b) -> a + "/" + b).orElse("");
            entries.add("{\"dex\":" + Integer.parseInt(cells[0]) + ",\"name\":" + quote(cells[1]) + ",\"form\":" + quote(cells[2]) + ",\"url\":" + quote("/offline/" + encoded) + ",\"local\":true}");
        }
        return "window.POKEDEX3D_DESKTOP_MODELS=[" + String.join(",", entries) + "];";
    }

    private static String mime(String path) {
        if (path.endsWith(".html")) return "text/html; charset=utf-8";
        if (path.endsWith(".js")) return "text/javascript; charset=utf-8";
        if (path.endsWith(".css")) return "text/css; charset=utf-8";
        if (path.endsWith(".json")) return "application/json";
        if (path.endsWith(".wasm")) return "application/wasm";
        if (path.endsWith(".glb")) return "model/gltf-binary";
        if (path.endsWith(".png")) return "image/png";
        if (path.endsWith(".jpg")) return "image/jpeg";
        return "application/octet-stream";
    }
}
