// 通德的固定入口（Cloudflare Worker）
//
// 用户永远访问 Worker 的网址，Worker 把请求转发到服务器当前的快速隧道链接（*.trycloudflare.com）。
// 隧道链接会变：服务器上的 tunnel.sh 每次拿到新链接，就 POST /__tunnel 告诉这里，存进 KV。
//
// 在 Cloudflare 网页上要配置的（步骤见 docs/features/fixed-url.md）：
//   KV 绑定  TUNNEL     存当前链接，键名 url
//   密钥     SET_TOKEN  和服务器上 ~/sprachbruecke/.worker_token 一样，只有知道它才能改链接

const TUNNEL_RE = /^https:\/\/[a-z0-9-]+\.trycloudflare\.com$/;
const CACHE_MS = 30 * 1000;   // 同一个 Worker 实例里缓存链接 30 秒，少读 KV（免费额度每天 10 万次读）

let cached = null;
let cachedAt = 0;

async function origin(env) {
  if (cached && Date.now() - cachedAt < CACHE_MS) return cached;
  cached = await env.TUNNEL.get("url");
  cachedAt = Date.now();
  return cached;
}

async function setOrigin(request, env) {
  if (!env.SET_TOKEN || request.headers.get("X-Tunnel-Token") !== env.SET_TOKEN) {
    return new Response("forbidden", { status: 403 });
  }
  let url = "";
  try { url = String((await request.json()).url || ""); } catch (e) {}
  if (!TUNNEL_RE.test(url)) return new Response("bad url", { status: 400 });
  await env.TUNNEL.put("url", url);
  cached = url;
  cachedAt = Date.now();
  return new Response("ok");
}

function down() {
  const html = `<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>通德</title>
<style>body{font-family:system-ui,sans-serif;max-width:420px;margin:80px auto;padding:0 16px;color:#333;text-align:center}
@media (prefers-color-scheme:dark){body{background:#111;color:#ddd}}</style></head>
<body><h2>服务器暂时连不上</h2><p>可能正在重启，请过一两分钟再刷新。</p></body></html>`;
  return new Response(html, { status: 503, headers: { "Content-Type": "text/html; charset=utf-8", "Retry-After": "60" } });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/__tunnel" && request.method === "POST") return setOrigin(request, env);

    const base = await origin(env);
    if (!base) return down();

    const headers = new Headers(request.headers);
    headers.set("X-Real-IP", request.headers.get("CF-Connecting-IP") || "");
    let resp;
    try {
      resp = await fetch(base + url.pathname + url.search, {
        method: request.method,
        headers,
        body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
        redirect: "manual",
      });
    } catch (e) {
      cached = null;          // 可能链接刚换，下次重新读 KV
      return down();
    }
    // 隧道断了时 Cloudflare 返回 502 / 530
    if (resp.status === 530 || resp.status === 502) { cached = null; return down(); }

    const out = new Response(resp.body, resp);
    const loc = out.headers.get("Location");
    if (loc && loc.startsWith(base)) out.headers.set("Location", loc.slice(base.length) || "/");
    return out;
  },
};
