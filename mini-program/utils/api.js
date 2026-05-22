/** 后端 API 封装 — 云函数直连云数据库（无需隧道，无需本地后端） */

const app = getApp();

/** 本地后端地址（仅在开发者工具中有效） */
const LOCAL_API = 'http://127.0.0.1:8000';

function callApi(path, data = {}) {
  // 先尝试云函数
  return callCloudFunction(path, data).catch(err => {
    console.warn('[API] 云函数调用失败，尝试本地后端:', err);
    // 云函数失败，降级到本地后端（开发工具可用）
    return callLocalApi(path, data);
  });
}

/** 通过云函数调用 */
function callCloudFunction(path, data = {}) {
  return new Promise((resolve, reject) => {
    wx.cloud.callFunction({
      name: 'api-backend',
      data: { path, params: data },
      success: res => {
        const result = res.result;
        if (!result) {
          reject(new Error('云函数返回为空'));
        } else if (result.error) {
          reject(new Error(result.error));
        } else {
          resolve(result);
        }
      },
      fail: err => {
        console.error('[云函数] 调用失败:', err);
        reject(err);
      },
    });
  });
}

/** 通过本地后端（开发者工具备用） */
function callLocalApi(path, data = {}) {
  return new Promise((resolve, reject) => {
    const qs = Object.keys(data).map(k => `${encodeURIComponent(k)}=${encodeURIComponent(data[k])}`).join('&');
    const url = `${LOCAL_API}${path}${qs ? '?' + qs : ''}`;
    wx.request({
      url,
      method: 'GET',
      success: res => {
        if (res.statusCode === 200 && res.data) {
          // 标准化返回格式
          const d = res.data;
          if (d && d.error) reject(new Error(d.error));
          else if (Array.isArray(d)) resolve({ count: d.length, data: d });
          else resolve(d);
        } else {
          reject(new Error(`HTTP ${res.statusCode}`));
        }
      },
      fail: err => reject(err),
    });
  });
}

/** 获取符合预算的航班列表 */
function getPrices(params = {}) {
  const g = app.globalData;
  return callApi('/api/prices', {
    origin: g.origin,
    destination: g.destination,
    date_from: g.dateFrom,
    date_to: g.dateTo,
    max_price: g.maxPrice,
    ...params
  });
}

/** 获取每日最低价 */
function getLowestPrices() {
  const g = app.globalData;
  return callApi('/api/prices/lowest', {
    origin: g.origin,
    destination: g.destination,
    date_from: g.dateFrom,
    date_to: g.dateTo,
  });
}

/** 获取价格趋势 */
function getTrend() {
  const g = app.globalData;
  return callApi('/api/prices/trend', {
    origin: g.origin,
    destination: g.destination,
    date_from: g.dateFrom,
    date_to: g.dateTo,
  });
}

/** 获取统计信息 */
function getStatistics() {
  return callApi('/api/statistics');
}

/** 获取平台比价数据 */
function getPriceCompare(date, origin, destination) {
  return callApi('/api/prices/compare', { date, origin, destination });
}

/** 获取往返比价方案 */
function getRoundtripDeals(maxTotal = 1700) {
  return callApi('/api/roundtrip/deals', { max_total: maxTotal });
}

/** 以下功能需要本地后端支持，暂不可用 */
function triggerScan() {
  return Promise.reject(new Error('自动扫描已在服务端运行'));
}
function triggerRoundtripScan() {
  return Promise.reject(new Error('往返数据已预生成'));
}
function startMonitor() {
  return Promise.reject(new Error('监控已服务端自动运行'));
}
function stopMonitor() {
  return Promise.reject(new Error('监控已服务端自动运行'));
}

module.exports = {
  getPrices,
  getLowestPrices,
  getTrend,
  getStatistics,
  getRoundtripDeals,
  getPriceCompare,
  triggerScan,
  triggerRoundtripScan,
  startMonitor,
  stopMonitor,
};
