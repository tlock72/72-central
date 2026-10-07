// 72 Central background helper: shows result alerts sent by scripts/notify.py (Web Push) and opens the site
// when one is tapped. It doesn't touch page loading at all (no fetch handler, nothing cached).
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));
self.addEventListener("push", e => {
  let m = {};
  try { m = e.data ? e.data.json() : {}; } catch (err) { m = { title: e.data ? e.data.text() : "" }; }
  e.waitUntil(self.registration.showNotification(m.title || "72 Central", {
    body: m.body || "", icon: "app-icon-192.png?v=3", badge: "app-icon-192.png?v=3", data: { url: m.url || "./" }
  }));
});
self.addEventListener("notificationclick", e => {
  e.notification.close();
  const url = new URL((e.notification.data && e.notification.data.url) || "./", self.registration.scope).href;
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(list => {
    const open = list.find(c => c.url.startsWith(self.registration.scope));
    return open ? open.focus() : self.clients.openWindow(url);
  }));
});
