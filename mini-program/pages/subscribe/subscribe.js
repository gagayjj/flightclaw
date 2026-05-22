const app = getApp();

Page({
  data: {
    directionLabel: '深圳↔北京',
    origin: '深圳',
    destination: '北京',
  },

  onShow() {
    const g = app.globalData;
    const dir = g.directions[g.currentDirection];
    this.setData({
      directionLabel: dir ? dir.label : `${g.origin}→${g.destination}`,
      origin: g.origin,
      destination: g.destination,
    });
  },
});
