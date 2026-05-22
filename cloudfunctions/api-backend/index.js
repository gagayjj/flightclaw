// 云函数：后端 API — 直接从云数据库读取数据
// 无需 SSH 隧道，无需本地后端
const cloud = require('wx-server-sdk');
cloud.init({
  env: 'cloudbase-d7g70bhvj07f8e6dd'
});
const db = cloud.database();
const _ = db.command;

/** 获取所有记录（处理微信云数据库 100 条限制） */
async function getAll(collection, where = {}, options = {}) {
  const { orderBy, limit = 1000 } = options;
  let results = [];
  let offset = 0;
  const pageSize = 100;
  while (offset < limit) {
    let q = db.collection(collection).where(where);
    if (orderBy) {
      for (const [field, dir] of orderBy) {
        q = q.orderBy(field, dir);
      }
    }
    const res = await q.skip(offset).limit(pageSize).get();
    results = results.concat(res.data);
    if (res.data.length < pageSize) break;
    offset += pageSize;
  }
  return results;
}

exports.main = async (event, context) => {
  const path = event.path || '/';
  const params = event.params || {};

  try {
    switch (path) {
      // ===== 价格列表 =====
      case '/api/prices': {
        const { origin = '深圳', destination = '北京', date_from = '2026-06-15', date_to = '2026-06-23', max_price = 2000 } = params;
        const data = await getAll('price_records', {
          origin, destination,
          flight_date: _.gte(date_from).and(_.lte(date_to)),
          total_price: _.gte(300).and(_.lte(Number(max_price))),
        }, { orderBy: [['flight_date', 'asc'], ['total_price', 'asc']] });
        return { count: data.length, data };
      }

      // ===== 每日最低价 =====
      case '/api/prices/lowest': {
        const { origin = '深圳', destination = '北京', date_from = '2026-06-15', date_to = '2026-06-23' } = params;
        const all = await getAll('price_records', {
          origin, destination,
          flight_date: _.gte(date_from).and(_.lte(date_to)),
          total_price: _.gte(300),
        });
        const byDate = {};
        for (const r of all) {
          if (!byDate[r.flight_date] || r.total_price < byDate[r.flight_date].total_price) {
            byDate[r.flight_date] = r;
          }
        }
        const data = Object.values(byDate).sort((a, b) => a.flight_date.localeCompare(b.flight_date));
        return { count: data.length, data };
      }

      // ===== 价格趋势 =====
      case '/api/prices/trend': {
        const { origin = '深圳', destination = '北京', date_from = '2026-06-15', date_to = '2026-06-23' } = params;
        const all = await getAll('price_records', {
          origin, destination,
          flight_date: _.gte(date_from).and(_.lte(date_to)),
        });
        const byDate = {};
        for (const r of all) {
          if (!byDate[r.flight_date]) {
            byDate[r.flight_date] = { min: Infinity, max: -Infinity, sum: 0, count: 0 };
          }
          const d = byDate[r.flight_date];
          d.min = Math.min(d.min, r.total_price);
          d.max = Math.max(d.max, r.total_price);
          d.sum += r.total_price;
          d.count++;
        }
        const data = Object.entries(byDate).sort(([a], [b]) => a.localeCompare(b)).map(([date, v]) => ({
          date,
          min: Math.round(v.min * 10) / 10,
          max: Math.round(v.max * 10) / 10,
          avg: Math.round(v.sum / v.count * 10) / 10,
          count: v.count,
        }));
        return { data };
      }

      // ===== 平台比价 =====
      case '/api/prices/compare': {
        const { date, origin = '深圳', destination = '北京' } = params;
        const all = await getAll('price_records', {
          origin, destination,
          flight_date: date,
        });
        const byFlight = {};
        for (const r of all) {
          const key = r.flight_number;
          if (!byFlight[key]) {
            byFlight[key] = {
              flight_number: r.flight_number,
              airline: r.airline,
              departure_time: r.departure_time,
              arrival_time: r.arrival_time,
              duration: r.duration,
              stops: r.stops,
              prices: {},
            };
          }
          byFlight[key].prices[r.source] = {
            ticket_price: r.ticket_price,
            total_price: r.total_price,
            booking_url: r.booking_url,
          };
        }
        return { date, sources: ['ctrip'], data: Object.values(byFlight) };
      }

      // ===== 统计数据 =====
      case '/api/statistics': {
        const all = await getAll('price_records', { total_price: _.gte(300) });
        const total = all.length;
        const lowest = all.reduce((m, r) => Math.min(m, r.total_price), Infinity);
        const today = new Date().toISOString().slice(0, 10);
        const todayRes = all.filter(r => (r.captured_at || '').startsWith(today));
        return {
          total_records: total,
          lowest_price: lowest === Infinity ? 0 : lowest,
          today_new: todayRes.length,
          sources: { ctrip: total },
        };
      }

      // ===== 往返方案 =====
      case '/api/roundtrip/deals': {
        const maxTotal = Number(params.max_total || 1700);
        const res = await db.collection('roundtrip_deals').where({
          total_price: _.lte(maxTotal),
        }).orderBy('total_price', 'asc').get();
        return { count: res.data.length, data: res.data };
      }

      // ===== 根路径 =====
      case '/':
      case '':
        return { status: 'ok', name: '低价机票追踪', version: '1.0.0-cloud' };

      default:
        return { error: `unknown path: ${path}`, code: -1 };
    }
  } catch (err) {
    console.error('[api-backend] 错误:', err);
    return { error: err.message, code: -1 };
  }
};
