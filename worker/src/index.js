import { DATA } from './data.js';
import { HTML } from './html.js';
import { PUA_MAP } from './pua.js';
import { generateABogus } from './a_bogus.js';

const UA_WEB = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36';
const JSON_HEADERS = {
  'content-type': 'application/json; charset=utf-8',
  'access-control-allow-origin': '*',
  'access-control-allow-methods': 'GET, POST, OPTIONS',
  'access-control-allow-headers': 'content-type',
};

const DETAIL_CACHE = new Map();
const CHAPTER_CACHE = new Map();

export default {
  async fetch(request) {
    if (request.method === 'OPTIONS') return new Response(null, { headers: JSON_HEADERS });
    const url = new URL(request.url);
    try {
      if (request.method === 'GET') return await handleGet(request, url);
      if (request.method === 'POST') return await handlePost(request, url);
      return json({ error: 'method not allowed' }, 405);
    } catch (error) {
      return json({ error: String(error && error.message ? error.message : error) }, 502);
    }
  },
};

async function handleGet(request, url) {
  const path = url.pathname;
  if (path === '/') return html(HTML);
  if (path === '/api/health') {
    return json({ ok: true, mode: 'cloudflare-worker', time: new Date().toISOString(), login_removed: true, features: DATA.features.map((f) => f.source) });
  }
  if (path === '/api/interfaces') return json(buildInterfaceMap());
  if (path === '/api/capture-summary') return json(DATA.capture);
  if (path === '/api/stats') return json(buildStats());
  if (path === '/api/search-filters') return json(fetchSearchFilters());
  if (path === '/api/latest-updates') return json(await fetchRecentUpdates(url.searchParams.get('offset') || '0', url.searchParams.get('limit') || '20'));
  if (path === '/api/recommend') return json(await fetchRecommendBooks(url.searchParams.get('type') || '3', url.searchParams.get('offset') || '0', url.searchParams.get('limit') || '10'));
  if (path === '/api/top-books') return json(await fetchTopBooks(url.searchParams.get('offset') || '0', url.searchParams.get('limit') || '200'));
  if (path === '/api/rankings' || path === '/api/mcp/list_rankings') return json(fetchLeaderboards());
  if (path === '/api/ranking' || path === '/api/mcp/get_ranking') {
    return json(await fetchRankingBooks(url.searchParams.get('ranking_id') || '', url.searchParams.get('offset') || '0', url.searchParams.get('limit') || '30'));
  }
  if (path === '/api/search') {
    return json(await fetchSearch(
      url.searchParams.get('query') || '',
      url.searchParams.get('query_type') || '1',
      url.searchParams.get('filter') || '127,127,127,127',
      url.searchParams.get('page_index') || '0',
      url.searchParams.get('page_count') || '10',
    ));
  }
  if (path === '/api/novels') return json({ novels: [], total: 0, page: 1, pages: 1, per_page: 50 });
  if (path === '/api/mcp/get_book_detail') {
    const bookId = url.searchParams.get('book_id') || url.searchParams.get('id') || '';
    if (!bookId) return json({ error: 'Missing book_id' }, 400);
    return json(await fetchBookDetail(bookId));
  }
  if (path === '/api/mcp/get_chapter_content') {
    const chapterId = url.searchParams.get('chapter_id') || url.searchParams.get('id') || '';
    if (!chapterId) return json({ error: 'Missing chapter_id' }, 400);
    return json(await fetchChapterContent(chapterId));
  }
  let match = path.match(/^\/api\/novels\/(\d+)$/);
  if (match) return json(await fetchBookDetail(match[1]));
  match = path.match(/^\/api\/novels\/(\d+)\/chapters$/);
  if (match) {
    const detail = await fetchBookDetail(match[1]);
    const chapters = detail.chapters || [];
    return json({ chapters, total: chapters.length, page: 1, pages: 1, per_page: chapters.length || 1, novel_id: match[1] });
  }
  match = path.match(/^\/api\/novels\/(\d+)\/chapters\/(\d+)$/);
  if (match) {
    const chapter = await fetchChapterContent(match[2]);
    return json({ ...chapter, novel_id: match[1] });
  }
  match = path.match(/^\/api\/chapters\/(\d+)$/);
  if (match) return json(await fetchChapterContent(match[1]));
  match = path.match(/^\/api\/novels\/(\d+)\/download$/);
  if (match) return downloadNovel(match[1]);
  return json({ error: 'not found' }, 404);
}

async function handlePost(request, url) {
  if (url.pathname === '/api/novels') {
    const body = await request.json().catch(() => ({}));
    const novelId = String(body.novel_id || body.id || '');
    if (!novelId) return json({ error: 'Missing novel_id' }, 400);
    return json(await fetchBookDetail(novelId));
  }
  return json({ error: 'not found' }, 404);
}

function fetchLeaderboards() {
  return { source: 'worker-snapshot', snapshot_date: new Date().toISOString(), count: DATA.rankings.length, groups: DATA.groups, rankings: DATA.rankings, error: '' };
}

async function fetchRankingBooks(rankingId, offsetRaw, limitRaw) {
  const ranking = DATA.rankings.find((item) => item.id === rankingId || item.name === rankingId) || DATA.rankings[0];
  if (!ranking) return { ranking_id: '', ranking_name: '', count: 0, total: 0, books: [], source: 'fanqie-web-rank-category-list', error: '未知榜单。' };
  const offset = Math.max(0, Number.parseInt(offsetRaw, 10) || 0);
  const limit = Math.max(1, Math.min(Number.parseInt(limitRaw, 10) || 30, 100));
  try {
    return await fetchLiveRankingBooks(ranking, offset, limit);
  } catch (error) {
    return fetchSnapshotRankingBooks(ranking, offset, limit, error);
  }
}

async function fetchLiveRankingBooks(ranking, offset, limit) {
  const params = new URLSearchParams({
    app_id: '2503',
    rank_list_type: String(ranking.rank_list_type || 3),
    offset: String(offset),
    limit: String(limit),
    category_id: String(ranking.category_id),
    rank_version: String(ranking.rank_version || ''),
    gender: String(ranking.gender),
    rankMold: String(ranking.rankMold),
  });
  const referer = `https://fanqienovel.com/rank/${ranking.gender}_${ranking.rankMold}_${ranking.category_id}`;
  const { payload, sourceUrl } = await fanqieJsonGet('/api/rank/category/list', params, referer);
  if (payload.code !== 0) throw new Error(payload.message || 'rank api failed');
  const { books, total } = booksFromCategoryPayload(payload, offset + 1);
  return rankingResponse(ranking, books, total, 'fanqie-web-rank-category-list', sourceUrl, '');
}

function fetchSnapshotRankingBooks(ranking, offset, limit, error) {
  const key = `${ranking.gender}|${ranking.rankMold}|${ranking.category_id}`;
  const bucket = DATA.rankSnapshot[key] || { books: [], total: 0 };
  const books = bucket.books.slice(offset, offset + limit);
  return rankingResponse(ranking, books, bucket.total || bucket.books.length, 'worker-snapshot', '', books.length ? '' : String(error && error.message ? error.message : error));
}

function rankingResponse(ranking, books, total, source, sourceUrl, error) {
  return {
    ranking_id: ranking.id,
    ranking_name: ranking.name,
    category_id: ranking.category_id,
    gender: ranking.gender,
    rankMold: ranking.rankMold,
    source_api: ranking.source_api,
    count: books.length,
    total,
    books,
    source,
    source_url: sourceUrl,
    error,
  };
}

function booksFromCategoryPayload(payload, baseRank = 1) {
  const data = payload && typeof payload.data === 'object' ? payload.data : {};
  const raw = Array.isArray(data.book_list) ? data.book_list : (Array.isArray(data.bookList) ? data.bookList : (Array.isArray(data.list) ? data.list : []));
  const books = raw.map((item, index) => normalizeRankBook(item, baseRank + index)).filter(Boolean);
  return { books, total: Number.parseInt(data.total_num, 10) || books.length };
}

function normalizeRankBook(item, rank) {
  if (!item || typeof item !== 'object') return null;
  const book = item.book_data && typeof item.book_data === 'object' ? item.book_data : item;
  const id = String(book.bookId || book.book_id || book.id || '');
  const title = cleanText(book.bookName || book.book_name || book.title || book.book_title || '');
  if (!id || !title) return null;
  return {
    id,
    rank: Number.parseInt(book.currentPos || book.rank || book.rankIdx, 10) || rank,
    title,
    author: cleanText(book.author || book.authorName || book.author_name || ''),
    category: cleanText(book.category || book.categoryName || book.book_type || book.categoryV2 || ''),
    synopsis: cleanText(book.abstract || book.description || book.desc || book.introduction || ''),
    cover: normalizeCover(String(book.thumbUri || book.thumb_url || book.cover || book.cover_url || '')),
    score: cleanText(book.rank_score || book.rankScore || ''),
    read_count: String(book.read_count || book.readCount || ''),
    word_count: String(book.wordNumber || book.word_num || book.word_count || ''),
    creation_status: String(book.creationStatus || book.creation_status || ''),
  };
}

function cleanText(value) {
  return decryptPua(String(value || '')).trim();
}

function normalizeSearchText(value) {
  return cleanText(value).toLowerCase().replace(/[\W_]+/g, '');
}

function rankSearchResults(query, results) {
  const needle = normalizeSearchText(query);
  if (!needle) return [...results];
  return results.filter((item) => normalizeSearchText(item.title) === needle);
}

async function fetchSearch(query, queryType = '1', filterValue = '127,127,127,127', pageIndexRaw = '0', pageCountRaw = '10') {
  if (!query) return { results: [] };
  const pageIndex = boundedInt(pageIndexRaw, 0, 0, 1000);
  const pageCount = boundedInt(pageCountRaw, 10, 1, 100);
  const params = new URLSearchParams({
    filter: String(filterValue),
    page_count: String(pageCount),
    page_index: String(pageIndex),
    query_type: String(queryType || '1'),
    query_word: query,
  });
  try {
    const { payload } = await fanqieJsonGet('/api/author/search/search_book/v1', params, `https://fanqienovel.com/search/${encodeURIComponent(query)}`);
    const data = payload && typeof payload.data === 'object' ? payload.data : {};
    const raw = Array.isArray(data.search_book_data_list) ? data.search_book_data_list : [];
    const results = rankSearchResults(query, raw.map(normalizeSearchBook).filter(Boolean));
    return { results, total: Number.parseInt(data.total_count, 10) || results.length, query_type: String(queryType || '1'), filter: String(filterValue), source: 'fanqie-web-search-book' };
  } catch (error) {
    return fetchSearchFromHtml(query, queryType, filterValue, pageCount);
  }
}

async function fetchSearchFromHtml(query, queryType, filterValue, pageCount) {
  const page = await fetchText(`https://fanqienovel.com/search/${encodeURIComponent(query)}`, { accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8' });
  const state = parseInitialState(page);
  const results = [];
  if (state) {
    for (const cur of walkObjects(state)) {
      const book = normalizeSearchBook(cur);
      if (book) results.push(book);
    }
  }
  return { results: rankSearchResults(query, dedupeBooks(results)).slice(0, pageCount), query_type: String(queryType || '1'), filter: String(filterValue), fallback: 'search-html' };
}

function normalizeSearchBook(item) {
  if (!item || typeof item !== 'object') return null;
  const book = item.book_data && typeof item.book_data === 'object' ? item.book_data : item;
  const id = String(book.book_id || book.bookId || book.id || '');
  const title = book.book_name || book.bookName || book.title || '';
  if (!id || !title) return null;
  return {
    id,
    title: cleanText(title),
    author: cleanText(book.author || book.author_name || book.authorName || ''),
    category: cleanText(book.category || book.categoryName || ''),
    synopsis: cleanText(book.book_abstract || book.abstract || book.description || book.desc || ''),
    cover: normalizeCover(String(book.thumb_url || book.thumbUri || book.thumb_uri || book.cover || book.cover_url || '')),
    read_count: String(book.read_count || book.readCount || ''),
    word_count: String(book.word_count || book.wordNumber || book.word_num || ''),
    creation_status: String(book.creation_status || book.creationStatus || ''),
    last_chapter_title: cleanText(book.last_chapter_title || ''),
  };
}

async function fetchRecentUpdates(offsetRaw = '0', limitRaw = '20') {
  const offset = boundedInt(offsetRaw, 0, 0, 10000);
  const limit = boundedInt(limitRaw, 20, 1, 100);
  const { payload, sourceUrl } = await fanqieJsonGet('/api/rank/recent/update/list', new URLSearchParams({ offset: String(offset), limit: String(limit) }));
  const data = payload && typeof payload.data === 'object' ? payload.data : {};
  const rows = Array.isArray(data.data) ? data.data : [];
  const updates = rows.map((item) => ({
    id: String(item.bookId || item.book_id || ''),
    chapter_id: String(item.itemId || item.item_id || ''),
    title: cleanText(item.bookName || item.book_name || ''),
    chapter_title: cleanText(item.title || item.chapterName || ''),
    author: cleanText(item.author || ''),
    category: cleanText(item.category || ''),
    update_time: String(item.updateTime || ''),
    need_pay: item.needPay,
  })).filter((item) => item.id || item.chapter_id);
  return { updates, count: updates.length, total: Number.parseInt(data.total, 10) || updates.length, source_url: sourceUrl };
}

async function fetchRecommendBooks(kind = '3', offsetRaw = '0', limitRaw = '10') {
  const offset = boundedInt(offsetRaw, 0, 0, 10000);
  const limit = boundedInt(limitRaw, 10, 1, 100);
  const { payload, sourceUrl } = await fanqieJsonGet('/api/rank/recommend/list', new URLSearchParams({ type: String(kind), offset: String(offset), limit: String(limit) }));
  const data = payload && typeof payload.data === 'object' ? payload.data : {};
  const rows = Array.isArray(data.list) ? data.list : [];
  const books = rows.map((item, index) => normalizeSimpleBook(item, offset + index + 1)).filter(Boolean);
  return { type: String(kind), books, count: books.length, total: Number.parseInt(data.total, 10) || books.length, source_url: sourceUrl };
}

async function fetchTopBooks(offsetRaw = '0', limitRaw = '200') {
  const offset = boundedInt(offsetRaw, 0, 0, 10000);
  const limit = boundedInt(limitRaw, 200, 1, 500);
  const { payload, sourceUrl } = await fanqieJsonGet('/api/author/misc/top_book_list/v1/', new URLSearchParams({ offset: String(offset), limit: String(limit) }));
  const rows = Array.isArray(payload?.book_list) ? payload.book_list : [];
  const books = rows.slice(0, limit).map((item, index) => normalizeSimpleBook(item, offset + index + 1)).filter(Boolean);
  return { books, count: books.length, source_url: sourceUrl };
}

function fetchSearchFilters() {
  return {
    query_types: [
      { id: '1', name: '书名' },
    ],
    filter_format: '固定书名搜索，不再提供热度筛选。',
    captured_filters: ['127,127,127,127'],
    feeds: {
      latest_updates: '/api/latest-updates?offset=0&limit=20',
      recommend: '/api/recommend?type=3&offset=0&limit=10',
      hot_books: '/api/top-books?offset=0&limit=200',
    },
  };
}

async function fetchBookDetail(bookId) {
  if (DETAIL_CACHE.has(bookId)) return DETAIL_CACHE.get(bookId);
  const page = await fetchText(`https://fanqienovel.com/page/${bookId}`);
  const state = parseInitialState(page);
  const detail = { id: String(bookId), title: '', author: '', description: '', status: '', tags: '', total_chapters_source: 0, chapters_in_db: 0, last_crawled_at: new Date().toISOString(), created_at: new Date().toISOString(), cover_image_url: '' };
  if (state) {
    for (const cur of walkObjects(state)) {
      const title = cur.bookName || cur.book_name || cur.title;
      if (title && (cur.bookId || cur.book_id || cur.id || cur.bookName || cur.book_name)) {
        detail.title = decryptPua(String(title));
        detail.author = decryptPua(String(cur.author || cur.authorName || cur.author_name || ''));
        detail.description = decryptPua(String(cur.abstract || cur.description || cur.desc || ''));
        detail.status = String(cur.creationStatus || cur.status || '');
        const tags = cur.tags || cur.categoryV2 || cur.category || '';
        detail.tags = Array.isArray(tags) ? tags.join('|') : String(tags || '');
        detail.cover_image_url = normalizeCover(String(cur.thumbUri || cur.cover || cur.cover_url || ''));
        break;
      }
    }
  }
  if (!detail.title) {
    const m = page.match(/<h1[^>]*>([\s\S]*?)<\/h1>/i);
    detail.title = m ? decryptPua(stripTags(m[1])) : `Book ${bookId}`;
  }
  const htmlChapters = extractChaptersFromHtml(page);
  const liveChapters = await fetchChapters(bookId).catch(() => []);
  const chapters = mergeChapters(liveChapters, htmlChapters);
  detail.chapters_in_db = chapters.length;
  detail.total_chapters_source = chapters.length;
  detail.chapters = chapters;
  DETAIL_CACHE.set(bookId, detail);
  return detail;
}

function extractChaptersFromHtml(htmlText) {
  const chapters = [];
  const re = /<a[^>]*href="\/reader\/(\d+)"[^>]*>([\s\S]*?)<\/a>/g;
  for (const match of htmlText.matchAll(re)) chapters.push({ id: match[1], index: chapters.length + 1, title: decryptPua(stripTags(match[2])), is_free: true, fetched_at: new Date().toISOString() });
  return dedupeChapters(chapters);
}

async function fetchChapters(bookId) {
  let data;
  try {
    data = (await fanqieJsonGet('/api/reader/directory/detail', new URLSearchParams({ bookId: String(bookId) }), `https://fanqienovel.com/page/${bookId}`)).payload;
  } catch (error) {
    data = await fetchJson(`https://fanqienovel.com/api/reader/directory/detail?bookId=${encodeURIComponent(bookId)}`);
  }
  const source = data?.data || {};
  let items = source.chapterListWithVolume || source.list || source.item_list || source.allItemIds || [];
  if (!Array.isArray(items)) items = [];
  const flat = [];
  for (const item of items) {
    if (Array.isArray(item)) flat.push(...item);
    else if (item && Array.isArray(item.itemList)) flat.push(...item.itemList);
    else flat.push(item);
  }
  const chapters = [];
  flat.forEach((item, idx) => {
    let id = '';
    let title = `第${idx + 1}章`;
    let isFree = true;
    if (item && typeof item === 'object') {
      id = String(item.itemId || item.item_id || item.id || '');
      title = item.title || item.chapterName || title;
      const needPay = Number.isInteger(item.needPay) ? item.needPay : item.need_pay;
      isFree = needPay === 0 && !item.isPaidStory;
    } else {
      id = String(item || '');
    }
    if (id) chapters.push({ id, index: chapters.length + 1, title: decryptPua(String(title)), is_free: isFree, fetched_at: new Date().toISOString() });
  });
  return chapters;
}

async function fetchChapterContent(chapterId) {
  if (CHAPTER_CACHE.has(chapterId)) return CHAPTER_CACHE.get(chapterId);
  try {
    const { payload } = await fanqieJsonGet('/api/reader/full', new URLSearchParams({ itemId: String(chapterId) }), `https://fanqienovel.com/reader/${chapterId}`);
    const chapterData = payload?.data?.chapterData || {};
    const content = cleanText(stripTags(String(chapterData.content || '')));
    if (content) {
      const result = { id: String(chapterId), title: cleanText(String(chapterData.title || '').trim()), content, source: 'fanqie-reader-full' };
      CHAPTER_CACHE.set(chapterId, result);
      return result;
    }
  } catch (error) {
    // Fall through to the rendered reader page.
  }
  const page = await fetchText(`https://fanqienovel.com/reader/${chapterId}`);
  const state = parseInitialState(page);
  if (!state) throw new Error('未解析到章节初始状态');
  const chapterData = state?.reader?.chapterData || {};
  const result = { id: String(chapterId), title: cleanText(String(chapterData.title || '').trim()), content: cleanText(stripTags(String(chapterData.content || ''))), fallback: 'reader-html' };
  CHAPTER_CACHE.set(chapterId, result);
  return result;
}

async function downloadNovel(bookId) {
  const detail = await fetchBookDetail(bookId);
  const parts = [`${detail.title}\n作者：${detail.author}\n\n${detail.description}\n`];
  const chapters = (detail.chapters || []).slice(0, 200);
  for (const chapter of chapters) {
    try {
      const content = await fetchChapterContent(chapter.id);
      parts.push(`\n${content.title || chapter.title}\n\n${content.content || ''}\n`);
    } catch (error) {
      parts.push(`\n${chapter.title}\n\n[无法获取：${String(error.message || error)}]\n`);
    }
  }
  const safeName = encodeURIComponent((detail.title || bookId).replace(/[\\/:*?"<>|]+/g, '_') + '.txt');
  return new Response(parts.join('\n'), { headers: { 'content-type': 'text/plain; charset=utf-8', 'content-disposition': `attachment; filename="novel.txt"; filename*=UTF-8''${safeName}` } });
}

function buildStats() {
  return { generated_at: new Date().toISOString(), anonymous: true, login_removed: true, features: DATA.features, ranking_groups: DATA.groups.length, ranking_categories: DATA.rankings.length, ranking_count: DATA.rankings.length, shelf_total: 0, detail_cache_total: DETAIL_CACHE.size, chapter_cache_total: CHAPTER_CACHE.size, interfaces_same: false };
}

function buildInterfaceMap() {
  return {
    same: false,
    summary: 'cloudflare-worker',
    login: 'removed',
    features: DATA.features,
    capture: DATA.capture,
    canonical: {
      capture_summary: '/api/capture-summary', rankings: '/api/rankings', ranking_books: '/api/ranking?ranking_id=<web榜单ID>', search_filters: '/api/search-filters', search: '/api/search?query=关键词&query_type=1&filter=127,127,127,127', latest_updates: '/api/latest-updates?offset=0&limit=20', recommend: '/api/recommend?type=3&offset=0&limit=10', hot_books: '/api/top-books?offset=0&limit=200', book_detail: '/api/novels/<book_id>', chapters: '/api/novels/<book_id>/chapters', chapter_content: '/api/novels/<book_id>/chapters/<chapter_id>', download_txt: '/api/novels/<book_id>/download',
    },
    mcp_aliases: { list_rankings: '/api/mcp/list_rankings', get_ranking: '/api/mcp/get_ranking?ranking_id=<web榜单ID>&offset=0&limit=30', get_book_detail: '/api/mcp/get_book_detail?book_id=<book_id>', get_chapter_content: '/api/mcp/get_chapter_content?chapter_id=<chapter_id>' },
  };
}

async function fetchText(url, extraHeaders = {}) {
  const headers = {
    accept: '*/*',
    'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'cache-control': 'no-cache',
    pragma: 'no-cache',
    ...extraHeaders,
  };
  // Cloudflare Workers forbid manually setting `user-agent` on subrequests.
  // Remove it defensively to avoid runtime TypeError and stalled interfaces.
  delete headers['user-agent'];
  delete headers.User-Agent;
  const response = await fetch(url, {
    headers,
    redirect: 'follow',
    cf: { cacheTtl: 0, cacheEverything: false },
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.text();
}

async function fetchJson(url, extraHeaders = {}) {
  return JSON.parse(await fetchText(url, { accept: 'application/json, text/plain, */*', ...extraHeaders }));
}

function signedFanqieUrl(path, params) {
  const query = params instanceof URLSearchParams ? params.toString() : new URLSearchParams(params).toString();
  const aBogus = generateABogus(query, UA_WEB);
  return `https://fanqienovel.com${path}?${query}&a_bogus=${encodeURIComponent(aBogus)}`;
}

async function fanqieJsonGet(path, params, referer = 'https://fanqienovel.com/') {
  const sourceUrl = signedFanqieUrl(path, params);
  const payload = await fetchJson(sourceUrl, { referer });
  return { payload, sourceUrl };
}

function boundedInt(value, fallback, min, max) {
  const parsed = Number.parseInt(value, 10);
  let number = Number.isFinite(parsed) ? parsed : fallback;
  number = Math.max(min, number);
  if (typeof max === 'number') number = Math.min(max, number);
  return number;
}

function normalizeSimpleBook(item, rank = 0) {
  if (!item || typeof item !== 'object') return null;
  const id = String(item.bookId || item.book_id || item.id || '');
  const title = item.bookName || item.book_name || item.title || item.book_title || '';
  if (!id || !title) return null;
  return {
    id,
    rank: Number.parseInt(item.rank || item.rankIdx, 10) || rank,
    title: cleanText(title),
    author: cleanText(item.author || item.authorName || item.author_name || ''),
    category: cleanText(item.category || item.categoryName || item.book_type || item.categoryV2 || ''),
    synopsis: cleanText(item.abstract || item.book_abstract || item.description || item.desc || ''),
    cover: normalizeCover(String(item.thumbUri || item.thumb_uri || item.thumb_url || item.cover || item.cover_url || '')),
    score: cleanText(item.rank_score || item.rankScore || ''),
    read_count: String(item.read_count || item.readCount || ''),
    word_count: String(item.wordNumber || item.word_num || item.word_count || ''),
    creation_status: String(item.creationStatus || item.creation_status || ''),
  };
}

function parseInitialState(page) {
  const marker = 'window.__INITIAL_STATE__';
  const pos = page.indexOf(marker);
  if (pos < 0) return null;
  const rest = page.slice(pos + marker.length);
  const eq = rest.indexOf('=');
  if (eq < 0) return null;
  const text = rest.slice(eq + 1).trim();
  if (!text.startsWith('{')) return null;
  let depth = 0, inString = false, escaped = false, end = 0;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (escaped) { escaped = false; continue; }
    if (inString && ch === '\\') { escaped = true; continue; }
    if (ch === '"') { inString = !inString; continue; }
    if (!inString) {
      if (ch === '{') depth += 1;
      else if (ch === '}') {
        depth -= 1;
        if (depth === 0) { end = i + 1; break; }
      }
    }
  }
  if (!end) return null;
  try { return JSON.parse(text.slice(0, end).replaceAll('undefined', 'null').replace(/,\s*([}\]])/g, '$1')); } catch { return null; }
}

function* walkObjects(value) {
  const stack = [value];
  while (stack.length) {
    const cur = stack.pop();
    if (cur && typeof cur === 'object') {
      if (!Array.isArray(cur)) yield cur;
      for (const v of Object.values(cur)) if (v && typeof v === 'object') stack.push(v);
    }
  }
}

function stripTags(value) {
  return String(value || '').replace(/<br\s*\/?\s*>/gi, '\n').replace(/<\/p\s*>/gi, '\n').replace(/<[^>]+>/g, '').replace(/&nbsp;/g, ' ').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&').replace(/&quot;/g, '"').trim();
}

function decryptPua(value) {
  return Array.from(String(value || ''), (ch) => {
    const code = ch.codePointAt(0);
    return code >= 0xe000 && code <= 0xf8ff ? (PUA_MAP[code] || ch) : ch;
  }).join('');
}

function normalizeCover(value) {
  if (!value) return '';
  if (value.startsWith('//')) return `https:${value}`;
  if (value.startsWith('http')) return value;
  return `https://p3-novel.byteimg.com/${value.replace(/^\/+/, '')}`;
}

function mergeChapters(...sources) {
  return dedupeChapters(sources.flat().filter(Boolean)).map((chapter, index) => ({ ...chapter, index: index + 1 }));
}

function dedupeChapters(chapters) {
  const seen = new Set();
  const out = [];
  for (const chapter of chapters) {
    const id = String(chapter.id || chapter.chapter_id || '');
    if (!id || seen.has(id)) continue;
    seen.add(id);
    out.push({ ...chapter, id, title: decryptPua(String(chapter.title || `第${out.length + 1}章`)) });
  }
  return out;
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data, null, 2), { status, headers: JSON_HEADERS });
}

function html(body) {
  return new Response(body, { headers: { 'content-type': 'text/html; charset=utf-8' } });
}
