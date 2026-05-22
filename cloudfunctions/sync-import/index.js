/**
 * 数据同步导入 - 从本地 Python 定时推送数据到云数据库
 * HTTP 触发：需在云开发控制台开启"HTTP 访问"
 */
const cloud = require('wx-server-sdk');
cloud.init({ env: 'cloudbase-d7g70bhvj07f8e6dd' });
const db = cloud.database();
const _ = db.command;

const AUTH_TOKEN = 'flightclaw-sync-2026';

/** 分页批量插入（云数据库单次最多 100 条） */
async function batchInsert(collection, items) {
  if (!items || items.length === 0) return 0;
  let inserted = 0;
  for (let i = 0; i < items.length; i += 100) {
    const batch = items.slice(i, i + 100);
    await db.collection(collection).add({ data: batch });
    inserted += batch.length;
  }
  return inserted;
}

/** 删除某天的旧数据，避免重复 */
async function removeExisting(collection, origin, destination, flightDate) {
  try {
    const res = await db.collection(collection).where({
      origin,
      destination,
      flight_date: flightDate,
    }).remove();
    return res.stats.removed || 0;
  } catch (e) {
    // remove 限制单次最多 1000 条，分批删
    let total = 0;
    for (;;) {
      const res = await db.collection(collection).where({
        origin, destination, flight_date: flightDate,
      }).limit(1000).remove();
      total += res.stats.removed || 0;
      if ((res.stats.removed || 0) < 1000) break;
    }
    return total;
  }
}

exports.main = async (event, context) => {
  const { action, token, data } = event;

  // 简单鉴权
  if (token !== AUTH_TOKEN) {
    return { code: 401, error: 'unauthorized' };
  }

  try {
    if (action === 'sync_prices') {
      // data: [{ origin, destination, flight_date, ... }]
      // 按 origin + destination + flight_date 分组去重
      const groups = {};
      for (const item of data || []) {
        const key = `${item.origin}|${item.destination}|${item.flight_date}`;
        if (!groups[key]) groups[key] = [];
        groups[key].push(item);
      }

      let totalDeleted = 0;
      let totalInserted = 0;

      for (const [key, items] of Object.entries(groups)) {
        const [origin, destination, flightDate] = key.split('|');
        const removed = await removeExisting('price_records', origin, destination, flightDate);
        const inserted = await batchInsert('price_records', items);
        totalDeleted += removed;
        totalInserted += inserted;
      }

      return {
        code: 0,
        message: `prices synced: ${totalDeleted} deleted, ${totalInserted} inserted`,
        groups: Object.keys(groups).length,
      };
    }

    if (action === 'sync_roundtrip') {
      // data: roundtrip_deals 数组
      // 先清空再插入
      await db.collection('roundtrip_deals').where({}).remove();
      const inserted = await batchInsert('roundtrip_deals', data || []);
      return { code: 0, message: `roundtrip synced: ${inserted} inserted` };
    }

    if (action === 'ping') {
      return { code: 0, message: 'pong', env: 'cloudbase-d7g70bhvj07f8e6dd' };
    }

    return { code: 400, error: 'unknown action' };
  } catch (e) {
    return { code: 500, error: e.message };
  }
};
