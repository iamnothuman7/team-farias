{% load static %}/* Team Farias — service worker {{ version }} */
const VERSION = "{{ version }}";
const STATIC_CACHE = `tf-static-${VERSION}`;
const PAGE_CACHE = `tf-pages-${VERSION}`;

const PRECACHE = [
  "{% static 'css/app.css' %}",
  "{% static 'css/dashboard.css' %}",
  "{% static 'js/app.js' %}",
  "{% static 'js/dashboard.js' %}",
  "{% static 'js/vendor/htmx.min.js' %}",
  "{% static 'img/logo-sm.webp' %}",
  "{% static 'img/icon-192.png' %}",
  "{% static 'img/favicon-32.png' %}",
  "{% static 'fonts/archivo-latin.woff2' %}",
  "{% static 'fonts/jakarta-latin.woff2' %}",
  "/offline/",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => cache.addAll(PRECACHE)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((key) => ![STATIC_CACHE, PAGE_CACHE].includes(key)).map((key) => caches.delete(key)))
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  // Nunca cacheia área logada, painel ou admin.
  if (url.pathname.startsWith("/app/") || url.pathname.startsWith("/painel/") || url.pathname.startsWith("/admin/")) {
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(PAGE_CACHE).then((cache) => cache.put(request, copy));
          return response;
        })
        .catch(() => caches.match(request).then((cached) => cached || caches.match("/offline/")))
    );
    return;
  }

  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached;
      return fetch(request).then((response) => {
        if (response.ok && (url.pathname.startsWith("/static/") || url.pathname.startsWith("/media/"))) {
          const copy = response.clone();
          caches.open(STATIC_CACHE).then((cache) => cache.put(request, copy));
        }
        return response;
      });
    })
  );
});
