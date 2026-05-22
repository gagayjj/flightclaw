const api = require('../../utils/api');
const util = require('../../utils/util');
const app = getApp();

Page({
  data: {
    directionLabel: '深圳→北京',
    origin: '深圳',
    destination: '北京',
    trend: [],
    lowestPrices: [],
    stats: null,
    minPrice: 0,
    maxPrice: 0,
    range: 1,
    lowestGlobal: 0,
    util: util,
  },

  onShow() {
    this.syncDirection();
    this.loadHistory();
  },

  syncDirection() {
    const g = app.globalData;
    const dir = g.directions[g.currentDirection];
    this.setData({
      directionLabel: dir ? dir.label : `${g.origin}→${g.destination}`,
      origin: g.origin,
      destination: g.destination,
    });
  },

  loadHistory() {
    wx.showLoading({ title: '加载中' });
    Promise.all([
      api.getTrend(),
      api.getLowestPrices(),
      api.getStatistics(),
    ]).then(([trendRes, lowestRes, stats]) => {
      const trend = (trendRes.data || []).map(t => ({ ...t, _minText: '¥' + Math.round(t.min) }));
      const lowestPrices = (lowestRes.data || []).sort((a, b) => a.total_price - b.total_price).map(p => ({
        ...p, _priceText: Number(p.total_price) > 0 ? '¥' + Math.round(Number(p.total_price)) : '¥--'
      }));

      let minPrice = 0, maxPrice = 0;
      if (trend.length > 0) {
        minPrice = Math.min(...trend.map(t => t.min));
        maxPrice = Math.max(...trend.map(t => t.max));
      }
      const lowestGlobal = lowestPrices.length > 0 ? lowestPrices[0].total_price : 0;
      const statsData = stats ? {
        total_records: stats.total_records,
        lowest_price: stats.lowest_price,
        today_new: stats.today_new,
        sources: Object.entries(stats.sources || {}).map(([name, count]) => ({ name, count })),
      } : null;

      this.setData({
        trend,
        lowestPrices,
        stats: statsData,
        minPrice, maxPrice,
        range: (maxPrice - minPrice) || 1,
        lowestGlobal,
      });
      wx.hideLoading();
    }).catch(() => {
      wx.hideLoading();
      wx.showToast({ title: '加载失败', icon: 'none' });
    });
  },

  /** 点击排名项查看详情 */
  onViewDetail(e) {
    const { date, origin, destination } = e.currentTarget.dataset;
    wx.navigateTo({
      url: `/pages/detail/detail?date=${date}&origin=${origin}&destination=${destination}`,
    });
  },

  /** 点击趋势日期查看详情 */
  onTrendDetail(e) {
    const { date } = e.currentTarget.dataset;
    wx.navigateTo({
      url: `/pages/detail/detail?date=${date}&origin=${this.data.origin}&destination=${this.data.destination}`,
    });
  },

  /** 复制预订链接到剪贴板 */
  onPlatformBook(e) {
    const item = e.currentTarget.dataset;
    util.bookFlight(this.data.origin, this.data.destination, item.flight_date, item.flight_number || '', item.source || 'ctrip');
  },
});
