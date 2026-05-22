const api = require('../../utils/api');
const util = require('../../utils/util');
const app = getApp();

Page({
  data: {
    origin: '深圳',
    destination: '北京',
    directionLabel: '深圳→北京',
    dateFrom: '2026-06-15',
    dateTo: '2026-06-23',
    maxPrice: 2000,
    priceOptions: [1000, 1300, 1500, 2000, 2500],
    priceIndex: 3,
    lowestPrices: [],
    allPrices: [],
    stats: null,
    lowestPriceDate: '',
    loading: true,
    util: util,
  },

  onLoad() {
    this.syncDirection();
    this.loadData();
  },

  onShow() {
    this.syncDirection();
  },

  /** 从 app.globalData 同步当前方向 */
  syncDirection() {
    const g = app.globalData;
    const dir = g.directions[g.currentDirection];
    this.setData({
      origin: g.origin,
      destination: g.destination,
      directionLabel: dir ? dir.label : `${g.origin}→${g.destination}`,
      dateFrom: g.dateFrom,
      dateTo: g.dateTo,
      maxPrice: g.maxPrice,
    });
  },

  onPullDownRefresh() {
    this.loadData(() => wx.stopPullDownRefresh());
  },

  /** 切换方向 */
  onSwitchDirection() {
    const dir = app.switchDirection();
    this.syncDirection();
    this.loadData();
    wx.showToast({ title: dir.label, icon: 'none' });
  },

  loadData(callback) {
    this.setData({ loading: true });
    const g = app.globalData;
    // 确保 globalData 是最新的
    g.origin = this.data.origin;
    g.destination = this.data.destination;
    Promise.all([
      api.getLowestPrices(),
      api.getPrices(),
      api.getStatistics(),
    ]).then(([lowestRes, pricesRes, stats]) => {
      const rawPrices = lowestRes.data || [];
      const rawAll = pricesRes.data || [];
      // 预处理：确保价格字段存在，预计算显示文本
      const prices = rawPrices.map(p => {
        const base = { ...p, _price: p.total_price, _priceText: Number(p.total_price) > 0 ? '¥' + Math.round(Number(p.total_price)) : '¥--' };
        base._feeText = `票¥${Math.round(Number(p.ticket_price) || 0)} + 机建¥${p.airport_fee || 50} + 燃油¥${p.fuel_tax || 50}`;
        return base;
      });
      const allPrices = rawAll.map(p => {
        const base = { ...p, _price: p.total_price, _priceText: Number(p.total_price) > 0 ? '¥' + Math.round(Number(p.total_price)) : '¥--' };
        base._feeText = `票¥${Math.round(Number(p.ticket_price) || 0)} + 机建¥${p.airport_fee || 50} + 燃油¥${p.fuel_tax || 50}`;
        return base;
      });
      const lowest = prices.reduce((a, b) => a._price < b._price ? a : b, prices[0]);
      this.setData({
        lowestPrices: prices,
        allPrices: allPrices,
        stats: stats || null,
        lowestPriceDate: lowest ? lowest.flight_date : '',
        loading: false,
      });
    }).catch(err => {
      console.error(err);
      this.setData({ loading: false });
      wx.showToast({ title: '网络错误', icon: 'none' });
    }).finally(() => {
      if (callback) callback();
    });
  },

  onRefresh() {
    wx.showLoading({ title: '正在刷新...' });
    this.loadData(() => {
      wx.hideLoading();
      wx.showToast({ title: '已是最新数据', icon: 'success' });
    });
  },

  onDateFromChange(e) {
    const val = e.detail.value;
    this.setData({ dateFrom: val });
    app.globalData.dateFrom = val;
    this.loadData();
  },

  onDateToChange(e) {
    const val = e.detail.value;
    this.setData({ dateTo: val });
    app.globalData.dateTo = val;
    this.loadData();
  },

  onPriceChange(e) {
    const idx = parseInt(e.detail.value);
    const maxPrice = parseInt(this.data.priceOptions[idx]);
    app.globalData.maxPrice = maxPrice;
    this.setData({ priceIndex: idx, maxPrice });
    this.loadData();
  },

  /** 跳转预订 */
  onPlatformBook(e) {
    const item = e.currentTarget.dataset;
    util.bookFlight(this.data.origin, this.data.destination, item.flight_date, item.flight_number, item.source || 'ctrip');
  },


  onViewDetail(e) {
    const date = e.currentTarget.dataset.date;
    wx.navigateTo({
      url: `/pages/detail/detail?date=${date}&origin=${this.data.origin}&destination=${this.data.destination}`,
    });
  },

  /** 跳转到全网最低价详情 */
  onViewLowestDetail() {
    if (!this.data.lowestPriceDate) return;
    wx.navigateTo({
      url: `/pages/detail/detail?date=${this.data.lowestPriceDate}&origin=${this.data.origin}&destination=${this.data.destination}`,
    });
  },

  onShareAppMessage() {
    return {
      title: `${this.data.directionLabel} 低价机票追踪`,
      path: '/pages/index/index',
    };
  },
});
