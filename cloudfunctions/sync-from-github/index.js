/**
 * 从 GitHub 拉取航班数据 JSON → 写入云数据库
 * 定时触发：每 30 分钟
 *
 * 数据来源：GitHub Actions 抓取后提交到仓库的 data/latest_prices.json
 */
const cloud = require('wx-server-sdk');
cloud.init({ env: 'cloudbase-d7g70bhvj07f8e6dd' });
const db = cloud.database();
const _ = db.command;

// ⚠️ 改成你的 GitHub 仓库地址
const DATA_URL = 'https://raw.githubusercontent.com/YOUR_USERNAME/YOUR_REPO/main/data/latest_prices.json';

/** 批量插入（每次最多 100 条） */
async function batchInsert(collection, items) {
  if (!items || items.length === 0) return 0;
  let count = 0;
  for (let i = 0; i < items.length; i += 100) {
    await db.collection(collection).add({ data: items.slice(i, i + 100) });
    count += Math.min(100, items.length - i);
  }
  return count;
}

/** 删除某天某路线的旧数据 */
async function removeDayRecords(origin, destination, flightDate) {
  let total = 0;
  for (;;) {
    const res = await db.collection('price_records').where({
      origin, destination, flight_date: flightDate,
    }).limit(1000).remove();
    total += res.stats.removed || 0;
    if ((res.stats.removed || 0) < 1000) break;
  }
  return total;
}

exports.main = async (event, context) => {
  console.log('[sync-from-github] 开始同步...');

  // 1. 获取自定义 URL（从 event 传入），否则用默认
  const dataUrl = event.dataUrl || DATA_URL;
  console.log('[sync-from-github] 数据地址:', dataUrl);

  try {
    // 2. 获取 JSON 数据
    const resp = await new Promise((resolve, reject) => {
      const url = require('url');
      const proto = dataUrl.startsWith('https') ? require('https') : require('http');
      const req = proto.get(dataUrl, (res) => {
        let body = '';
        res.on('data', chunk => body += chunk);
        res.on('end', () => resolve(body));
      });
      req.on('error', reject);
      req.setTimeout(30000, () => { req.destroy(); reject(new Error('timeout')); });
    });

    const data = JSON.parse(resp);
    console.log('[sync-from-github] 获取数据:', JSON.stringify(data).length, 'bytes');

    // 3. 导入价格记录
    const prices = data.prices || [];
    if (prices.length > 0) {
      // 按日分组去重
      const groups = {};
      for (const p of prices) {
        const key = `${p.origin}|${p.destination}|${p.flight_date}`;
        if (!groups[key]) groups[key] = [];
        groups[key].push(p);
      }

      let totalDel = 0, totalIns = 0;
      for (const [key, items] of Object.entries(groups)) {
        const [origin, dest, date] = key.split('|');
        const del = await removeDayRecords(origin, dest, date);
        const ins = await batchInsert('price_records', items);
        totalDel += del;
        totalIns += ins;
      }
      console.log(`[sync-from-github] 价格: 删 ${totalDel} 插 ${totalIns}`);
    }

    // 4. 导入往返方案
    const deals = data.roundtrip || data.deals || [];
    if (deals.length > 0) {
      await db.collection('roundtrip_deals').where({}).remove();
      const ins = await batchInsert('roundtrip_deals', deals);
      console.log(`[sync-from-github] 往返: 插 ${ins} 条`);
    }

    return { code: 0, message: `synced: ${prices.length} prices, ${deals.length} deals` };

  } catch (e) {
    console.error('[sync-from-github] 错误:', e.message);
    return { code: 500, error: e.message };
  }
};
