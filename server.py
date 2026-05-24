#!/usr/bin/env python3
import json
import mimetypes
import os
import concurrent.futures
import re
import sys
import time
from datetime import datetime
from html import unescape
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlencode, urlparse, quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / 'static'
sys.path.insert(0, str(ROOT))
from a_bogus import generate_a_bogus
from pua_map import decrypt_pua

UA_RANK = 'Dalvik/2.1.0 (Linux; U; Android 10; SM-G975F Build/QP1A.190711.020) com.ss.android.article.news/831'
UA_WEB = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
SHELF = {}
CHAPTER_CACHE = {}
DETAIL_CACHE = {}
RANKING_CACHE = {}

SUITE_FEATURES = [
    {
        'source': 'fanqienovel-decryptor',
        'label': 'PUA 字体解密 / TXT 导出',
        'local_api': [
            '/api/novels/<id>/chapters/<chapter_id>',
            '/api/novels/<id>/download',
        ],
    },
    {
        'source': 'fanqie-novel',
        'label': '轻量前端阅读页',
        'local_api': [
            '/',
            '/api/search',
            '/api/novels/<id>',
        ],
    },
    {
        'source': 'fanqie-rank-mcp',
        'label': '番茄榜单',
        'local_api': [
            '/api/rankings',
            '/api/ranking',
            '/api/mcp/list_rankings',
            '/api/mcp/get_ranking',
        ],
    },
    {
        'source': 'fanqie-reader',
        'label': '无登录阅读器',
        'local_api': [
            '/api/search',
            '/api/novels',
            '/api/novels/<id>',
            '/api/novels/<id>/chapters',
            '/api/novels/<id>/chapters/<chapter_id>',
            '/api/novels/<id>/download',
        ],
    },
]

WEB_CATEGORY_FALLBACK = [
    {'id': '1141', 'name': '西方奇幻', 'groups': ['male']},
    {'id': '1140', 'name': '东方仙侠', 'groups': ['male']},
    {'id': '8', 'name': '科幻末世', 'groups': ['male', 'female']},
    {'id': '261', 'name': '都市日常', 'groups': ['male']},
    {'id': '124', 'name': '都市修真', 'groups': ['male']},
    {'id': '1014', 'name': '都市高武', 'groups': ['male']},
    {'id': '273', 'name': '历史古代', 'groups': ['male']},
    {'id': '27', 'name': '战神赘婿', 'groups': ['male']},
    {'id': '263', 'name': '都市种田', 'groups': ['male']},
    {'id': '258', 'name': '传统玄幻', 'groups': ['male']},
    {'id': '272', 'name': '历史脑洞', 'groups': ['male']},
    {'id': '539', 'name': '悬疑脑洞', 'groups': ['male', 'female']},
    {'id': '262', 'name': '都市脑洞', 'groups': ['male']},
    {'id': '257', 'name': '玄幻脑洞', 'groups': ['male']},
    {'id': '751', 'name': '悬疑灵异', 'groups': ['male']},
    {'id': '504', 'name': '抗战谍战', 'groups': ['male']},
    {'id': '746', 'name': '游戏体育', 'groups': ['male', 'female']},
    {'id': '718', 'name': '动漫衍生', 'groups': ['male']},
    {'id': '1016', 'name': '男频衍生', 'groups': ['male']},
    {'id': '1139', 'name': '古风世情', 'groups': ['female']},
    {'id': '1015', 'name': '女频衍生', 'groups': ['female']},
    {'id': '248', 'name': '玄幻言情', 'groups': ['female']},
    {'id': '23', 'name': '种田', 'groups': ['female']},
    {'id': '79', 'name': '年代', 'groups': ['female']},
    {'id': '267', 'name': '现言脑洞', 'groups': ['female']},
    {'id': '246', 'name': '宫斗宅斗', 'groups': ['female']},
    {'id': '253', 'name': '古言脑洞', 'groups': ['female']},
    {'id': '24', 'name': '快穿', 'groups': ['female']},
    {'id': '749', 'name': '青春甜宠', 'groups': ['female']},
    {'id': '745', 'name': '星光璀璨', 'groups': ['female']},
    {'id': '747', 'name': '女频悬疑', 'groups': ['female']},
    {'id': '750', 'name': '职场婚恋', 'groups': ['female']},
    {'id': '748', 'name': '豪门总裁', 'groups': ['female']},
    {'id': '1017', 'name': '民国言情', 'groups': ['female']},
]

WEB_RANK_SECTIONS = [
    {'title': '男频阅读榜', 'gender': '1', 'rankMold': '2', 'group': 'male'},
    {'title': '男频新书榜', 'gender': '1', 'rankMold': '1', 'group': 'male'},
    {'title': '女频阅读榜', 'gender': '0', 'rankMold': '2', 'group': 'female'},
    {'title': '女频新书榜', 'gender': '0', 'rankMold': '1', 'group': 'female'},
]

WEB_CATEGORY_CACHE = {'categories': WEB_CATEGORY_FALLBACK, 'fetched_at': '', 'error': ''}
HAR_RANK_PATHS = [
    Path('/storage/emulated/0/142.250.73.74_2026_05_24_18_51_13.TXT'),
    Path('/storage/emulated/0/Download/Reqable/mcs.zijieapi.com_2026_05_24_17_24_01.har'),
    ROOT / '142.250.73.74_2026_05_24_18_51_13.TXT',
    ROOT / 'mcs.zijieapi.com_2026_05_24_17_24_01.har',
]
WORKER_DATA_PATH = ROOT / 'worker' / 'src' / 'data.js'
HAR_READER_PATHS = [
    Path('/storage/emulated/0/Download/Reqable/mcs.zijieapi.com_2026_05_25_01_03_54.har'),
    Path('/storage/emulated/0/Download/Reqable/mcs.zijieapi.com_2026_05_25_00_56_14.har'),
    ROOT / 'mcs.zijieapi.com_2026_05_25_01_03_54.har',
    ROOT / 'mcs.zijieapi.com_2026_05_25_00_56_14.har',
]
HAR_RANK_SNAPSHOT = None
HAR_READER_SNAPSHOT = None
HAR_RANK_ERROR = ''
HAR_RANK_SOURCES = []


def build_web_ranking_groups(categories):
    groups = []
    for section in WEB_RANK_SECTIONS:
        items = []
        for category in categories:
            category_groups = category.get('groups', category.get('group', []))
            if isinstance(category_groups, str):
                category_groups = [category_groups]
            if section['group'] not in category_groups:
                continue
            category_id = str(category.get('id') or '')
            category_name = str(category.get('name') or category_id)
            if not category_id:
                continue
            ranking_id = f"web_{section['gender']}_{section['rankMold']}_{category_id}"
            items.append({
                'id': ranking_id,
                'name': category_name,
                'display_name': f"{section['title']} · {category_name}",
                'section': section['title'],
                'category_id': category_id,
                'category_name': category_name,
                'gender': section['gender'],
                'rankMold': section['rankMold'],
                'source_api': '/api/rank/category/list',
                'rank_list_type': 3,
                'rank_version': '',
            })
        if items:
            groups.append({'title': section['title'], 'items': items})
    return groups


RANKING_GROUPS = build_web_ranking_groups(WEB_CATEGORY_FALLBACK)
RANKING_LIST = [item for group in RANKING_GROUPS for item in group['items']]
RANKING_BY_ID = {}
RANKING_BY_NAME = {}
RANKING_ALIAS = {}


def refresh_ranking_indexes():
    RANKING_BY_ID.clear()
    RANKING_BY_NAME.clear()
    for item in RANKING_LIST:
        RANKING_BY_ID[item['id']] = item
        RANKING_BY_NAME[item.get('display_name') or item.get('name')] = item


refresh_ranking_indexes()

def now_iso():
    return datetime.now().replace(microsecond=0).isoformat()


def http_get(url, ua=UA_WEB, timeout=8, extra_headers=None):
    headers = {'User-Agent': ua, 'Accept': '*/*'}
    if extra_headers:
        headers.update(extra_headers)
    req = Request(url, headers=headers)
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode('utf-8', errors='replace')


def strip_tags(text):
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.I)
    text = re.sub(r'</p\s*>', '\n', text, flags=re.I)
    text = re.sub(r'<[^>]+>', '', text)
    return unescape(text).strip()


def walk_objects(value):
    stack = [value]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            yield cur
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)


def parse_initial_state(html):
    marker = 'window.__INITIAL_STATE__'
    pos = html.find(marker)
    if pos < 0:
        return None
    rest = html[pos + len(marker):]
    eq = rest.find('=')
    if eq < 0:
        return None
    text = rest[eq + 1:].strip()
    if not text.startswith('{'):
        return None
    depth = 0
    in_string = False
    escaped = False
    end = 0
    for i, ch in enumerate(text):
        if escaped:
            escaped = False
            continue
        if in_string and ch == '\\':
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if not in_string:
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
    if not end:
        return None
    raw = text[:end].replace('undefined', 'null')
    raw = re.sub(r',\s*([}\]])', r'\1', raw)
    try:
        return json.loads(raw)
    except Exception:
        return None


def normalize_cover(url):
    if not url:
        return ''
    if url.startswith('//'):
        return 'https:' + url
    if url.startswith('http'):
        return url
    return 'https://p3-novel.byteimg.com/' + url.lstrip('/')


def friendly_external_error(exc):
    text = str(exc)
    lowered = text.lower()
    if 'handshake operation timed out' in lowered or '_ssl.c' in lowered:
        return '官方入口刷新超时，已使用本地榜单快照。'
    if 'timed out' in lowered or 'timeout' in lowered:
        return '官方接口请求超时，已使用本地榜单快照。'
    if 'urlopen error' in lowered:
        return '官方接口暂时不可访问，已使用本地榜单快照。'
    if 'expecting value' in lowered and 'char 0' in lowered:
        return '官方接口暂时不可访问，已返回本地可用结果。'
    return text


def clean_text(value):
    if value is None:
        return ''
    return decrypt_pua(str(value)).strip()


def normalize_search_text(value):
    return re.sub(r'[\W_]+', '', decrypt_pua(str(value or '')).strip().lower())


def rank_search_results(query, results):
    needle = normalize_search_text(query)
    if not needle:
        return list(results)
    return [
        item for item in results
        if normalize_search_text(item.get('title')) == needle
    ]


def intish(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def bounded_int(value, default, minimum=None, maximum=None):
    number = intish(value, default)
    if minimum is not None:
        number = max(minimum, number)
    if maximum is not None:
        number = min(maximum, number)
    return number


def signed_fanqie_url(path, params):
    query = urlencode(params)
    a_bogus = generate_a_bogus(query, UA_WEB)
    return 'https://fanqienovel.com' + path + '?' + query + '&a_bogus=' + quote(a_bogus, safe='')


def fanqie_json_get(path, params, referer='https://fanqienovel.com/', timeout=8):
    url = signed_fanqie_url(path, params)
    body = http_get(url, UA_WEB, timeout=timeout, extra_headers={
        'Accept': 'application/json, text/plain, */*',
        'Referer': referer,
    })
    return json.loads(body), url


def fanqie_get_search_endpoint(query, query_type='1', filter_value='127,127,127,127', page_index=0, page_count=10, timeout=8):
    params = [
        ('filter', filter_value),
        ('page_count', str(page_count)),
        ('page_index', str(page_index)),
        ('query_type', str(query_type)),
        ('query_word', query),
    ]
    return fanqie_json_get('/api/author/search/search_book/v1', params, referer=f'https://fanqienovel.com/search/{quote(query, safe="")}', timeout=timeout)


def fanqie_get_reader_full(item_id, timeout=8):
    return fanqie_json_get('/api/reader/full', [('itemId', str(item_id))], referer=f'https://fanqienovel.com/reader/{item_id}', timeout=timeout)


def fanqie_get_search_page_html(query, timeout=8):
    return http_get(f'https://fanqienovel.com/search/{quote(query, safe="")}', UA_WEB, timeout=timeout, extra_headers={'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'})


def update_web_rankings(categories, error=''):
    global RANKING_GROUPS, RANKING_LIST
    RANKING_GROUPS = build_web_ranking_groups(categories or WEB_CATEGORY_FALLBACK)
    RANKING_LIST = [item for group in RANKING_GROUPS for item in group.get('items', [])]
    refresh_ranking_indexes()
    WEB_CATEGORY_CACHE['categories'] = categories or WEB_CATEGORY_FALLBACK
    WEB_CATEGORY_CACHE['fetched_at'] = now_iso()
    WEB_CATEGORY_CACHE['error'] = error


def fetch_web_categories(refresh=False):
    if WEB_CATEGORY_CACHE.get('fetched_at') and not refresh:
        return WEB_CATEGORY_CACHE
    try:
        data, _ = fanqie_json_get('/api/config/list', [('config_key', 'serial_rank_category_list_common')], timeout=6)
        if data.get('code') != 0:
            raise RuntimeError(data.get('message') or '分类配置接口返回失败')
        categories = []
        for item in data.get('data', {}).get('list', []):
            if not isinstance(item, dict):
                continue
            category_id = str(item.get('id') or '')
            name = clean_text(item.get('name') or category_id)
            groups = item.get('group') or item.get('groups') or []
            if isinstance(groups, str):
                groups = [groups]
            if category_id and name:
                categories.append({'id': category_id, 'name': name, 'groups': groups})
        if categories:
            update_web_rankings(categories)
            return WEB_CATEGORY_CACHE
        raise RuntimeError('分类配置接口没有返回分类')
    except Exception as exc:
        update_web_rankings(WEB_CATEGORY_FALLBACK, friendly_external_error(exc))
        return WEB_CATEGORY_CACHE


def normalize_rank_book(item, rank=0):
    if not isinstance(item, dict):
        return None
    book = item.get('book_data') if isinstance(item.get('book_data'), dict) else item
    book_id = str(book.get('bookId') or book.get('book_id') or book.get('id') or '')
    title = clean_text(book.get('bookName') or book.get('book_name') or book.get('title') or book.get('book_title'))
    if not book_id or not title:
        return None
    author = clean_text(book.get('author') or book.get('authorName') or book.get('author_name'))
    category = clean_text(book.get('category') or book.get('categoryName') or book.get('book_type') or book.get('categoryV2'))
    synopsis = clean_text(book.get('abstract') or book.get('description') or book.get('desc') or book.get('introduction'))
    cover = normalize_cover(str(book.get('thumbUri') or book.get('thumb_url') or book.get('cover') or book.get('cover_url') or ''))
    current_pos = intish(book.get('currentPos') or book.get('rank') or book.get('rankIdx'), rank)
    return {
        'id': book_id,
        'rank': current_pos or rank,
        'title': title,
        'author': author,
        'category': category,
        'synopsis': synopsis,
        'cover': cover,
        'score': clean_text(book.get('rank_score') or book.get('rankScore')),
        'read_count': str(book.get('read_count') or book.get('readCount') or ''),
        'word_count': str(book.get('wordNumber') or book.get('word_num') or book.get('word_count') or ''),
        'creation_status': str(book.get('creationStatus') or book.get('creation_status') or ''),
    }


def books_from_category_payload(payload, base_rank=1):
    data = payload.get('data', {}) if isinstance(payload, dict) else {}
    raw_books = []
    if isinstance(data, dict):
        raw_books = data.get('book_list') or data.get('bookList') or data.get('list') or []
    elif isinstance(data, list):
        raw_books = data
    books = []
    for idx, item in enumerate(raw_books if isinstance(raw_books, list) else [], base_rank):
        book = normalize_rank_book(item, idx)
        if book:
            books.append(book)
    total = intish(data.get('total_num') if isinstance(data, dict) else 0, len(books))
    return books, total, data if isinstance(data, dict) else {}


def existing_reader_har_paths():
    seen = set()
    paths = []
    for path in HAR_READER_PATHS:
        key = str(path)
        if key in seen or not path.exists():
            continue
        seen.add(key)
        paths.append(path)
    return paths


def load_reader_har_snapshot():
    global HAR_READER_SNAPSHOT
    if HAR_READER_SNAPSHOT is not None:
        return HAR_READER_SNAPSHOT
    snapshot = {'search': {}, 'chapters': {}, 'directories': {}, 'latest_updates': [], 'recommend': [], 'top_books': [], 'sources': [], 'errors': []}
    for har_path in existing_reader_har_paths():
        source = {'path': str(har_path), 'searches': 0, 'chapters': 0, 'directories': 0, 'error': ''}
        try:
            with har_path.open('r', encoding='utf-8', errors='replace') as f:
                har = json.load(f)
            for entry in har.get('log', {}).get('entries', []):
                req = entry.get('request', {})
                parsed = urlparse(req.get('url', ''))
                if parsed.netloc != 'fanqienovel.com':
                    continue
                text = entry.get('response', {}).get('content', {}).get('text', '')
                if not text:
                    continue
                qs = parse_qs(parsed.query)
                if parsed.path == '/api/rank/recent/update/list':
                    try:
                        payload = json.loads(text)
                    except Exception:
                        continue
                    data = payload.get('data', {}) if isinstance(payload, dict) else {}
                    rows = data.get('data') if isinstance(data, dict) else []
                    if isinstance(rows, list) and rows and not snapshot['latest_updates']:
                        for item in rows:
                            if not isinstance(item, dict):
                                continue
                            snapshot['latest_updates'].append({
                                'id': str(item.get('bookId') or item.get('book_id') or ''),
                                'chapter_id': str(item.get('itemId') or item.get('item_id') or ''),
                                'title': clean_text(item.get('bookName') or item.get('book_name')),
                                'chapter_title': clean_text(item.get('title') or item.get('chapterName')),
                                'author': clean_text(item.get('author')),
                                'category': clean_text(item.get('category')),
                                'update_time': str(item.get('updateTime') or ''),
                                'need_pay': item.get('needPay'),
                            })
                elif parsed.path == '/api/rank/recommend/list':
                    try:
                        payload = json.loads(text)
                    except Exception:
                        continue
                    data = payload.get('data', {}) if isinstance(payload, dict) else {}
                    rows = data.get('list') if isinstance(data, dict) else []
                    if isinstance(rows, list) and rows and not snapshot['recommend']:
                        snapshot['recommend'].extend([book for idx, item in enumerate(rows, 1) if (book := normalize_simple_book(item, idx))])
                elif parsed.path == '/api/author/misc/top_book_list/v1/':
                    try:
                        payload = json.loads(text)
                    except Exception:
                        continue
                    rows = payload.get('book_list') if isinstance(payload, dict) else []
                    if isinstance(rows, list) and rows and not snapshot['top_books']:
                        snapshot['top_books'].extend([book for idx, item in enumerate(rows, 1) if (book := normalize_simple_book(item, idx))])
                elif parsed.path == '/api/author/search/search_book/v1':
                    query = qs.get('query_word', [''])[0]
                    query_type = qs.get('query_type', ['0'])[0]
                    filter_value = qs.get('filter', ['127,127,127,127'])[0]
                    try:
                        payload = json.loads(text)
                    except Exception:
                        continue
                    raw = payload.get('data', {}).get('search_book_data_list') or []
                    results = []
                    for item in raw if isinstance(raw, list) else []:
                        if not isinstance(item, dict):
                            continue
                        book_id = str(item.get('book_id') or item.get('bookId') or item.get('id') or '')
                        title = item.get('book_name') or item.get('bookName') or item.get('title') or ''
                        if not book_id or not title:
                            continue
                        results.append({
                            'id': book_id,
                            'title': decrypt_pua(str(title)),
                            'author': decrypt_pua(str(item.get('author') or item.get('author_name') or '')),
                            'category': decrypt_pua(str(item.get('category') or '')),
                            'synopsis': decrypt_pua(str(item.get('book_abstract') or item.get('abstract') or '')),
                            'cover': normalize_cover(str(item.get('thumb_url') or item.get('thumbUri') or item.get('thumb_uri') or '')),
                            'read_count': str(item.get('read_count') or ''),
                            'word_count': str(item.get('word_count') or ''),
                            'creation_status': str(item.get('creation_status') or ''),
                            'last_chapter_title': decrypt_pua(str(item.get('last_chapter_title') or '')),
                        })
                    if results:
                        snapshot['search'][(query, query_type, filter_value)] = {
                            'results': results,
                            'total': intish(payload.get('data', {}).get('total_count'), len(results)),
                            'query_type': query_type,
                            'filter': filter_value,
                            'source': 'har-search-snapshot',
                        }
                        source['searches'] += 1
                elif parsed.path == '/api/reader/full':
                    item_id = qs.get('itemId', [''])[0]
                    if not item_id:
                        continue
                    try:
                        payload = json.loads(text)
                    except Exception:
                        continue
                    ch_data = payload.get('data', {}).get('chapterData', {}) if isinstance(payload, dict) else {}
                    raw = ch_data.get('content') or ''
                    if not isinstance(raw, str) or not raw:
                        continue
                    snapshot['chapters'][str(item_id)] = {
                        'id': str(item_id),
                        'title': decrypt_pua(str(ch_data.get('title') or '').strip()),
                        'content': decrypt_pua(strip_tags(raw)),
                        'source': 'har-reader-full-snapshot',
                    }
                    source['chapters'] += 1
                elif parsed.path == '/api/reader/directory/detail':
                    book_id = qs.get('bookId', [''])[0]
                    if not book_id:
                        continue
                    try:
                        payload = json.loads(text)
                    except Exception:
                        continue
                    data = payload.get('data', {}) if isinstance(payload, dict) else {}
                    snapshot['directories'][str(book_id)] = data
                    source['directories'] += 1
        except Exception as exc:
            source['error'] = friendly_external_error(exc)
            snapshot['errors'].append(f"{har_path}: {source['error']}")
        snapshot['sources'].append(source)
    HAR_READER_SNAPSHOT = snapshot
    return snapshot


def fetch_feed_snapshot(feed, offset=0, limit=20, kind='3'):
    snapshot = load_reader_har_snapshot()
    rows = snapshot.get(feed, [])
    offset = int(bounded_int(offset, 0, minimum=0))
    limit = int(bounded_int(limit, 20, minimum=1, maximum=500))
    sliced = rows[offset:offset + limit]
    if feed == 'latest_updates':
        return {'updates': sliced, 'count': len(sliced), 'total': len(rows), 'source': 'har-feed-snapshot'}
    if feed == 'recommend':
        return {'type': str(kind), 'books': sliced, 'count': len(sliced), 'total': len(rows), 'source': 'har-feed-snapshot'}
    if feed == 'top_books':
        return {'books': sliced, 'count': len(sliced), 'source': 'har-feed-snapshot'}
    return None


def fetch_search_snapshot(query, query_type='1', filter_value='127,127,127,127', page_index=0, page_count=10):
    snapshot = load_reader_har_snapshot()
    row = snapshot.get('search', {}).get((str(query), str(query_type), str(filter_value)))
    if not row:
        return None
    page_index = int(bounded_int(page_index, 0, minimum=0))
    page_count = int(bounded_int(page_count, 10, minimum=1, maximum=100))
    start = page_index * page_count
    end = start + page_count
    results = row.get('results', [])
    return {**row, 'results': results[start:end], 'snapshot_total': row.get('total', 0)}


def existing_har_paths():
    seen = set()
    paths = []
    for path in HAR_RANK_PATHS:
        key = str(path)
        if key in seen or not path.exists():
            continue
        seen.add(key)
        paths.append(path)
    return paths


def merge_snapshot_books(snapshot, key, books, total, source_path):
    if not books:
        return
    bucket = snapshot.setdefault(key, {'books': [], 'total': 0, 'sources': []})
    bucket['total'] = max(intish(bucket.get('total'), 0), intish(total, 0), len(books))
    if source_path and source_path not in bucket['sources']:
        bucket['sources'].append(source_path)
    bucket['books'].extend(books)


def load_worker_rank_snapshot(snapshot, errors, sources):
    source = {'path': str(WORKER_DATA_PATH), 'rank_requests': 0, 'books': 0, 'error': ''}
    if not WORKER_DATA_PATH.exists():
        source['error'] = '未找到 Worker 快照。'
        sources.append(source)
        return
    try:
        text = WORKER_DATA_PATH.read_text(encoding='utf-8', errors='replace').strip()
        prefix = 'export const DATA = '
        if text.startswith(prefix):
            text = text[len(prefix):]
        if text.endswith(';'):
            text = text[:-1]
        data = json.loads(text)
        rank_snapshot = data.get('rankSnapshot') or {}
        for raw_key, bucket in rank_snapshot.items():
            parts = str(raw_key).split('|')
            if len(parts) != 3 or not isinstance(bucket, dict):
                continue
            books = [book for book in bucket.get('books', []) if isinstance(book, dict)]
            if not books:
                continue
            source['rank_requests'] += 1
            source['books'] += len(books)
            merge_snapshot_books(snapshot, tuple(parts), books, bucket.get('total'), str(WORKER_DATA_PATH))
    except Exception as exc:
        source['error'] = friendly_external_error(exc)
        errors.append(f"{WORKER_DATA_PATH}: {source['error']}")
    sources.append(source)


def load_har_rank_snapshot():
    global HAR_RANK_SNAPSHOT, HAR_RANK_ERROR, HAR_RANK_SOURCES
    if HAR_RANK_SNAPSHOT is not None:
        return HAR_RANK_SNAPSHOT
    snapshot = {}
    errors = []
    sources = []
    load_worker_rank_snapshot(snapshot, errors, sources)
    har_paths = existing_har_paths()
    for har_path in har_paths:
        source = {'path': str(har_path), 'rank_requests': 0, 'books': 0, 'error': ''}
        try:
            with har_path.open('r', encoding='utf-8', errors='replace') as f:
                har = json.load(f)
            for entry in har.get('log', {}).get('entries', []):
                request = entry.get('request', {})
                parsed = urlparse(request.get('url', ''))
                if parsed.netloc != 'fanqienovel.com' or parsed.path != '/api/rank/category/list':
                    continue
                qs = parse_qs(parsed.query)
                key = (qs.get('gender', [''])[0], qs.get('rankMold', [''])[0], qs.get('category_id', [''])[0])
                if not all(key):
                    continue
                source['rank_requests'] += 1
                offset = intish(qs.get('offset', ['0'])[0], 0)
                text = entry.get('response', {}).get('content', {}).get('text', '')
                if not text:
                    continue
                try:
                    payload = json.loads(text)
                except Exception:
                    continue
                books, total, _ = books_from_category_payload(payload, offset + 1)
                if not books:
                    continue
                source['books'] += len(books)
                merge_snapshot_books(snapshot, key, books, max(total, offset + len(books)), str(har_path))
        except Exception as exc:
            source['error'] = friendly_external_error(exc)
            errors.append(f"{har_path}: {source['error']}")
        sources.append(source)
    for bucket in snapshot.values():
        seen = set()
        deduped = []
        for book in sorted(bucket['books'], key=lambda row: intish(row.get('rank'), 999999)):
            if book['id'] in seen:
                continue
            seen.add(book['id'])
            deduped.append(book)
        bucket['books'] = deduped
    if not snapshot and not errors:
        errors.append('未找到可用排行榜快照。')
    HAR_RANK_ERROR = '; '.join(errors)
    HAR_RANK_SOURCES = sources
    HAR_RANK_SNAPSHOT = snapshot
    return snapshot


def build_capture_summary():
    snapshot = load_har_rank_snapshot()
    reader_snapshot = load_reader_har_snapshot()
    return {
        'source_paths': [str(WORKER_DATA_PATH)] + [str(path) for path in HAR_RANK_PATHS + HAR_READER_PATHS],
        'loaded_sources': HAR_RANK_SOURCES,
        'ranking_keys': len(snapshot),
        'ranking_books': sum(len(bucket.get('books', [])) for bucket in snapshot.values()),
        'reader_sources': reader_snapshot.get('sources', []),
        'search_snapshots': len(reader_snapshot.get('search', {})),
        'chapter_snapshots': len(reader_snapshot.get('chapters', {})),
        'directory_snapshots': len(reader_snapshot.get('directories', {})),
        'latest_update_snapshots': len(reader_snapshot.get('latest_updates', [])),
        'recommend_snapshots': len(reader_snapshot.get('recommend', [])),
        'top_book_snapshots': len(reader_snapshot.get('top_books', [])),
        'rank_api': '/api/rank/category/list',
        'search_api': '/api/author/search/search_book/v1',
        'reader_api': '/api/reader/full',
        'directory_api': '/api/reader/directory/detail',
        'latest_api': '/api/rank/recent/update/list',
        'recommend_api': '/api/rank/recommend/list',
        'top_books_api': '/api/author/misc/top_book_list/v1/',
        'captured_at': '2026-05-24T18:51:13+08:00',
        'error': HAR_RANK_ERROR,
    }


def fetch_har_category_books(meta, offset, limit):
    snapshot = load_har_rank_snapshot()
    key = (str(meta.get('gender') or ''), str(meta.get('rankMold') or ''), str(meta.get('category_id') or ''))
    bucket = snapshot.get(key, {})
    books = list(bucket.get('books', []))
    return books[offset:offset + limit], intish(bucket.get('total'), len(books))


def fetch_live_category_books(meta, offset, limit):
    books = []
    total = 0
    rank_version = str(meta.get('rank_version') or '')
    cursor = offset
    remaining = limit
    source_url = ''
    while remaining > 0:
        page_limit = min(10, remaining)
        params = [
            ('app_id', '2503'),
            ('rank_list_type', str(meta.get('rank_list_type') or 3)),
            ('offset', str(cursor)),
            ('limit', str(page_limit)),
            ('category_id', str(meta.get('category_id'))),
            ('rank_version', rank_version),
            ('gender', str(meta.get('gender'))),
            ('rankMold', str(meta.get('rankMold'))),
        ]
        referer = f"https://fanqienovel.com/rank/{meta.get('gender')}_{meta.get('rankMold')}_{meta.get('category_id')}"
        payload, source_url = fanqie_json_get('/api/rank/category/list', params, referer=referer, timeout=4)
        if payload.get('code') != 0:
            raise RuntimeError(payload.get('message') or '排行榜接口返回失败')
        page_books, page_total, data = books_from_category_payload(payload, cursor + 1)
        total = max(total, page_total)
        rank_version = str(data.get('rankVersion') or rank_version)
        if not page_books:
            raise RuntimeError('排行榜接口返回空列表')
        books.extend(page_books)
        cursor += page_limit
        remaining -= page_limit
        if len(page_books) < page_limit:
            break
    return books[:limit], total or len(books), source_url

def ranking_snapshot_key(item):
    return (str(item.get('gender') or ''), str(item.get('rankMold') or ''), str(item.get('category_id') or ''))


def snapshot_book_count(item):
    bucket = load_har_rank_snapshot().get(ranking_snapshot_key(item), {})
    return len(bucket.get('books', []))


def public_ranking_item(item):
    snapshot_books = snapshot_book_count(item)
    return {
        'id': item.get('id', ''),
        'name': item.get('display_name') or item.get('name', ''),
        'category_name': item.get('category_name') or item.get('name', ''),
        'section': item.get('section', ''),
        'available': True,
        'source_api': item.get('source_api', ''),
        'gender': item.get('gender'),
        'rankMold': item.get('rankMold'),
        'category_id': item.get('category_id'),
        'rank_list_type': item.get('rank_list_type'),
        'snapshot_books': snapshot_books,
    }


def fixed_ranking_groups():
    groups = []
    for group in RANKING_GROUPS:
        items = [public_ranking_item(item) for item in group.get('items', [])]
        items.sort(key=lambda item: (item.get('snapshot_books', 0) == 0, item.get('category_name') or item.get('name') or ''))
        groups.append({'title': group['title'], 'items': items})
    return groups


def normalize_ranking_id(ranking_id=None):
    raw = str(ranking_id or (RANKING_LIST[0]['id'] if RANKING_LIST else ''))
    if raw in RANKING_BY_ID:
        return raw
    if raw in RANKING_ALIAS:
        return RANKING_ALIAS[raw]
    if raw in RANKING_BY_NAME:
        return RANKING_BY_NAME[raw]['id']
    return raw


def ranking_meta(ranking_id=None):
    normalized = normalize_ranking_id(ranking_id)
    return RANKING_BY_ID.get(normalized)


def flatten_rankings(groups=None):
    rows = []
    source_groups = groups or fixed_ranking_groups()
    for group in source_groups:
        for item in group.get('items', []):
            rows.append({
                **item,
                'group': group.get('title', ''),
                'cached_books': len(RANKING_CACHE.get(item.get('id', ''), {}).get('books', [])),
            })
    return rows


def fetch_leaderboards(refresh=False):
    category_state = fetch_web_categories(refresh)
    groups = fixed_ranking_groups()
    return {
        'source': 'fanqie-web-rank-category-list',
        'snapshot_date': now_iso(),
        'count': len(RANKING_LIST),
        'groups': groups,
        'rankings': [item for group in groups for item in group.get('items', [])],
        'error': category_state.get('error', ''),
    }


def unavailable_ranking_response(ranking_id, error=''):
    meta = ranking_meta(ranking_id)
    name = meta.get('display_name') or meta.get('name') if meta else str(ranking_id or '')
    normalized = meta.get('id') if meta else normalize_ranking_id(ranking_id)
    return {
        'ranking_id': normalized,
        'ranking_name': name,
        'count': 0,
        'books': [],
        'source': 'fanqie-web-rank-category-list',
        'error': error or '未知榜单。',
    }


def fetch_ranking_books(ranking_id=None, offset=0, limit=30):
    fetch_web_categories(False)
    if not ranking_id:
        ranking_id = RANKING_LIST[0]['id'] if RANKING_LIST else ''
    meta = ranking_meta(ranking_id)
    if not meta:
        return unavailable_ranking_response(ranking_id, '未知榜单。')

    offset = bounded_int(offset, 0, minimum=0)
    limit = bounded_int(limit, 30, minimum=1, maximum=100)
    normalized = meta['id']
    error = ''
    source_url = ''
    source = 'fanqie-web-rank-category-list'
    try:
        books, total, source_url = fetch_live_category_books(meta, offset, limit)
    except Exception as exc:
        error = friendly_external_error(exc)
        books, total = fetch_har_category_books(meta, offset, limit)
        if books:
            source = 'local-rank-snapshot'
        else:
            cached = RANKING_CACHE.get(normalized, {})
            cached_books = list(cached.get('books', []))
            books = cached_books[offset:offset + limit]
            total = intish(cached.get('total'), len(cached_books))
            source = 'memory-cache' if books else 'fanqie-web-rank-category-list'
    if books:
        RANKING_CACHE[normalized] = {'books': books, 'total': total, 'fetched_at': now_iso(), 'source': source}
    return {
        'ranking_id': normalized,
        'ranking_name': meta.get('display_name') or meta.get('name'),
        'category_id': meta.get('category_id'),
        'gender': meta.get('gender'),
        'rankMold': meta.get('rankMold'),
        'source_api': meta.get('source_api'),
        'count': len(books),
        'total': total,
        'books': books,
        'source': source,
        'source_url': source_url,
        'error': error if not books else '',
    }


def normalize_simple_book(item, rank=0):
    if not isinstance(item, dict):
        return None
    book_id = str(item.get('bookId') or item.get('book_id') or item.get('id') or '')
    title = clean_text(item.get('bookName') or item.get('book_name') or item.get('title') or item.get('book_title'))
    if not book_id or not title:
        return None
    return {
        'id': book_id,
        'rank': intish(item.get('rank') or item.get('rankIdx'), rank) or rank,
        'title': title,
        'author': clean_text(item.get('author') or item.get('authorName') or item.get('author_name')),
        'category': clean_text(item.get('category') or item.get('categoryName') or item.get('book_type') or item.get('categoryV2')),
        'synopsis': clean_text(item.get('abstract') or item.get('book_abstract') or item.get('description') or item.get('desc')),
        'cover': normalize_cover(str(item.get('thumbUri') or item.get('thumb_uri') or item.get('thumb_url') or item.get('cover') or item.get('cover_url') or '')),
        'score': clean_text(item.get('rank_score') or item.get('rankScore')),
        'read_count': str(item.get('read_count') or item.get('readCount') or ''),
        'word_count': str(item.get('wordNumber') or item.get('word_num') or item.get('word_count') or ''),
        'creation_status': str(item.get('creationStatus') or item.get('creation_status') or ''),
    }


def fetch_recent_updates(offset=0, limit=20):
    offset = bounded_int(offset, 0, minimum=0)
    limit = bounded_int(limit, 20, minimum=1, maximum=100)
    try:
        payload, source_url = fanqie_json_get('/api/rank/recent/update/list', [('offset', str(offset)), ('limit', str(limit))], timeout=8)
    except Exception:
        return fetch_feed_snapshot('latest_updates', offset, limit)
    data = payload.get('data') if isinstance(payload, dict) else {}
    rows = data.get('data') if isinstance(data, dict) else []
    updates = []
    for item in rows if isinstance(rows, list) else []:
        updates.append({
            'id': str(item.get('bookId') or item.get('book_id') or ''),
            'chapter_id': str(item.get('itemId') or item.get('item_id') or ''),
            'title': clean_text(item.get('bookName') or item.get('book_name')),
            'chapter_title': clean_text(item.get('title') or item.get('chapterName')),
            'author': clean_text(item.get('author')),
            'category': clean_text(item.get('category')),
            'update_time': str(item.get('updateTime') or ''),
            'need_pay': item.get('needPay'),
        })
    return {'updates': updates, 'count': len(updates), 'total': intish(data.get('total') if isinstance(data, dict) else 0, len(updates)), 'source_url': source_url}


def fetch_recommend_books(kind='3', offset=0, limit=10):
    offset = bounded_int(offset, 0, minimum=0)
    limit = bounded_int(limit, 10, minimum=1, maximum=100)
    try:
        payload, source_url = fanqie_json_get('/api/rank/recommend/list', [('type', str(kind)), ('offset', str(offset)), ('limit', str(limit))], timeout=8)
    except Exception:
        return fetch_feed_snapshot('recommend', offset, limit, kind)
    data = payload.get('data') if isinstance(payload, dict) else {}
    rows = data.get('list') if isinstance(data, dict) else []
    books = [book for idx, item in enumerate(rows if isinstance(rows, list) else [], offset + 1) if (book := normalize_simple_book(item, idx))]
    return {'type': str(kind), 'books': books, 'count': len(books), 'total': intish(data.get('total') if isinstance(data, dict) else 0, len(books)), 'source_url': source_url}


def fetch_top_books(offset=0, limit=200):
    offset = bounded_int(offset, 0, minimum=0)
    limit = bounded_int(limit, 200, minimum=1, maximum=500)
    try:
        payload, source_url = fanqie_json_get('/api/author/misc/top_book_list/v1/', [('offset', str(offset)), ('limit', str(limit))], timeout=8)
    except Exception:
        return fetch_feed_snapshot('top_books', offset, limit)
    rows = payload.get('book_list') if isinstance(payload, dict) else []
    rows = rows if isinstance(rows, list) else []
    books = [book for idx, item in enumerate(rows[:limit], offset + 1) if (book := normalize_simple_book(item, idx))]
    return {'books': books, 'count': len(books), 'source_url': source_url}


def fetch_search_filters():
    return {
        'query_types': [
            {'id': '1', 'name': '书名'},
        ],
        'filter_format': '固定书名搜索，不再提供热度筛选。',
        'captured_filters': [
            '127,127,127,127',
        ],
        'feeds': {
            'latest_updates': '/api/latest-updates?offset=0&limit=20',
            'recommend': '/api/recommend?type=3&offset=0&limit=10',
            'hot_books': '/api/top-books?offset=0&limit=200',
        },
    }


def fetch_search(query, query_type='1', filter_value='127,127,127,127', page_index=0, page_count=10):
    query = str(query or '').strip()
    query_type = str(query_type or '1')
    filter_value = str(filter_value or '127,127,127,127')
    page_index = int(bounded_int(page_index, 0, minimum=0))
    page_count = int(bounded_int(page_count, 10, minimum=1, maximum=100))
    if not query:
        return {'results': [], 'query_type': query_type, 'filter': filter_value}
    live_error = None
    try:
        data, _ = fanqie_get_search_endpoint(query, query_type=query_type, filter_value=filter_value, page_index=page_index, page_count=page_count, timeout=3)
        raw = data.get('data', {}).get('search_book_data_list') or []
        results = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            book_id = str(item.get('book_id') or item.get('bookId') or item.get('id') or '')
            title = item.get('book_name') or item.get('bookName') or item.get('title') or ''
            author = item.get('author') or item.get('author_name') or ''
            if book_id and title:
                results.append({
                    'id': book_id,
                    'title': decrypt_pua(str(title)),
                    'author': decrypt_pua(str(author)),
                    'category': decrypt_pua(str(item.get('category') or '')),
                    'synopsis': decrypt_pua(str(item.get('book_abstract') or item.get('abstract') or '')),
                    'cover': normalize_cover(str(item.get('thumb_url') or item.get('thumbUri') or item.get('thumb_uri') or '')),
                    'read_count': str(item.get('read_count') or ''),
                    'word_count': str(item.get('word_count') or ''),
                    'creation_status': str(item.get('creation_status') or ''),
                    'last_chapter_title': decrypt_pua(str(item.get('last_chapter_title') or '')),
                })
        results = rank_search_results(query, results)
        if results:
            return {'results': results[:page_count], 'total': intish(data.get('data', {}).get('total_count'), len(results)), 'query_type': query_type, 'filter': filter_value, 'source': 'fanqie-web-search-book'}
    except Exception as exc:
        live_error = friendly_external_error(exc)
    snapshot_result = fetch_search_snapshot(query, query_type, filter_value, page_index, page_count)
    if snapshot_result:
        snapshot_results = rank_search_results(query, snapshot_result.get('results', []))
        if snapshot_results:
            limited = snapshot_results[:page_count]
            return {**snapshot_result, 'results': limited, 'count': len(limited), 'query_type': query_type, 'filter': filter_value}
    if live_error:
        return {'results': [], 'query_type': query_type, 'filter': filter_value, 'error': live_error}
    try:
        html = fanqie_get_search_page_html(query, timeout=3)
    except Exception as exc:
        return {'results': [], 'query_type': query_type, 'filter': filter_value, 'error': friendly_external_error(exc)}
    state = parse_initial_state(html)
    results = []
    if state:
        for cur in walk_objects(state):
            if not isinstance(cur, dict):
                continue
            book_id = str(cur.get('bookId') or cur.get('book_id') or cur.get('id') or '')
            title = cur.get('bookName') or cur.get('book_name') or cur.get('title') or ''
            if book_id and title:
                results.append({
                    'id': book_id,
                    'title': decrypt_pua(str(title)),
                    'author': decrypt_pua(str(cur.get('author') or cur.get('authorName') or cur.get('author_name') or '')),
                })
    results = rank_search_results(query, results)
    if not results:
        return {'results': [], 'query_type': query_type, 'filter': filter_value, 'fallback': 'search-html'}
    return {'results': results[:page_count], 'query_type': query_type, 'filter': filter_value, 'fallback': 'search-html'}


def fetch_book_detail(book_id):
    if book_id in DETAIL_CACHE:
        return DETAIL_CACHE[book_id]
    html = http_get(f'https://fanqienovel.com/page/{book_id}', UA_WEB)
    state = parse_initial_state(html)
    detail = {'id': str(book_id), 'title': '', 'author': '', 'description': '', 'status': '', 'tags': '', 'total_chapters_source': 0, 'chapters_in_db': 0, 'last_crawled_at': now_iso(), 'created_at': now_iso(), 'cover_image_url': ''}
    if state:
        candidates = []
        stack = [state]
        while stack:
            cur = stack.pop()
            if isinstance(cur, dict):
                if any(k in cur for k in ('bookName', 'book_name', 'bookId', 'book_id')):
                    candidates.append(cur)
                stack.extend(cur.values())
            elif isinstance(cur, list):
                stack.extend(cur)
        for cur in candidates:
            title = cur.get('bookName') or cur.get('book_name') or cur.get('title')
            if title:
                detail['title'] = decrypt_pua(str(title))
                detail['author'] = decrypt_pua(str(cur.get('author') or cur.get('authorName') or cur.get('author_name') or ''))
                detail['description'] = decrypt_pua(str(cur.get('abstract') or cur.get('description') or cur.get('desc') or ''))
                detail['status'] = str(cur.get('creationStatus') or cur.get('status') or '')
                tags = cur.get('tags') or cur.get('categoryV2') or cur.get('category') or ''
                detail['tags'] = '|'.join(tags) if isinstance(tags, list) else str(tags)
                detail['cover_image_url'] = normalize_cover(str(cur.get('thumbUri') or cur.get('cover') or cur.get('cover_url') or ''))
                break
    if not detail['title']:
        title_m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
        detail['title'] = decrypt_pua(strip_tags(title_m.group(1))) if title_m else f'Book {book_id}'
    html_chapters = extract_chapters_from_html(html)
    chapters = fetch_full_chapters(book_id, html_chapters)
    detail['chapters_in_db'] = len(chapters)
    detail['total_chapters_source'] = len(chapters)
    detail['chapters'] = chapters
    DETAIL_CACHE[book_id] = detail
    SHELF[book_id] = detail
    return detail


def extract_chapters_from_html(html):
    chapters = []
    for m in re.finditer(r'<a[^>]*href="/reader/(\d+)"[^>]*>(.*?)</a>', html, re.S):
        title = decrypt_pua(strip_tags(m.group(2)))
        chapters.append({'id': m.group(1), 'index': len(chapters) + 1, 'title': title, 'is_free': True, 'fetched_at': now_iso()})
    seen = set()
    deduped = []
    for ch in chapters:
        if ch['id'] not in seen:
            seen.add(ch['id'])
            deduped.append(ch)
    return deduped


def fetch_chapters(book_id, allow_empty=False):
    try:
        payload, _ = fanqie_json_get('/api/reader/directory/detail', [('bookId', str(book_id))], referer=f'https://fanqienovel.com/page/{book_id}', timeout=8)
        data = payload.get('data', {}) if isinstance(payload, dict) else {}
    except Exception:
        body = http_get(f'https://fanqienovel.com/api/reader/directory/detail?bookId={book_id}', UA_WEB)
        data = json.loads(body).get('data', {})
    items = data.get('chapterListWithVolume') or data.get('list') or data.get('item_list') or data.get('allItemIds') or []
    flat = []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, list):
            flat.extend(item)
        elif isinstance(item, dict) and isinstance(item.get('itemList'), list):
            flat.extend(item.get('itemList'))
        else:
            flat.append(item)
    chapters = []
    for i, item in enumerate(flat):
        if isinstance(item, dict):
            cid = str(item.get('itemId') or item.get('item_id') or item.get('id') or '')
            title = item.get('title') or item.get('chapterName') or f'第{i+1}章'
            need_pay = item.get('needPay') if isinstance(item.get('needPay'), int) else item.get('need_pay', 1)
            is_paid_story = item.get('isPaidStory', True)
            is_free = (need_pay == 0 and not is_paid_story)
        else:
            cid = str(item)
            title = f'第{i+1}章'
            is_free = True
        if cid:
            chapters.append({'id': cid, 'index': len(chapters) + 1, 'title': decrypt_pua(str(title)), 'is_free': is_free, 'fetched_at': now_iso()})
    if not chapters:
        snapshot_data = load_reader_har_snapshot().get('directories', {}).get(str(book_id), {})
        snapshot_items = snapshot_data.get('chapterListWithVolume') or snapshot_data.get('list') or snapshot_data.get('item_list') or snapshot_data.get('allItemIds') or []
        snapshot_flat = []
        for item in snapshot_items if isinstance(snapshot_items, list) else []:
            if isinstance(item, list):
                snapshot_flat.extend(item)
            elif isinstance(item, dict) and isinstance(item.get('itemList'), list):
                snapshot_flat.extend(item.get('itemList'))
            else:
                snapshot_flat.append(item)
        for i, item in enumerate(snapshot_flat):
            if isinstance(item, dict):
                cid = str(item.get('itemId') or item.get('item_id') or item.get('id') or '')
                title = item.get('title') or item.get('chapterName') or f'第{i+1}章'
                need_pay = item.get('needPay') if isinstance(item.get('needPay'), int) else item.get('need_pay', 1)
                is_paid_story = item.get('isPaidStory', True)
                is_free = (need_pay == 0 and not is_paid_story)
            else:
                cid = str(item)
                title = f'第{i+1}章'
                is_free = True
            if cid:
                chapters.append({'id': cid, 'index': len(chapters) + 1, 'title': decrypt_pua(str(title)), 'is_free': is_free, 'fetched_at': now_iso(), 'source': 'har-directory-snapshot'})
    if not chapters and not allow_empty:
        raise RuntimeError('未获取到章节目录；页面结构变化或接口暂不可用。')
    return chapters



def merge_chapters(*sources):
    merged = []
    seen = set()
    for source in sources:
        for ch in source or []:
            if not isinstance(ch, dict):
                continue
            cid = str(ch.get('id') or ch.get('chapter_id') or '')
            if not cid or cid in seen:
                continue
            item = dict(ch)
            item['id'] = cid
            item['index'] = len(merged) + 1
            item['title'] = decrypt_pua(str(item.get('title') or f"第{item['index']}章"))
            item.setdefault('is_free', True)
            item.setdefault('fetched_at', now_iso())
            merged.append(item)
            seen.add(cid)
    return merged


def fetch_full_chapters(book_id, fallback=None):
    try:
        live_chapters = fetch_chapters(book_id, allow_empty=True)
    except Exception:
        live_chapters = []
    return merge_chapters(live_chapters, fallback or [])

def fetch_chapter_content(chapter_id, timeout=8):
    if chapter_id in CHAPTER_CACHE:
        return CHAPTER_CACHE[chapter_id]
    try:
        payload, _ = fanqie_get_reader_full(chapter_id, timeout=timeout)
        ch_data = payload.get('data', {}).get('chapterData', {}) if isinstance(payload, dict) else {}
        title = str(ch_data.get('title') or '').strip()
        raw = ch_data.get('content') or ''
        if not isinstance(raw, str):
            raw = ''
        content = decrypt_pua(strip_tags(raw))
        if content:
            result = {'id': str(chapter_id), 'title': decrypt_pua(title), 'content': content}
            CHAPTER_CACHE[chapter_id] = result
            return result
    except Exception:
        snapshot_chapter = load_reader_har_snapshot().get('chapters', {}).get(str(chapter_id))
        if snapshot_chapter:
            CHAPTER_CACHE[chapter_id] = snapshot_chapter
            return snapshot_chapter
    html = http_get(f'https://fanqienovel.com/reader/{chapter_id}', UA_WEB, timeout=timeout)
    state = parse_initial_state(html)
    if not state:
        raise RuntimeError('未解析到章节初始状态；页面结构变化或接口暂不可用。')
    reader = state.get('reader', {}) if isinstance(state, dict) else {}
    ch_data = reader.get('chapterData', {}) if isinstance(reader, dict) else {}
    title = str(ch_data.get('title') or '').strip()
    raw = ch_data.get('content') or ''
    if not isinstance(raw, str):
        raw = ''
    content = decrypt_pua(strip_tags(raw))
    result = {'id': str(chapter_id), 'title': decrypt_pua(title), 'content': content}
    CHAPTER_CACHE[chapter_id] = result
    return result



def build_suite_stats():
    fetch_web_categories(False)
    return {
        'generated_at': now_iso(),
        'anonymous': True,
        'login_removed': True,
        'features': SUITE_FEATURES,
        'ranking_groups': len(RANKING_GROUPS),
        'ranking_categories': len(WEB_CATEGORY_CACHE.get('categories') or WEB_CATEGORY_FALLBACK),
        'ranking_count': len(RANKING_LIST),
        'shelf_total': len(SHELF),
        'detail_cache_total': len(DETAIL_CACHE),
        'chapter_cache_total': len(CHAPTER_CACHE),
        'interfaces_same': False,
    }


def build_interface_map():
    return {
        'same': False,
        'summary': '本地合并版使用当前番茄网页版排行榜分类接口和无登录阅读器。',
        'login': '已移除。没有 /login、/register、JWT、用户表或会话依赖。',
        'features': SUITE_FEATURES,
        'capture': build_capture_summary(),
        'canonical': {
            'capture_summary': '/api/capture-summary',
            'rankings': '/api/rankings',
            'ranking_books': '/api/ranking?ranking_id=<web榜单ID>',
            'search_filters': '/api/search-filters',
            'search': '/api/search?query=关键词&query_type=0&filter=127,127,127,127',
            'latest_updates': '/api/latest-updates?offset=0&limit=20',
            'recommend': '/api/recommend?type=3&offset=0&limit=10',
            'hot_books': '/api/top-books?offset=0&limit=200',
            'book_detail': '/api/novels/<book_id>',
            'chapters': '/api/novels/<book_id>/chapters',
            'chapter_content': '/api/novels/<book_id>/chapters/<chapter_id>',
            'download_txt': '/api/novels/<book_id>/download',
        },
        'mcp_aliases': {
            'list_rankings': '/api/mcp/list_rankings',
            'get_ranking': '/api/mcp/get_ranking?ranking_id=<web榜单ID>&offset=0&limit=30',
            'get_book_detail': '/api/mcp/get_book_detail?book_id=<book_id>',
            'get_chapter_content': '/api/mcp/get_chapter_content?chapter_id=<chapter_id>',
        },
    }


def boolish(value):
    return str(value).lower() in ('1', 'true', 'yes', 'on')



class Handler(BaseHTTPRequestHandler):
    server_version = 'FanqieNovelSuiteReal/1.0'

    def log_message(self, fmt, *args):
        print(f'[{datetime.now().strftime("%H:%M:%S")}] {self.address_string()} {fmt % args}')

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def send_file(self, path):
        if not path.exists() or not path.is_file():
            return self.send_json({'error': 'not found'}, 404)
        body = path.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', mimetypes.guess_type(str(path))[0] or 'application/octet-stream')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_static(self, request_path):
        root = STATIC.resolve()
        relative = unquote(request_path.removeprefix('/static/')).lstrip('/')
        target = (root / relative).resolve()
        if target != root and root not in target.parents:
            return self.send_json({'error': 'not found'}, 404)
        return self.send_file(target)

    def read_json(self):
        size = intish(self.headers.get('Content-Length', '0'), 0)
        if size <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(size).decode('utf-8') or '{}')
        except json.JSONDecodeError as exc:
            raise ValueError(f'Invalid JSON body: {exc.msg}') from exc

    def fail(self, exc, status=502):
        return self.send_json({'error': friendly_external_error(exc)}, status)

    def do_GET(self):
        parsed = urlparse(self.path)
        path, qs = parsed.path, parse_qs(parsed.query)
        try:
            if path == '/':
                return self.send_file(STATIC / 'index.html')
            if path.startswith('/static/'):
                return self.send_static(path)
            if path == '/api/health':
                return self.send_json({'ok': True, 'mode': 'real-anonymous-merged', 'time': now_iso(), 'login_removed': True, 'features': [f['source'] for f in SUITE_FEATURES], 'capture_loaded': bool(load_har_rank_snapshot())})
            if path == '/api/interfaces':
                return self.send_json(build_interface_map())
            if path == '/api/capture-summary':
                return self.send_json(build_capture_summary())
            if path == '/api/stats':
                return self.send_json(build_suite_stats())
            if path == '/api/search-filters':
                return self.send_json(fetch_search_filters())
            if path == '/api/latest-updates':
                return self.send_json(fetch_recent_updates(qs.get('offset', ['0'])[0], qs.get('limit', ['20'])[0]))
            if path == '/api/recommend':
                return self.send_json(fetch_recommend_books(qs.get('type', ['3'])[0], qs.get('offset', ['0'])[0], qs.get('limit', ['10'])[0]))
            if path == '/api/top-books':
                return self.send_json(fetch_top_books(qs.get('offset', ['0'])[0], qs.get('limit', ['200'])[0]))
            if path == '/api/rankings':
                return self.send_json(fetch_leaderboards(qs.get('refresh', ['0'])[0] == '1'))
            if path == '/api/ranking':
                try:
                    return self.send_json(fetch_ranking_books(qs.get('ranking_id', [''])[0], qs.get('offset', ['0'])[0], qs.get('limit', ['30'])[0]))
                except Exception as exc:
                    return self.fail(exc, 504)
            if path == '/api/mcp/list_rankings':
                return self.send_json(fetch_leaderboards(boolish(qs.get('refresh', ['0'])[0])))
            if path == '/api/mcp/get_ranking':
                try:
                    return self.send_json(fetch_ranking_books(qs.get('ranking_id', [''])[0], qs.get('offset', ['0'])[0], qs.get('limit', ['30'])[0]))
                except Exception as exc:
                    return self.fail(exc, 504)
            if path == '/api/mcp/get_book_detail':
                book_id = qs.get('book_id', qs.get('id', ['']))[0]
                if not book_id:
                    return self.send_json({'error': 'Missing book_id'}, 400)
                return self.send_json(fetch_book_detail(book_id))
            if path == '/api/mcp/get_chapter_content':
                chapter_id = qs.get('chapter_id', qs.get('id', ['']))[0]
                if not chapter_id:
                    return self.send_json({'error': 'Missing chapter_id'}, 400)
                return self.send_json(fetch_chapter_content(chapter_id))
            if path == '/api/search':
                return self.send_json(fetch_search(qs.get('query', [''])[0], qs.get('query_type', ['1'])[0], qs.get('filter', ['127,127,127,127'])[0], qs.get('page_index', ['0'])[0], qs.get('page_count', ['10'])[0]))
            if path == '/api/novels':
                return self.send_json({'novels': list(SHELF.values()), 'total': len(SHELF), 'page': 1, 'pages': 1, 'per_page': 50})
            m = re.match(r'^/api/novels/(\d+)$', path)
            if m:
                return self.send_json(fetch_book_detail(m.group(1)))
            m = re.match(r'^/api/novels/(\d+)/chapters$', path)
            if m:
                detail = fetch_book_detail(m.group(1))
                chapters = fetch_full_chapters(m.group(1), detail.get('chapters', []))
                return self.send_json({'chapters': chapters, 'total': len(chapters), 'page': 1, 'pages': 1, 'per_page': len(chapters) or 1, 'novel_id': m.group(1)})
            m = re.match(r'^/api/novels/(\d+)/chapters/(\d+)$', path)
            if m:
                chapter = fetch_chapter_content(m.group(2))
                chapter['novel_id'] = m.group(1)
                return self.send_json(chapter)
            m = re.match(r'^/api/chapters/(\d+)$', path)
            if m:
                return self.send_json(fetch_chapter_content(m.group(1)))
            m = re.match(r'^/api/novels/(\d+)/download$', path)
            if m:
                detail = fetch_book_detail(m.group(1))
                chapters = fetch_full_chapters(m.group(1), detail.get('chapters', []))
                parts = [f"{detail.get('title')}\n作者：{detail.get('author')}\n\n{detail.get('description')}\n"]
                fetched = {}
                if chapters:
                    workers = min(6, len(chapters))
                    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
                        future_map = {}
                        for idx, ch in enumerate(chapters):
                            cached = CHAPTER_CACHE.get(ch['id'])
                            if cached:
                                fetched[idx] = cached
                                continue
                            future_map[pool.submit(fetch_chapter_content, ch['id'], 8)] = idx
                        for fut in concurrent.futures.as_completed(future_map):
                            idx = future_map[fut]
                            try:
                                fetched[idx] = fut.result(timeout=0)
                            except Exception as exc:
                                fetched[idx] = {'title': chapters[idx].get('title', ''), 'content': f'[无法获取：{exc}]'}
                for idx, ch in enumerate(chapters):
                    got = fetched.get(idx) or {'title': ch.get('title', ''), 'content': '[无法获取：超时]'}
                    parts.append('\n' + got.get('title', ch['title']) + '\n\n' + got.get('content', '') + '\n')
                body = '\n'.join(parts).encode('utf-8')
                safe_name = re.sub(r'[\\/:*?"<>|]+', '_', (detail.get('title') or m.group(1)).strip()) or m.group(1)
                filename = quote(f'{safe_name}.txt')
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.send_header('Content-Disposition', f"attachment; filename=\"novel.txt\"; filename*=UTF-8''{filename}")
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            return self.send_json({'error': 'not found'}, 404)
        except BrokenPipeError:
            return
        except Exception as exc:
            return self.fail(exc)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            payload = self.read_json()
            if path == '/api/novels':
                novel_id = str(payload.get('novel_id') or payload.get('id') or '')
                if not novel_id:
                    return self.send_json({'error': 'Missing novel_id'}, 400)
                return self.send_json(fetch_book_detail(novel_id))
            return self.send_json({'error': 'not found'}, 404)
        except BrokenPipeError:
            return
        except ValueError as exc:
            return self.fail(exc, 400)
        except Exception as exc:
            return self.fail(exc)


def main():
    port = int(os.environ.get('PORT', '5173'))
    server = ThreadingHTTPServer(('0.0.0.0', port), Handler)
    print(f'Fanqie Novel Suite running on http://127.0.0.1:{port}')
    server.serve_forever()


if __name__ == '__main__':
    main()
