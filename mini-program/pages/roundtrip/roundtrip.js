const api = require('../../utils/api');
const util = require('../../utils/util');
const app = getApp();

Page({
  data: {
    deals: [],
    loading: true,
    maxTotal: 1700,
    budget: 1700,
    directionLabel: '深圳↔北京',
    util: util,
  },

  onShow() {
    this.loadDeals();
  },

  loadDeals() {
    this.setData({ loading: true });
    return api.getRoundtripDeals(this.data.maxTotal).then(res => {
      this.setData({
        deals: res.data || [],
        loading: false,
      });
    }).catch(err => {
      console.error(err);
      this.setData({ loading: false });
      throw err;
    });
  },

  onRefresh() {
    wx.showLoading({ title: '刷新中...' });
    this.loadDeals().then(() => {
      wx.hideLoading();
      wx.showToast({ title: '已刷新', icon: 'success' });
    }).catch(() => {
      wx.hideLoading();
      wx.showToast({ title: '刷新失败', icon: 'none' });
    });
  },

  onViewOutbound(e) {
    const { date } = e.currentTarget.dataset;
    wx.navigateTo({
      url: `/pages/detail/detail?date=${date}&origin=深圳&destination=北京`,
    });
  },

  onViewReturn(e) {
    const { date } = e.currentTarget.dataset;
    wx.navigateTo({
      url: `/pages/detail/detail?date=${date}&origin=北京&destination=深圳`,
    });
  },

  /** 复制预订链接到剪贴板 */
  onPlatformBook(e) {
    const item = e.currentTarget.dataset;
    util.bookFlight(item.origin || '深圳', item.destination || '北京', item.flight_date || '', '', item.source || 'ctrip');
  },

  onShareAppMessage() {
    return {
      title: '深圳↔北京 往返低价方案',
      path: '/pages/roundtrip/roundtrip',
    };
  },
});
