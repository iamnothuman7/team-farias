{% load static %}/* Team Farias — service worker {{ version }} */
const VERSION = "{{ version }}";
const DEVELOPMENT = {{ development|yesno:"true,false" }};
const STATIC_CACHE = `tf-static-${VERSION}`;
const PAGE_CACHE = `tf-pages-${VERSION}`;

const PRECACHE = [
  "{% static 'css/app.css' %}",
  "{% static 'css/dashboard.css' %}",
  "{% static 'css/shop.css' %}",
  "{% static 'css/refinements.css' %}",
  "{% static 'js/app.js' %}",
  "{% static 'js/install.js' %}",
  "{% static 'js/dashboard.js' %}",
  "{% static 'js/notifications.js' %}",
  "{% static 'js/vendor/htmx.min.js' %}",
  "{% static 'img/logo-sm.webp' %}",
  "{% static 'img/icon-192.png' %}",
  "{% static 'img/favicon-32.png' %}",
  "{% static 'fonts/archivo-latin.woff2' %}",
  "{% static 'fonts/jakarta-latin.woff2' %}",
  "/offline/",
];

self.addEventListener("install", (event) => {
  if (DEVELOPMENT) { self.skipWaiting(); return; }
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => cache.addAll(PRECACHE.map((url) => new Request(url, { credentials: "omit" })))).then(() => self.skipWaiting())
  );
});

self.addEventListener('push', (event) => {
  let data = {};
  try { data = event.data?.json() || {}; } catch (_) {}
  const url = typeof data.url === 'string' && /^\/app\/comunicados\/\d+\/$/.test(data.url) ? data.url : '/app/comunicados/';
  event.waitUntil(self.registration.showNotification('Team Farias', {
    body:'Você tem um novo comunicado da escolinha. Abra sua conta para ler.',
    icon:"{% static 'img/icon-192.png' %}", tag:data.tag || 'team-farias-comunicado',
    data:{url},
  }));
});
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const path = event.notification.data?.url || '/app/comunicados/';
  const url = new URL(path, self.location.origin);
  if(url.origin !== self.location.origin || !url.pathname.startsWith('/app/comunicados/')) return;
  event.waitUntil(self.clients.openWindow(url.href));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((key) => key.startsWith("tf-") && (DEVELOPMENT || ![STATIC_CACHE, PAGE_CACHE].includes(key))).map((key) => caches.delete(key)))
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  if (DEVELOPMENT) return;
  const { request } = event;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  // Só arquivos estáticos são armazenados. HTML contém CSRF e dados de sessão.
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(caches.match(request).then((cached) => cached || fetch(request).then((response) => {
      if (response.ok) {
        const copy = response.clone();
        event.waitUntil(caches.open(STATIC_CACHE).then((cache) => cache.put(request, copy)));
      }
      return response;
    })));
    return;
  }
  if (request.mode === "navigate") {
    event.respondWith(fetch(request).catch(() => caches.match("/offline/")));
  }
});
