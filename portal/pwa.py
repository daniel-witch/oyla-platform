"""Web-app ("PWA") support: the manifest, the service worker and the offline page.

Together these let students install Oyla on their phone or computer like a
normal app (own icon, full screen, no browser bar). Everything is still served
by this same Django server and uses the same database.
"""
import json

from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import cache_control

APP_VERSION = "oyla-v1"   # change this to make every installed app refresh its cached files

ICONS = "/static/portal/icons/"


@cache_control(max_age=3600)
def manifest(request):
    data = {
        "id": "/",
        "name": "Oyla Platform",
        "short_name": "Oyla",
        "description": "Critical thinking lessons, quizzes and progress for high school students.",
        "start_url": "/?source=app",
        "scope": "/",
        "display": "standalone",
        "orientation": "any",
        "background_color": "#f6f7fb",
        "theme_color": "#0f2a4a",
        "lang": "en",
        "categories": ["education"],
        "icons": [
            {"src": ICONS + "icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": ICONS + "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": ICONS + "icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
        "shortcuts": [
            {"name": "My dashboard", "url": "/", "icons": [{"src": ICONS + "icon-192.png", "sizes": "192x192"}]},
            {"name": "My data", "url": "/data/", "icons": [{"src": ICONS + "icon-192.png", "sizes": "192x192"}]},
        ],
    }
    return HttpResponse(json.dumps(data, indent=2), content_type="application/manifest+json")


SERVICE_WORKER = r"""
// Oyla Platform service worker - makes the site installable and keeps it usable offline.
const CACHE = "%(version)s";
const OFFLINE_URL = "/offline/";
const PRECACHE = [OFFLINE_URL, %(icons)s];
// Never cache these: personal data, saves, API and video streams always go to the server.
const NETWORK_ONLY = [/^\/api\//, /^\/admin\//, /^\/progress\//, /\/video\/$/, /^\/sw\.js$/];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (NETWORK_ONLY.some((re) => re.test(url.pathname))) return;

  // Pages: always fresh from the server; show the offline screen if there's no internet.
  if (req.mode === "navigate") {
    event.respondWith(fetch(req).catch(() => caches.match(OFFLINE_URL)));
    return;
  }
  // Icons, CSS, JS: use the saved copy, fetch and save it the first time.
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(
      caches.match(req).then((hit) => hit || fetch(req).then((res) => {
        if (res.ok) { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(req, copy)); }
        return res;
      }))
    );
  }
});
"""


def service_worker(request):
    icons = ", ".join(json.dumps(ICONS + n) for n in (
        "icon-192.png", "icon-512.png", "apple-touch-icon.png", "favicon-32.png"))
    js = SERVICE_WORKER % {"version": APP_VERSION, "icons": icons}
    resp = HttpResponse(js, content_type="application/javascript; charset=utf-8")
    resp["Service-Worker-Allowed"] = "/"
    resp["Cache-Control"] = "no-cache"
    return resp


def offline(request):
    return render(request, "portal/offline.html")
