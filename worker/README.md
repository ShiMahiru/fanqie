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
