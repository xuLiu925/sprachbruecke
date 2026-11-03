// Service Worker(由 app.py 的 /sw.js 提供, 作用范围是整个网站)。
// 只管打开页面这一下: 连不上服务器时显示“连不上服务器 / 重试”, 而不是浏览器的断网页(装到桌面后更像 App)。
// 不缓存页面和数据: 所有内容都要服务器给, 缓存一个空壳只会让人以为打开了却什么都没有; 改了前端也不用管这里。
const OFFLINE = `<!doctype html><html lang="zh"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#1f4e78">
<title>通德</title><body style="font-family:sans-serif;text-align:center;padding:80px 20px;color:#333">
<h2>连不上服务器</h2><p>检查一下网络，稍后再试。</p>
<button onclick="location.reload()" style="font-size:16px;padding:10px 28px;border:0;border-radius:8px;background:#1f4e78;color:#fff">重试</button>`;

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(
  caches.keys().then(keys => Promise.all(keys.map(k => caches.delete(k)))).then(() => self.clients.claim())));

self.addEventListener("fetch", e => {
  if (e.request.mode !== "navigate") return;
  e.respondWith(fetch(e.request).catch(() =>
    new Response(OFFLINE, {headers: {"Content-Type": "text/html; charset=utf-8"}})));
});
