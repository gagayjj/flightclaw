const api = require('../../utils/api');
const util = require('../../utils/util');

Page({
  data: {
    origin: '',
    destination: '',
    date: '',
    flights: [],
    lowest: null,
    util,
  },

  onLoad(options) {
    const { date, origin, destination } = options;
    this.setData({ date, origin: origin || '深圳', destination: destination || '北京' });
    this.loadFlights();
  },

  loadFlights() {
    wx.showLoading({ title: '加载中' });
    const { date, origin, destination } = this.data;

    api.getPrices({
      date_from: date,
      date_to: date,
      origin,
      destination,
    }).then(res => {
      const raw = res.data || res || [];
      const flights = raw.map(p => ({
        ...p,
        _price: p.total_price,
        _priceText: Number(p.total_price) > 0 ? '¥' + Math.round(Number(p.total_price)) : '¥--',
        _feeText: `票价 ¥${Math.round(Number(p.ticket_price) || 0)} + 机建 ¥${p.airport_fee || 50} + 燃油 ¥${p.fuel_tax || 50}`,
      })).sort((a, b) => (a._price || 0) - (b._price || 0));
      this.setData({
        flights,
        lowest: flights.length > 0 ? flights[0] : null,
      });
      wx.hideLoading();
    }).catch(() => {
      wx.hideLoading();
      wx.showToast({ title: '加载失败', icon: 'none' });
    });
  },


  /** 复制预订链接到剪贴板 */
  onPlatformBook(e) {
    const item = e.currentTarget.dataset;
    util.bookFlight(this.data.origin, this.data.destination, item.flight_date, item.flight_number, item.source || 'ctrip');
  },

  /** 预订最低价 */
  onBookLowest(e) {
    const item = e.currentTarget.dataset;
    util.bookFlight(this.data.origin, this.data.destination, item.flight_date, item.flight_number, item.source || 'ctrip');
  },
});
