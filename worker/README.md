# Fanqie Novel Worker

Cloudflare Worker 版本，静态页和 API 都在 `src/index.js`。

## 行为

- `/api/ranking` 实时生成 `a_bogus` 并请求 `https://fanqienovel.com/api/rank/category/list`。
- 实时请求失败时回落到 `src/data.js` 里的抓包快照。
- 搜索、书籍详情、章节正文走匿名代理请求。

## Run

```bash
npm install
npm run dev
```

## Deploy

```bash
npm run deploy
```

## Cloudflare Worker 适配自检（2026-05-24）

- 入口采用 Worker Modules 语法（`export default { fetch() {} }`），可被 Wrangler 直接打包。
- 路由逻辑基于 `Request/Response/fetch/URL` 等 Web 标准 API，无 Node 服务端监听代码。
- `wrangler.toml` 已配置 `main`、`compatibility_date` 与 `assets` 绑定。
- `wrangler deploy --dry-run` 在本地通过，可完成打包与上传前检查。

