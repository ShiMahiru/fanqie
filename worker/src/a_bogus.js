const ENCODE_TABLES = {
  s0: 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=',
  s1: 'Dkdpgh4ZKsQB80/Mfvw36XI1R25+WUAlEi7NLboqYTOPuzmFjJnryx9HVGcaStCe=',
  s2: 'Dkdpgh4ZKsQB80/Mfvw36XI1R25-WUAlEi7NLboqYTOPuzmFjJnryx9HVGcaStCe=',
  s3: 'ckdp1h4ZKsUB80/Mfvw36XIgR25+WQAlEi7NLboqYTOPuzmFjJnryx9HVGDaStCe',
  s4: 'Dkdpgh2ZmsQB80/MfvV36XI1R45-WUAlEixNLwoqYTOPuzKFjJnry79HbGcaStCe',
};
const WINDOW_ENV_STR = '1536|747|1536|834|0|30|0|0|1536|834|1536|864|1525|747|24|24|Win32';
const SM3_IV = [0x7380166f, 0x4914b2b9, 0x172442d7, 0xda8a0600, 0xa96f30bc, 0x163138aa, 0xe38dee4d, 0xb0fb0e4e];
const textEncoder = new TextEncoder();

export function generateABogus(urlSearchParams, userAgent) {
  const random = generateRandomStr();
  const rc4bb = generateRc4BbStr(urlSearchParams, userAgent);
  return resultEncrypt(new Uint8Array([...random, ...rc4bb]), 's4') + '=';
}

function rc4Encrypt(plain, key) {
  const s = Array.from({ length: 256 }, (_, i) => i);
  let j = 0;
  for (let i = 0; i < 256; i += 1) {
    j = (j + s[i] + key[i % key.length]) & 0xff;
    [s[i], s[j]] = [s[j], s[i]];
  }
  let ii = 0;
  let jj = 0;
  const out = new Uint8Array(plain.length);
  for (let n = 0; n < plain.length; n += 1) {
    ii = (ii + 1) & 0xff;
    jj = (jj + s[ii]) & 0xff;
    [s[ii], s[jj]] = [s[jj], s[ii]];
    out[n] = s[(s[ii] + s[jj]) & 0xff] ^ plain[n];
  }
  return out;
}

function rotl(x, n) {
  n %= 32;
  return ((x << n) | (x >>> (32 - n))) >>> 0;
}
function ff(j, x, y, z) { return j < 16 ? (x ^ y ^ z) >>> 0 : ((x & y) | (x & z) | (y & z)) >>> 0; }
function gg(j, x, y, z) { return j < 16 ? (x ^ y ^ z) >>> 0 : ((x & y) | ((~x) & z)) >>> 0; }
function tj(j) { return j < 16 ? 0x79cc4519 : 0x7a879d8a; }
function p0(x) { return (x ^ rotl(x, 9) ^ rotl(x, 17)) >>> 0; }
function p1(x) { return (x ^ rotl(x, 15) ^ rotl(x, 23)) >>> 0; }
function add32(...vals) { return vals.reduce((acc, v) => (acc + (v >>> 0)) >>> 0, 0); }

function sm3Compress(reg, block) {
  const w = new Array(132).fill(0);
  for (let i = 0; i < 16; i += 1) {
    const p = i * 4;
    w[i] = (((block[p] << 24) | (block[p + 1] << 16) | (block[p + 2] << 8) | block[p + 3]) >>> 0);
  }
  for (let n = 16; n < 68; n += 1) {
    const a = (w[n - 16] ^ w[n - 9] ^ rotl(w[n - 3], 15)) >>> 0;
    w[n] = (p1(a) ^ rotl(w[n - 13], 7) ^ w[n - 6]) >>> 0;
  }
  for (let n = 0; n < 64; n += 1) w[n + 68] = (w[n] ^ w[n + 4]) >>> 0;
  const v = reg.slice();
  for (let c = 0; c < 64; c += 1) {
    const ssBase = add32(rotl(v[0], 12), v[4], rotl(tj(c), c));
    const ss1 = (rotl(ssBase, 7) ^ rotl(v[0], 12)) >>> 0;
    const ss2 = (ss1 ^ rotl(v[0], 12)) >>> 0;
    const tt1 = add32(ff(c, v[0], v[1], v[2]), v[3], ss2, w[c + 68]);
    const tt2 = add32(gg(c, v[4], v[5], v[6]), v[7], ss1, w[c]);
    v[3] = v[2];
    v[2] = rotl(v[1], 9);
    v[1] = v[0];
    v[0] = tt1;
    v[7] = v[6];
    v[6] = rotl(v[5], 19);
    v[5] = v[4];
    v[4] = p0(tt2);
  }
  return reg.map((r, i) => (r ^ v[i]) >>> 0);
}

function urlEncodeBytes(s) {
  const bytes = textEncoder.encode(s);
  const out = [];
  const safe = new Set([32, 45, 46, 95, 126]);
  const hex = '0123456789ABCDEF';
  for (const ch of bytes) {
    if ((ch >= 48 && ch <= 57) || (ch >= 65 && ch <= 90) || (ch >= 97 && ch <= 122) || safe.has(ch)) out.push(ch);
    else {
      out.push(37, hex.charCodeAt(ch >> 4), hex.charCodeAt(ch & 15));
    }
  }
  return new Uint8Array(out);
}

function sm3BytesFromBytes(data) {
  let reg = SM3_IV.slice();
  const size = data.length;
  const withOne = size + 1;
  const padLen = ((withOne % 64) <= 56 ? 56 - (withOne % 64) : 64 + 56 - (withOne % 64));
  const full = new Uint8Array(size + 1 + padLen + 8);
  full.set(data, 0);
  full[size] = 0x80;
  const bitLen = size * 8;
  const hi = Math.floor(bitLen / 0x100000000) >>> 0;
  const lo = bitLen >>> 0;
  const p = full.length - 8;
  full[p] = (hi >>> 24) & 0xff; full[p + 1] = (hi >>> 16) & 0xff; full[p + 2] = (hi >>> 8) & 0xff; full[p + 3] = hi & 0xff;
  full[p + 4] = (lo >>> 24) & 0xff; full[p + 5] = (lo >>> 16) & 0xff; full[p + 6] = (lo >>> 8) & 0xff; full[p + 7] = lo & 0xff;
  for (let i = 0; i < full.length; i += 64) reg = sm3Compress(reg, full.slice(i, i + 64));
  return regToBytes(reg);
}
function sm3Bytes(s) { return sm3BytesFromBytes(urlEncodeBytes(s)); }
function sm3Hex(s) { return Array.from(sm3Bytes(s), (b) => b.toString(16).padStart(2, '0')).join(''); }
function regToBytes(reg) {
  const out = new Uint8Array(32);
  reg.forEach((r, i) => {
    const p = i * 4;
    out[p] = (r >>> 24) & 0xff; out[p + 1] = (r >>> 16) & 0xff; out[p + 2] = (r >>> 8) & 0xff; out[p + 3] = r & 0xff;
  });
  return out;
}

function resultEncrypt(data, tableName) {
  const table = ENCODE_TABLES[tableName] || ENCODE_TABLES.s0;
  const out = [];
  const chunks = Math.floor(data.length / 3);
  for (let i = 0; i < chunks; i += 1) {
    const r = i * 3;
    const longInt = (data[r] << 16) | (data[r + 1] << 8) | data[r + 2];
    out.push(table[(longInt & 0xfc0000) >> 18], table[(longInt & 0x03f000) >> 12], table[(longInt & 0x000fc0) >> 6], table[longInt & 63]);
  }
  return out.join('');
}

function generRandom(randomVal, option) {
  return new Uint8Array([
    ((randomVal & 0xff & 0xaa) | (option[0] & 0x55)) & 0xff,
    ((randomVal & 0xff & 0x55) | (option[0] & 0xaa)) & 0xff,
    (((randomVal >> 8) & 0xff & 0xaa) | (option[1] & 0x55)) & 0xff,
    (((randomVal >> 8) & 0xff & 0x55) | (option[1] & 0xaa)) & 0xff,
  ]);
}
function generateRandomStr() {
  return new Uint8Array([...generRandom(Math.floor(Math.random() * 10000), [3, 45]), ...generRandom(Math.floor(Math.random() * 10000), [1, 0]), ...generRandom(Math.floor(Math.random() * 10000), [1, 5])]);
}

function latin1Bytes(str) {
  const out = new Uint8Array(str.length);
  for (let i = 0; i < str.length; i += 1) out[i] = str.charCodeAt(i) & 0xff;
  return out;
}
function utf8LossyRoundTrip(bytes) {
  return textEncoder.encode(new TextDecoder('utf-8', { fatal: false }).decode(bytes));
}

function generateRc4BbStr(urlSearchParams, userAgent) {
  const start = Date.now() >>> 0;
  const urlHashHex = sm3Hex(urlSearchParams);
  const urlList = sm3Bytes(urlHashHex);
  const cusHashHex = sm3Hex('cus');
  const cusList = sm3Bytes(cusHashHex);
  const rc4ua = rc4Encrypt(latin1Bytes(userAgent), new Uint8Array([1, 0, 14]));
  const uaBase64 = resultEncrypt(rc4ua, 's3');
  const uaList = sm3BytesFromBytes(latin1Bytes(uaBase64));
  const end = Date.now() >>> 0;
  const b = {};
  b[8] = 3; b[10] = end; b[16] = start; b[18] = 44;
  b[20] = (b[16] >>> 24) & 0xff; b[21] = (b[16] >>> 16) & 0xff; b[22] = (b[16] >>> 8) & 0xff; b[23] = b[16] & 0xff; b[24] = 0; b[25] = 0;
  b[26] = 0; b[27] = 0; b[28] = 0; b[29] = 0; b[30] = 0; b[31] = 1; b[32] = 0; b[33] = 0; b[34] = 0; b[35] = 0; b[36] = 0; b[37] = 14;
  b[38] = urlList[21]; b[39] = urlList[22]; b[40] = cusList[21]; b[41] = cusList[22]; b[42] = uaList[23]; b[43] = uaList[24];
  b[44] = (b[10] >>> 24) & 0xff; b[45] = (b[10] >>> 16) & 0xff; b[46] = (b[10] >>> 8) & 0xff; b[47] = b[10] & 0xff; b[48] = b[8]; b[49] = 0; b[50] = 0;
  const pageId = 6241, aid = 6383;
  b[51] = pageId; b[52] = (pageId >>> 24) & 0xff; b[53] = (pageId >>> 16) & 0xff; b[54] = (pageId >>> 8) & 0xff; b[55] = pageId & 0xff;
  b[56] = aid; b[57] = aid & 0xff; b[58] = (aid >>> 8) & 0xff; b[59] = (aid >>> 16) & 0xff; b[60] = (aid >>> 24) & 0xff;
  const env = latin1Bytes(WINDOW_ENV_STR);
  b[64] = env.length; b[65] = env.length & 0xff; b[66] = (env.length >>> 8) & 0xff; b[69] = 0; b[70] = 0; b[71] = 0;
  b[72] = (b[18] ^ b[20] ^ b[26] ^ b[30] ^ b[38] ^ b[40] ^ b[42] ^ b[21] ^ b[27] ^ b[31] ^ b[35] ^ b[39] ^ b[41] ^ b[43] ^ b[22] ^ b[28] ^ b[32] ^ b[36] ^ b[23] ^ b[29] ^ b[33] ^ b[37] ^ b[44] ^ b[45] ^ b[46] ^ b[47] ^ b[48] ^ b[49] ^ b[50] ^ b[24] ^ b[25] ^ b[52] ^ b[53] ^ b[54] ^ b[55] ^ b[57] ^ b[58] ^ b[59] ^ b[60] ^ b[65] ^ b[66] ^ b[70] ^ b[71]) & 0xff;
  const order = [18, 20, 52, 26, 30, 34, 58, 38, 40, 53, 42, 21, 27, 54, 55, 31, 35, 57, 39, 41, 43, 22, 28, 32, 60, 36, 23, 29, 33, 37, 44, 45, 59, 46, 47, 48, 49, 50, 24, 25, 65, 66, 70, 71];
  const bb = new Uint8Array(order.length + env.length + 1);
  order.forEach((idx, i) => { bb[i] = (b[idx] || 0) & 0xff; });
  bb.set(env, order.length);
  bb[bb.length - 1] = b[72];
  return rc4Encrypt(utf8LossyRoundTrip(bb), new Uint8Array([121]));
}
