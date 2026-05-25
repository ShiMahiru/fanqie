# Fanqie Novel Worker

Cloudflare Worker / Pages 版本，静态页和 API 都由 Worker 接管。

## 行为

- `/api/rankings` 返回内置分类列表。
- `/api/ranking` 实时生成 `a_bogus` 并请求 `https://fanqienovel.com/api/rank/category/list`。
- 默认不回落本地快照；只有显式 `snapshot=1` 才读取内置快照。
- 搜索、书籍详情、章节正文走匿名代理请求。
- `/api/worker-self-test` 用来确认线上是否真正跑到了 Worker。

## Worker 部署

```bash
npm install
npm run deploy
```

## Pages 部署

如果用 Cloudflare Pages 静态部署，把输出目录设为 `worker/public`。
目录里已经生成 `_worker.js`，Pages 会用它接管 `/api/*`，避免只部署静态页面导致接口 404。

部署后先访问：

```text
https://你的域名/api/worker-self-test
https://你的域名/api/worker-self-test?upstream=1
```

第一个能返回 JSON 说明 Worker 路由已生效；第二个能返回 `upstream.ok=true` 说明官方接口在 Cloudflare 环境也能访问。
