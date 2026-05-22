App({
  globalData: {
    apiBaseUrl: '',
    tunnelUrl: '',
    origin: '深圳',
    destination: '北京',
    dateFrom: '2026-06-15',
    dateTo: '2026-06-23',
    maxPrice: 2000,
    directions: [
      { origin: '深圳', destination: '北京', label: '深圳→北京' },
      { origin: '北京', destination: '深圳', label: '北京→深圳' },
    ],
    currentDirection: 0,
  },
  onLaunch() {
    wx.cloud.init({
      env: 'cloudbase-d7g70bhvj07f8e6dd',
    });
    console.log('小程序启动，云开发已初始化');
  },
  /** 切换方向 */
  switchDirection() {
    const g = this.globalData;
    const dirs = g.directions;
    const nextIdx = (g.currentDirection + 1) % dirs.length;
    g.currentDirection = nextIdx;
    g.origin = dirs[nextIdx].origin;
    g.destination = dirs[nextIdx].destination;
    return dirs[nextIdx];
  },
});
