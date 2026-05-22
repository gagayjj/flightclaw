// 云函数：API 代理
// 支持两种调用方式：
//   1. wx.cloud.callFunction (event.path = /api/xxx)
//   2. HTTP 服务 (event.path = /api-proxy/api/xxx)
const cloud = require('wx-server-sdk');
cloud.init();

function httpRequest(url, method = 'GET') {
  return new Promise((resolve, reject) => {
    const mod = url.startsWith('https') ? require('https') : require('http');
    const urlObj = new URL(url);
    const options = {
      hostname: urlObj.hostname,
      port: urlObj.port || 443,
      path: urlObj.pathname + urlObj.search,
      method: method,
      timeout: 15000,
      headers: { 'User-Agent': 'CloudFunction/1.0' },
    };
    const req = mod.request(options, (resp) => {
      let data = '';
      resp.on('data', chunk => data += chunk);
      resp.on('end', () => {
        try { resolve(JSON.parse(data)); }
        catch { resolve({ raw: data }); }
      });
    });
    req.on('error', reject);
    req.setTimeout(15000, () => { req.destroy(); reject(new Error('timeout')); });
    req.end();
  });
}

exports.main = async (event, context) => {
  const isHttpService = event.httpMethod !== undefined;
  let path, params, tunnelUrl, method;

  if (isHttpService) {
    // HTTP 服务调用
    path = event.path || '/';
    path = path.replace(/^\/api-proxy/, '') || '/';
    params = event.queryStringParameters || {};
    method = event.httpMethod || 'GET';
    tunnelUrl = event.headers?.['x-tunnel-url'] || '';
  } else {
    // wx.cloud.callFunction 调用
    path = event.path || '/';
    params = event.params || {};
    method = event.method || (path.includes('/api/scan') || path.includes('/api/start') || path.includes('/api/stop') || path.includes('/api/push') ? 'POST' : 'GET');
    tunnelUrl = event._apiBaseUrl || '';
  }

  if (!tunnelUrl) {
    return { error: 'no tunnel url', code: -1 };
  }

  // 构建完整 URL
  const baseUrl = `${tunnelUrl}${path}`;
  const hasQuery = baseUrl.includes('?');
  const paramStr = Object.entries(params)
    .filter(([k]) => k !== '_apiBaseUrl')
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
    .join('&');

  const fullUrl = paramStr ? `${baseUrl}${hasQuery ? '&' : '?'}${paramStr}&_t=${Date.now()}` : baseUrl;

  console.log(`[代理] ${method} ${fullUrl.substring(0, 200)}`);

  try {
    return await httpRequest(fullUrl, method);
  } catch (err) {
    console.error('[代理] 请求失败:', err.message);
    return { error: err.message, code: -1 };
  }
};
