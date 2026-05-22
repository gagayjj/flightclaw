/** 工具函数 */

// 各平台信息
const PLATFORMS = [
  { key: 'ctrip',   name: '携程',    color: '#FF6A00', icon: '✈' },
  { key: 'qunar',   name: '去哪儿',  color: '#00AF66', icon: '✈' },
  { key: 'fliggy',  name: '飞猪',    color: '#FF6600', icon: '✈' },
  { key: 'airline', name: '航司直营', color: '#1a73e8', icon: '✈' },
];

function getPlatformInfo(source) {
  return PLATFORMS.find(p => p.key === source) || { key: source, name: source, color: '#999', icon: '✈' };
}

/** 生成各平台预订链接（含具体航班号） */
function getBookingUrl(source, origin, destination, date, flightNumber) {
  const cityMap = { '深圳': 'szx', '北京': 'bjs', '广州': 'can', '上海': 'sha' };
  const dep = cityMap[origin] || origin.toLowerCase();
  const arr = cityMap[destination] || destination.toLowerCase();
  const fno = flightNumber ? '&flight=' + encodeURIComponent(flightNumber) : '';
  const urls = {
    ctrip: `https://flights.ctrip.com/online/list/oneway-${dep}-${arr}?depdate=${date}${fno}`,
    qunar: `https://flight.qunar.com/site/oneway_list.htm?searchDepartureAirport=${encodeURIComponent(origin)}&searchArrivalAirport=${encodeURIComponent(destination)}&startDate=${date}`,
    fliggy: `https://www.fliggy.com/search/flight?departure=${encodeURIComponent(origin)}&arrival=${encodeURIComponent(destination)}&date=${date}`,
    airline: '',
  };
  return urls[source] || '';
}

function formatPrice(price) {
  if (price === undefined || price === null || isNaN(Number(price))) return '¥--';
  return '¥' + Math.round(Number(price));
}

function formatTime(isoStr) {
  if (!isoStr) return '';
  return isoStr.substring(11, 16);
}

function formatDate(dateStr) {
  const d = dateStr.replace(/-/g, '/');
  const dt = new Date(d);
  const weekdays = ['日', '一', '二', '三', '四', '五', '六'];
  return `${dateStr} 周${weekdays[dt.getDay()]}`;
}

function getStopText(stops) {
  if (stops === 0) return '直飞';
  return `${stops}次中转`;
}

function getStopClass(stops) {
  return stops === 0 ? 'tag-direct' : 'tag-transfer';
}

function getSourceTag(source) {
  const tags = {
    ctrip: '携程',
    qunar: '去哪儿',
    fliggy: '飞猪',
    airline: '航司直营',
  };
  return tags[source] || source;
}

/** 跳转预订（复制链接到剪贴板，按平台走） */
function bookFlight(origin, destination, date, flightNumber, source, _bookingUrl) {
  const pages = getCurrentPages();
  const page = pages[pages.length - 1];
  const o = origin || (page && page.data.origin) || '深圳';
  const d = destination || (page && page.data.destination) || '北京';
  const dt = date || '';
  const src = source || 'ctrip';

  const url = getBookingUrl(src, o, d, dt, flightNumber || '');
  if (!url) {
    wx.showToast({ title: `${src} 暂不支持`, icon: 'none' });
    return;
  }

  wx.setClipboardData({
    data: url,
    success: () => {
      wx.showToast({ title: `${getSourceTag(src)}链接已复制，去浏览器打开`, icon: 'none' });
    },
  });
}

/** 格式化费用明细 */
function formatFeeDetail(item) {
  const fee_a = item.airport_fee || 50;
  const fee_f = item.fuel_tax || 50;
  return `票¥${Math.round(item.ticket_price)} + 机建¥${fee_a} + 燃油¥${fee_f}`;
}

module.exports = {
  formatPrice,
  formatTime,
  formatDate,
  getStopText,
  getStopClass,
  getSourceTag,
  formatFeeDetail,
  PLATFORMS,
  getPlatformInfo,
  getBookingUrl,
  bookFlight,
};
