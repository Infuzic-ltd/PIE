self.addEventListener('push', function (event) {
  let data = { title: 'PIE Real Estate', body: 'You have a new notification.', url: '/' };
  try { data = Object.assign(data, JSON.parse(event.data.text())); } catch (e) {}

  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: '/static/img/logo.png',
      badge: '/static/img/logo.png',
      data: { url: data.url },
      requireInteraction: true,
    })
  );
});

self.addEventListener('notificationclick', function (event) {
  event.notification.close();
  const target = event.notification.data && event.notification.data.url ? event.notification.data.url : '/';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (list) {
      for (const c of list) {
        if (c.url === target && 'focus' in c) return c.focus();
      }
      if (clients.openWindow) return clients.openWindow(target);
    })
  );
});
