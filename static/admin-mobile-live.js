/*
 * 管理端移动页面：这是实际数据页面，不是画布演示稿。
 * 桌面端继续使用原管理界面；小屏幕下由本文件把现有接口数据渲染成卡片。
 */
(function () {
  'use strict';

  var root = document.getElementById('mobile-admin-live');
  if (!root) return;

  var media = window.matchMedia('(max-width: 768px)');
  var bell = document.getElementById('bell-container');
  var bellHome = bell ? bell.parentNode : null;
  var bellNext = bell ? bell.nextSibling : null;
  var searchTimer = null;
  var examSearchTimer = null;
  var mobileExamRecords = [];
  var state = {
    tab: 'records',
    recordCompanyOpen: false,
    recordFiltersOpen: false,
    recordStatus: 'all',
    downloadOpen: false,
    pendingQuery: '',
    restoreQuery: '',
    examCompanyOpen: false,
    examFiltersOpen: false,
    examHistoryId: null
  };

  function isMobile() { return media.matches; }
  function esc(value) {
    if (typeof window.escapeHtml === 'function') return window.escapeHtml(String(value == null ? '' : value));
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (m) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m];
    });
  }
  function jsArg(value) {
    return JSON.stringify(value == null ? '' : String(value)).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  function icon(name) {
    var icons = {
      search: '<svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="6"></circle><path d="m16 16 4 4"></path></svg>',
      down: '<svg viewBox="0 0 24 24"><path d="m6 9 6 6 6-6"></path></svg>',
      filter: '<svg viewBox="0 0 24 24"><path d="M4 6h16M4 12h10M4 18h6"></path><circle cx="17" cy="12" r="2"></circle><circle cx="13" cy="18" r="2"></circle></svg>',
      download: '<svg viewBox="0 0 24 24"><path d="M12 3v12"></path><path d="m7 10 5 5 5-5"></path><path d="M5 21h14"></path></svg>',
      records: '<svg viewBox="0 0 24 24"><path d="M4 5h16v14H4z"></path><path d="M8 9h8M8 13h5"></path></svg>',
      users: '<svg viewBox="0 0 24 24"><circle cx="9" cy="8" r="3"></circle><path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6"></path><path d="M17 10a3 3 0 1 0-1.2-5.7M17 14c2.2.2 4 2.3 4 4.7"></path></svg>',
      restore: '<svg viewBox="0 0 24 24"><path d="M4 12a8 8 0 1 0 2.3-5.7"></path><path d="M4 4v5h5"></path></svg>',
      exam: '<svg viewBox="0 0 24 24"><rect x="5" y="3" width="14" height="18" rx="2"></rect><path d="M8 8h8M8 12h8M8 16h4"></path></svg>',
      settings: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.1 2.1-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5v.2h-3v-.2a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1-2.1-2.1.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H5.3v-3h.2a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.9l-.1-.1 2.1-2.1.1.1a1.7 1.7 0 0 0 1.9.3 1.7 1.7 0 0 0 1-1.5v-.2h3v.2a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1 2.1 2.1-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.5 1h.2v3h-.2a1.7 1.7 0 0 0-1.5 1Z"></path></svg>',
      arrow: '<svg viewBox="0 0 24 24"><path d="m9 18 6-6-6-6"></path></svg>'
    };
    return icons[name] || '';
  }
  function getArray(name) {
    try { return Array.isArray(window[name]) ? window[name] : []; } catch (e) { return []; }
  }
  function getGlobalArray(identifier) {
    try {
      if (identifier === 'records') return typeof lastFilteredRecords !== 'undefined' && Array.isArray(lastFilteredRecords) ? lastFilteredRecords : [];
      if (identifier === 'restore') return typeof lastFilteredRestoreRecords !== 'undefined' && Array.isArray(lastFilteredRestoreRecords) ? lastFilteredRestoreRecords : [];
      if (identifier === 'users') return typeof filteredUsersList !== 'undefined' && Array.isArray(filteredUsersList) ? filteredUsersList : [];
    } catch (e) { /* page has not finished initialising yet */ }
    return [];
  }
  function isToday(value) {
    if (!value) return false;
    var date = new Date();
    var key = date.getFullYear() + '-' + String(date.getMonth() + 1).padStart(2, '0') + '-' + String(date.getDate()).padStart(2, '0');
    return String(value).slice(0, 10) === key;
  }
  function displayTime(value) {
    try { return typeof window.formatTime === 'function' ? window.formatTime(value) : String(value || '--'); } catch (e) { return String(value || '--'); }
  }
  function displayDateTime(value) {
    try { return typeof window.formatDateTime === 'function' ? window.formatDateTime(value) : String(value || '--'); } catch (e) { return String(value || '--'); }
  }
  function photoUrl(path) {
    if (!path) return '';
    return '/' + String(path).replace(/\\/g, '/').replace(/^\/+/, '');
  }
  function initials(value) { return String(value || '?').trim().slice(0, 1) || '?'; }
  function selectedRecord(id) {
    try { return typeof selectedRecordsMap !== 'undefined' && selectedRecordsMap.has(id); } catch (e) { return false; }
  }
  function selectedRestore(id) {
    try { return typeof selectedRestoreRecordsMap !== 'undefined' && selectedRestoreRecordsMap.has(id); } catch (e) { return false; }
  }
  function recordsForMobile() {
    var list = getGlobalArray('records').slice();
    list.sort(function (a, b) {
      if ((a.is_gate_downloaded || 0) !== (b.is_gate_downloaded || 0)) return (a.is_gate_downloaded || 0) - (b.is_gate_downloaded || 0);
      return new Date(String(b.created_at || '').replace(' ', 'T')) - new Date(String(a.created_at || '').replace(' ', 'T'));
    });
    if (state.recordStatus === 'today') list = list.filter(function (r) { return isToday(r.created_at); });
    if (state.recordStatus === 'pending') list = list.filter(function (r) { return Number(r.is_gate_downloaded) !== 1; });
    if (state.recordStatus === 'downloaded') list = list.filter(function (r) { return Number(r.is_gate_downloaded) === 1; });
    return list;
  }
  function rootHeader() {
    return '<header class="app-top">' +
      '<div class="status-row"><span>管理端</span><span>培训信息系统</span></div>' +
      '<div class="top-row"><div><h1 class="app-title">培训管理</h1><p class="app-subtitle">人员记录、注册管理与考试信息</p></div><div id="mobile-live-bell-slot" class="bell-slot"></div></div>' +
      '</header>';
  }
  function recordPanel() {
    var records = recordsForMobile();
    var total = 0;
    var pending = 0;
    try { total = typeof recordsTotal !== 'undefined' ? recordsTotal : records.length; } catch (e) { total = records.length; }
    pending = records.filter(function (r) { return Number(r.is_gate_downloaded) !== 1; }).length;
    var companies = [];
    try { companies = typeof recordsAllCompanies !== 'undefined' && Array.isArray(recordsAllCompanies) ? recordsAllCompanies : []; } catch (e) { companies = []; }
    var companyButtons = [''].concat(companies).map(function (company) {
      return '<button type="button" onclick="mobileAdminSelectRecordCompany(' + jsArg(company) + ')">' + esc(company || '全部培训单位') + '</button>';
    }).join('');
    var query = '';
    try { query = typeof filterName !== 'undefined' ? filterName : ''; } catch (e) { query = ''; }
    var selectedCompany = '';
    try { selectedCompany = typeof filterCompany !== 'undefined' ? filterCompany : ''; } catch (e) { selectedCompany = ''; }
    var status = function (key, text) { return '<button type="button" class="filter-option ' + (state.recordStatus === key ? 'is-selected' : '') + '" onclick="mobileAdminSetRecordStatus(\'' + key + '\')">' + text + '</button>'; };
    return '<section class="tab-panel ' + (state.tab === 'records' ? 'is-active' : '') + '" data-panel="records">' +
      '<div class="summary-grid"><article class="summary-card primary"><div class="summary-label">培训记录</div><div class="summary-value">' + total + '</div><div class="summary-note">完整保留历史培训</div></article><article class="summary-card"><div class="summary-label">本页待下载</div><div class="summary-value">' + pending + '</div><div class="summary-note">默认已勾选，可逐个调整</div></article></div>' +
      '<div class="page-toolbar"><div class="company-combobox"><span class="search-glyph">' + icon('search') + '</span>' +
        '<input type="search" id="live-record-search" value="' + esc(query) + '" placeholder="姓名、单位、身份证、手机号" oninput="mobileAdminRecordSearch(this.value)">' +
        '<button class="company-toggle" type="button" aria-label="选择培训单位" onclick="mobileAdminToggleRecordCompany(event)">' + icon('down') + '</button>' +
        '<div class="company-options ' + (state.recordCompanyOpen ? 'is-open' : '') + '">' + companyButtons + '</div></div>' +
      '<button class="toolbar-btn" type="button" aria-label="筛选培训记录" onclick="mobileAdminToggleRecordFilters(event)">' + icon('filter') + '</button>' +
      '<div class="download-wrap"><button class="toolbar-btn" type="button" aria-label="下载所选人员" onclick="mobileAdminToggleDownload(event)">' + icon('download') + '</button>' +
        '<div class="download-chooser ' + (state.downloadOpen ? 'is-open' : '') + '"><h3>选择下载内容</h3><p>可按需要只下载一种内容。</p><div class="download-options"><button type="button" onclick="mobileAdminExport(\'excel\')">下载 Excel</button><button type="button" onclick="mobileAdminExport(\'csv\')">下载 CSV</button><button type="button" onclick="mobileAdminExport(\'photos\')">下载照片包</button></div></div></div></div>' +
      '<div class="filter-panel ' + (state.recordFiltersOpen ? 'is-open' : '') + '"><div class="filter-group"><span class="filter-group-label">下载状态</span><div class="filter-options">' + status('all', '全部') + status('pending', '未下载') + status('downloaded', '已下载') + status('today', '今日录入') + '</div></div>' +
        '<div class="filter-panel-actions"><button type="button" onclick="mobileAdminClearRecordFilters()">重置</button><button type="button" class="apply-filter" onclick="mobileAdminToggleRecordFilters()">完成</button></div></div>' +
      '<div class="section-heading"><h3>' + esc(selectedCompany || '全部培训单位') + '</h3><span>当前 ' + records.length + ' 人</span></div><div class="record-stack">' +
      (records.length ? records.map(recordCard).join('') : '<div class="empty-state">没有符合条件的培训记录</div>') + '</div>' + recordPager() + '</section>';
  }
  function recordCard(r) {
    var downloaded = Number(r.is_gate_downloaded) === 1;
    var image = photoUrl(r.photo_path);
    var checked = selectedRecord(r.id);
    return '<article class="record-card ' + (downloaded ? 'is-downloaded' : '') + ' ' + (checked ? 'is-selected' : '') + '"><div class="record-head"><input class="record-select" type="checkbox" ' + (checked ? 'checked' : '') + ' aria-label="选择' + esc(r.name) + '" onchange="mobileAdminToggleRecord(' + Number(r.id) + ',this.checked)"><div class="person-line"><div class="person">' +
      (image ? '<button class="photo-thumb" type="button" aria-label="放大' + esc(r.name) + '照片" onclick="zoomImage(' + jsArg(image) + ')"><img src="' + esc(image) + '" alt="' + esc(r.name) + '照片"></button>' : '<div class="avatar">' + esc(initials(r.name)) + '</div>') +
      '<div><div class="person-name">' + esc(r.name) + '</div><div class="person-meta">' + esc(r.gender || '--') + ' · ' + esc(r.age || '--') + '岁 · ' + esc(r.education || '--') + '</div></div></div><span class="state-pill ' + (downloaded ? '' : 'warning') + '">' + (downloaded ? '已下载' : '待下载') + '</span></div></div>' +
      '<div class="record-details"><div><span>工作单位</span><strong>' + esc(r.company || '暂无单位') + '</strong></div><div><span>联系电话</span><strong>' + esc(r.phone || '--') + '</strong></div><div><span>身份证号</span><strong>' + esc(r.id_card || '--') + '</strong></div><div><span>岗位 / 区域</span><strong>' + esc(r.job || '--') + ' · ' + esc(r.region_auth || '--') + '</strong></div>' +
      (r.remark ? '<div class="wide"><span>备注</span><strong>' + esc(r.remark) + '</strong></div>' : '') + '</div>' +
      '<div class="card-footer"><span class="record-time">录入 ' + esc(displayTime(r.created_at)) + '</span><span><button class="small-action" type="button" onclick="openRecordDetail(' + Number(r.id) + ')">详情</button> <button class="small-action" type="button" onclick="deleteRecord(' + Number(r.id) + ')">删除</button></span></div></article>';
  }
  function recordPager() {
    var page = 1, total = 0, limit = 20;
    try { page = recordsPage; total = recordsTotal; limit = recordsLimit; } catch (e) { return ''; }
    var pages = Math.ceil(total / limit) || 1;
    if (pages <= 1) return '';
    return '<div class="pager"><button type="button" ' + (page <= 1 ? 'disabled' : '') + ' onclick="changeRecordsPage(' + (page - 1) + ')">上一页</button><span>第 ' + page + ' / ' + pages + ' 页 · 共 ' + total + ' 条</span><button type="button" ' + (page >= pages ? 'disabled' : '') + ' onclick="changeRecordsPage(' + (page + 1) + ')">下一页</button></div>';
  }
  function pendingPanel() {
    var query = String(state.pendingQuery || '').trim().toLowerCase();
    var users = getGlobalArray('users').filter(function (u) {
      return !query || [u.username, u.real_name, u.company, u.phone].some(function (x) { return String(x || '').toLowerCase().indexOf(query) !== -1; });
    });
    return '<section class="tab-panel ' + (state.tab === 'pending' ? 'is-active' : '') + '" data-panel="pending">' +
      '<div class="sheet"><h3 class="sheet-title">注册用户管理</h3><div class="list-line"><div>这里仅展示已注册用户<small>允许、拒绝及其他审批统一在右上角铃铛处理。</small></div><span class="state-pill">' + users.length + ' 人</span></div></div>' +
      '<div class="page-toolbar"><div class="company-combobox"><span class="search-glyph">' + icon('search') + '</span><input type="search" value="' + esc(state.pendingQuery) + '" placeholder="搜索用户名、姓名、单位" oninput="mobileAdminPendingSearch(this.value)"></div></div>' +
      '<div class="record-stack">' + (users.length ? users.map(userCard).join('') : '<div class="empty-state">没有符合条件的注册用户</div>') + '</div></section>';
  }
  function userCard(u) {
    var status = u.status === 'approved' ? '已通过' : (u.status === 'rejected' ? '已拒绝' : '待审批');
    return '<article class="record-card"><div class="record-head"><div class="person-line"><div class="person"><div class="avatar">' + esc(initials(u.real_name || u.username)) + '</div><div><div class="person-name">' + esc(u.real_name || u.username) + '</div><div class="person-meta">账号：' + esc(u.username || '--') + '</div></div></div><span class="state-pill ' + (u.status === 'pending' ? 'warning' : '') + '">' + status + '</span></div></div>' +
      '<div class="record-details"><div class="wide"><span>工作单位</span><strong>' + esc(u.company || '--') + '</strong></div><div><span>联系电话</span><strong>' + esc(u.phone || u.username || '--') + '</strong></div><div><span>注册时间</span><strong>' + esc(displayTime(u.created_at)) + '</strong></div></div>' +
      '<div class="card-footer"><span class="record-time">审批请点右上角铃铛</span><button class="small-action" type="button" onclick="openEditUserModal(' + Number(u.id) + ',' + jsArg(u.username) + ',' + jsArg(u.real_name) + ',' + jsArg(u.company) + ')">编辑</button></div></article>';
  }
  function restorePanel() {
    var query = String(state.restoreQuery || '').trim().toLowerCase();
    var records = getGlobalArray('restore').filter(function (r) {
      return !query || [r.name, r.company, r.phone, r.id_card].some(function (x) { return String(x || '').toLowerCase().indexOf(query) !== -1; });
    });
    return '<section class="tab-panel ' + (state.tab === 'restore' ? 'is-active' : '') + '" data-panel="restore">' +
      '<div class="sheet"><h3 class="sheet-title">门禁恢复管理</h3><div class="list-line"><div>待恢复人员默认已勾选<small>已恢复下载的人员会变灰，仍保留历史。</small></div><button class="small-action" type="button" onclick="exportRestoreData()">下载所选</button></div></div>' +
      '<div class="page-toolbar"><div class="company-combobox"><span class="search-glyph">' + icon('search') + '</span><input type="search" value="' + esc(state.restoreQuery) + '" placeholder="姓名、单位、身份证、手机号" oninput="mobileAdminRestoreSearch(this.value)"></div></div>' +
      '<div class="record-stack">' + (records.length ? records.map(restoreCard).join('') : '<div class="empty-state">当前没有门禁恢复记录</div>') + '</div></section>';
  }
  function restoreCard(r) {
    var downloaded = Number(r.is_restore_downloaded) === 1;
    var image = photoUrl(r.photo_path);
    var checked = selectedRestore(r.id);
    return '<article class="record-card ' + (downloaded ? 'is-downloaded' : '') + ' ' + (checked ? 'is-selected' : '') + '"><div class="record-head"><input class="record-select" type="checkbox" ' + (checked ? 'checked' : '') + ' onchange="mobileAdminToggleRestore(' + Number(r.id) + ',this.checked)"><div class="person-line"><div class="person">' +
      (image ? '<button class="photo-thumb" type="button" onclick="zoomImage(' + jsArg(image) + ')"><img src="' + esc(image) + '" alt="' + esc(r.name) + '照片"></button>' : '<div class="avatar">' + esc(initials(r.name)) + '</div>') + '<div><div class="person-name">' + esc(r.name) + '</div><div class="person-meta">' + esc(r.gender || '--') + ' · ' + esc(r.age || '--') + '岁</div></div></div><span class="state-pill ' + (downloaded ? '' : 'warning') + '">' + (downloaded ? '已下载' : '待恢复') + '</span></div></div>' +
      '<div class="record-details"><div><span>工作单位</span><strong>' + esc(r.company || '--') + '</strong></div><div><span>联系电话</span><strong>' + esc(r.phone || '--') + '</strong></div><div class="wide"><span>身份证号</span><strong>' + esc(r.id_card || '--') + '</strong></div></div><div class="card-footer"><span class="record-time">提交 ' + esc(displayTime(r.created_at)) + '</span><button class="small-action" type="button" onclick="deleteRestoreGate(' + Number(r.id) + ')">删除</button></div></article>';
  }
  function examPanel() {
    var company = '', subject = '', query = '';
    try { company = document.getElementById('exam-filter-company').value || ''; } catch (e) { /* ignore */ }
    try { subject = document.getElementById('exam-filter-type').value || ''; } catch (e) { /* ignore */ }
    try { query = typeof examFilterName !== 'undefined' ? examFilterName : ''; } catch (e) { query = ''; }
    var companies = [];
    try { companies = typeof allCompanies !== 'undefined' && Array.isArray(allCompanies) ? allCompanies : []; } catch (e) { companies = []; }
    var subjects = [];
    var subjectSelect = document.getElementById('exam-filter-type');
    if (subjectSelect) subjects = Array.prototype.map.call(subjectSelect.options, function (option) { return option.value; }).filter(Boolean);
    var recordCount = mobileExamRecords.length;
    var passCount = mobileExamRecords.filter(function (item) { return Number(item.score) >= 90; }).length;
    var companyOptions = [''].concat(companies).map(function (item) { return '<button type="button" onclick="mobileAdminSelectExamCompany(' + jsArg(item) + ')">' + esc(item || '全部工作单位') + '</button>'; }).join('');
    var subjectOptions = [''].concat(subjects).map(function (item) { return '<button type="button" class="filter-option ' + (subject === item ? 'is-selected' : '') + '" onclick="mobileAdminSelectExamSubject(' + jsArg(item) + ')">' + esc(item || '全部科目') + '</button>'; }).join('');
    return '<section class="tab-panel ' + (state.tab === 'exam' ? 'is-active' : '') + '" data-panel="exam">' +
      '<div class="sheet exam-summary"><div class="score-ring">' + (recordCount ? Math.round(passCount * 100 / recordCount) : 0) + '%</div><div><h3 class="sheet-title">考试信息</h3><div class="summary-note">共 ' + recordCount + ' 人，合格 ' + passCount + ' 人；成绩以最后一次考试为准。</div></div></div>' +
      '<div class="page-toolbar"><div class="company-combobox"><span class="search-glyph">' + icon('search') + '</span><input type="search" value="' + esc(query) + '" placeholder="姓名、单位、身份证、手机号" oninput="mobileAdminExamSearch(this.value)"><button class="company-toggle" type="button" onclick="mobileAdminToggleExamCompany(event)">' + icon('down') + '</button><div class="company-options ' + (state.examCompanyOpen ? 'is-open' : '') + '">' + companyOptions + '</div></div><button class="toolbar-btn" type="button" aria-label="筛选考试信息" onclick="mobileAdminToggleExamFilters(event)">' + icon('filter') + '</button></div>' +
      '<div class="filter-panel ' + (state.examFiltersOpen ? 'is-open' : '') + '"><div class="filter-group"><span class="filter-group-label">考试科目</span><div class="filter-options">' + subjectOptions + '</div></div><div class="filter-panel-actions"><button type="button" onclick="mobileAdminClearExamFilters()">重置</button><button type="button" class="apply-filter" onclick="mobileAdminToggleExamFilters()">完成</button></div></div>' +
      '<div class="section-heading"><h3>' + esc(company || '全部工作单位') + '</h3><span>成绩为最后一次</span></div><div class="record-stack">' +
      (mobileExamRecords.length ? mobileExamRecords.map(examCard).join('') : '<div class="empty-state">没有符合条件的考试记录</div>') + '</div>' + examPager() + '</section>';
  }
  function examCard(record) {
    var pass = Number(record.score) >= 90;
    var history = Array.isArray(record.history) ? record.history : [];
    var multiple = history.length > 1;
    var expanded = multiple && state.examHistoryId === record.id;
    var today = isToday(record.created_at);
    var historyHtml = multiple ? '<div class="exam-history"><div class="exam-history-title">历史考试记录（' + history.length + ' 次）</div>' + history.map(function (item, index) {
      var itemPass = Number(item.score) >= 90;
      return '<div class="exam-attempt"><div><strong>第 ' + (index + 1) + ' 次 · <span class="' + (itemPass ? 'exam-pass' : 'exam-fail') + '">' + esc(item.score) + ' 分</span></strong><span>' + esc(displayDateTime(item.created_at)) + ' · 用时 ' + esc(item.duration || '--') + '</span></div><button class="exam-detail-button" type="button" onclick="event.stopPropagation();viewExamDetail(' + Number(item.id) + ')">考试详情</button></div>';
    }).join('') + '</div>' : '';
    var toggle = multiple ? ' onclick="mobileAdminToggleExamHistory(' + Number(record.id) + ')"' : '';
    return '<article class="record-card exam-card ' + (today ? 'today' : 'past') + ' ' + (expanded ? 'is-expanded' : '') + '"><button class="exam-card-toggle" type="button"' + toggle + '><div class="person-line"><div><div class="person-name">' + esc(record.name) + (multiple ? ' <small>（考试 ' + history.length + ' 次）</small>' : '') + '</div><div class="person-meta">' + esc(record.company || '--') + ' · ' + esc(record.exam_type || '--') + '</div></div><span class="state-pill exam-result ' + (pass ? 'high' : 'low') + '">' + esc(record.score) + ' 分</span></div><div class="exam-card-meta"><span class="' + (today ? 'today-label' : '') + '">' + (today ? '今日考试' : '历史考试') + ' · ' + esc(displayTime(record.created_at)) + '</span><span>' + (multiple ? (expanded ? '收起历史' : '查看历史') : '一次通过') + '</span></div></button><div class="card-footer"><span class="record-time">' + (pass ? '成绩合格' : '成绩未达标') + '</span><button class="exam-detail-button" type="button" onclick="viewExamDetail(' + Number(record.id) + ')">考试详情</button></div>' + historyHtml + '</article>';
  }
  function examPager() {
    var page = 1, total = 0, limit = 20;
    try { page = examRecordsPage; total = examRecordsTotal; limit = examRecordsLimit; } catch (e) { return ''; }
    var pages = Math.ceil(total / limit) || 1;
    if (pages <= 1) return '';
    return '<div class="pager"><button type="button" ' + (page <= 1 ? 'disabled' : '') + ' onclick="changeExamPage(' + (page - 1) + ')">上一页</button><span>第 ' + page + ' / ' + pages + ' 页 · 共 ' + total + ' 条</span><button type="button" ' + (page >= pages ? 'disabled' : '') + ' onclick="changeExamPage(' + (page + 1) + ')">下一页</button></div>';
  }
  function settingsPanel() {
    var start = '--', end = '--', regions = '未配置';
    try { start = document.getElementById('cfg-start-time').value || '--'; end = document.getElementById('cfg-end-time').value || '--'; } catch (e) { /* configuration is still loading */ }
    try { regions = typeof configuredRegions !== 'undefined' && configuredRegions.length ? configuredRegions.join('、') : regions; } catch (e) { /* configuration is still loading */ }
    return '<section class="tab-panel ' + (state.tab === 'settings' ? 'is-active' : '') + '" data-panel="settings">' +
      '<div class="sheet settings-summary"><h3 class="sheet-title">系统配置</h3>' +
      '<button class="list-line settings-summary-line" type="button" onclick="mobileAdminOpenLegacyConfig(\'core\')"><div>考试时间<small>' + esc(start) + ' – ' + esc(end) + '</small></div><span class="value-tag">编辑</span></button>' +
      '<button class="list-line settings-summary-line" type="button" onclick="mobileAdminOpenLegacyConfig(\'core\')"><div>开放区域<small>' + esc(regions) + '</small></div><span class="value-tag">编辑</span></button></div>' +
      settingsRow('培训单位', '维护可选单位和归属信息', 'core') + settingsRow('考试题库', '科目、题目、导入与更新', 'bank') + settingsRow('二级管理员', '账号、权限与状态', 'password', 'sub-admins-section') + settingsRow('修改密码', '更新当前管理员密码', 'password') + '</section>';
  }
  function settingsRow(title, detail, section, anchor) {
    var args = '\'' + section + '\'' + (anchor ? ',\'' + anchor + '\'' : '');
    return '<button class="settings-row" type="button" onclick="mobileAdminOpenLegacyConfig(' + args + ')"><span class="settings-icon">' + icon('settings') + '</span><span class="settings-copy"><strong>' + title + '</strong><span>' + detail + '</span></span>' + icon('arrow') + '</button>';
  }
  function nav() {
    var tabs = [['records', '记录', 'records'], ['pending', '注册', 'users'], ['restore', '恢复', 'restore'], ['exam', '考试', 'exam'], ['settings', '设置', 'settings']];
    return '<nav class="app-nav" aria-label="移动管理导航">' + tabs.map(function (tab) { return '<button class="nav-item ' + (state.tab === tab[0] ? 'is-active' : '') + '" type="button" onclick="mobileAdminGo(\'' + tab[0] + '\')">' + icon(tab[2]) + '<span>' + tab[1] + '</span></button>'; }).join('') + '</nav>';
  }
  function render() {
    if (!isMobile()) return;
    root.innerHTML = '<div class="phone">' + rootHeader() + '<main class="content">' + recordPanel() + pendingPanel() + restorePanel() + examPanel() + settingsPanel() + '</main>' + nav() + '</div>';
    moveBell(true);
  }
  function moveBell(toMobile) {
    if (!bell) return;
    var slot = root.querySelector('#mobile-live-bell-slot');
    if (toMobile && slot && bell.parentNode !== slot) slot.appendChild(bell);
    if (!toMobile && bellHome && bell.parentNode !== bellHome) bellHome.insertBefore(bell, bellNext);
  }
  function loadCurrentTab() {
    if (state.tab === 'records' && typeof window.loadRecords === 'function') window.loadRecords();
    if (state.tab === 'pending' && typeof window.loadPendingUsers === 'function') window.loadPendingUsers();
    if (state.tab === 'restore' && typeof window.loadRestoreRecords === 'function') window.loadRestoreRecords();
    if (state.tab === 'exam' && typeof window.loadExamRecords === 'function') { window.loadExamRecords(); if (typeof window.loadExamCompanyOptions === 'function') window.loadExamCompanyOptions(); }
  }
  function activate() {
    document.body.classList.add('mobile-admin-live-enabled');
    render();
    loadCurrentTab();
  }
  function deactivate() {
    document.body.classList.remove('mobile-admin-live-enabled');
    moveBell(false);
  }
  function onBreakpointChange() { if (isMobile()) activate(); else deactivate(); }

  function wrap(name, after) {
    var original = window[name];
    if (typeof original !== 'function' || original.__mobileLiveWrapped) return;
    function wrapped() {
      var result = original.apply(this, arguments);
      after.apply(this, arguments);
      return result;
    }
    wrapped.__mobileLiveWrapped = true;
    window[name] = wrapped;
  }
  wrap('renderRecords', function () { if (isMobile() && state.tab === 'records') render(); });
  wrap('renderPendingUsers', function () { if (isMobile() && state.tab === 'pending') render(); });
  wrap('renderRestoreRecords', function () { if (isMobile() && state.tab === 'restore') render(); });
  wrap('renderExamRecords', function (records) { mobileExamRecords = Array.isArray(records) ? records : []; if (isMobile() && state.tab === 'exam') render(); });
  wrap('switchAdminTab', function (tab) { if (!isMobile()) return; state.tab = tab === 'config' ? 'settings' : tab; render(); });

  window.mobileAdminGo = function (tab) {
    state.tab = tab;
    state.downloadOpen = false;
    if (tab === 'settings') { render(); return; }
    if (typeof window.switchAdminTab === 'function') window.switchAdminTab(tab);
    else { render(); loadCurrentTab(); }
  };
  window.mobileAdminToggleRecordCompany = function (event) { if (event) event.stopPropagation(); state.recordCompanyOpen = !state.recordCompanyOpen; state.downloadOpen = false; render(); };
  window.mobileAdminSelectRecordCompany = function (company) {
    state.recordCompanyOpen = false;
    try { filterCompany = company; recordsPage = 1; document.getElementById('filter-company').value = company; } catch (e) { /* page loading */ }
    if (typeof window.loadRecords === 'function') window.loadRecords(); else render();
  };
  window.mobileAdminRecordSearch = function (value) {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(function () {
      try { filterName = value; recordsPage = 1; document.getElementById('filter-name').value = value; } catch (e) { /* page loading */ }
      if (typeof window.loadRecords === 'function') window.loadRecords();
    }, 260);
  };
  window.mobileAdminToggleRecordFilters = function (event) { if (event) event.stopPropagation(); state.recordFiltersOpen = !state.recordFiltersOpen; state.downloadOpen = false; render(); };
  window.mobileAdminSetRecordStatus = function (status) { state.recordStatus = status; render(); };
  window.mobileAdminClearRecordFilters = function () {
    state.recordStatus = 'all'; state.recordFiltersOpen = false;
    try { filterName = ''; filterCompany = ''; recordsPage = 1; document.getElementById('filter-name').value = ''; document.getElementById('filter-company').value = ''; } catch (e) { /* ignore */ }
    if (typeof window.loadRecords === 'function') window.loadRecords(); else render();
  };
  window.mobileAdminToggleDownload = function (event) { if (event) event.stopPropagation(); state.downloadOpen = !state.downloadOpen; state.recordCompanyOpen = false; render(); };
  window.mobileAdminExport = function (format) { state.downloadOpen = false; render(); if (typeof window.exportData === 'function') window.exportData(format); };
  window.mobileAdminToggleRecord = function (id, checked) { if (typeof window.handleSingleCheckboxChange === 'function') window.handleSingleCheckboxChange({ checked: checked }, id); else render(); };
  window.mobileAdminPendingSearch = function (value) { state.pendingQuery = value; render(); };
  window.mobileAdminRestoreSearch = function (value) { state.restoreQuery = value; render(); };
  window.mobileAdminToggleRestore = function (id, checked) { if (typeof window.handleSingleRestoreCheckboxChange === 'function') window.handleSingleRestoreCheckboxChange({ checked: checked }, id); else render(); };
  window.mobileAdminToggleExamCompany = function (event) { if (event) event.stopPropagation(); state.examCompanyOpen = !state.examCompanyOpen; render(); };
  window.mobileAdminSelectExamCompany = function (company) {
    state.examCompanyOpen = false;
    var input = document.getElementById('exam-filter-company');
    if (input) input.value = company;
    try { examRecordsPage = 1; } catch (e) { /* ignore */ }
    if (typeof window.loadExamRecords === 'function') window.loadExamRecords(); else render();
  };
  window.mobileAdminExamSearch = function (value) {
    clearTimeout(examSearchTimer);
    examSearchTimer = setTimeout(function () {
      try { examFilterName = value; examRecordsPage = 1; document.getElementById('exam-filter-name').value = value; } catch (e) { /* ignore */ }
      if (typeof window.loadExamRecords === 'function') window.loadExamRecords();
    }, 260);
  };
  window.mobileAdminToggleExamFilters = function (event) { if (event) event.stopPropagation(); state.examFiltersOpen = !state.examFiltersOpen; render(); };
  window.mobileAdminSelectExamSubject = function (subject) {
    var select = document.getElementById('exam-filter-type');
    if (select) select.value = subject;
    try { examRecordsPage = 1; } catch (e) { /* ignore */ }
    if (typeof window.loadExamRecords === 'function') window.loadExamRecords(); else render();
  };
  window.mobileAdminClearExamFilters = function () {
    state.examFiltersOpen = false;
    var company = document.getElementById('exam-filter-company');
    var subject = document.getElementById('exam-filter-type');
    var search = document.getElementById('exam-filter-name');
    if (company) company.value = '';
    if (subject) subject.value = '';
    if (search) search.value = '';
    try { examFilterName = ''; examRecordsPage = 1; } catch (e) { /* ignore */ }
    if (typeof window.loadExamRecords === 'function') window.loadExamRecords(); else render();
  };
  window.mobileAdminToggleExamHistory = function (id) { state.examHistoryId = state.examHistoryId === id ? null : id; render(); };
  window.mobileAdminOpenLegacyConfig = function (section, anchor) {
    deactivate();
    if (typeof window.switchAdminTab === 'function') window.switchAdminTab('config');
    if (typeof window.switchConfigSubTab === 'function') window.switchConfigSubTab(section);
    if (anchor) setTimeout(function () { var target = document.getElementById(anchor); if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' }); }, 80);
    var button = document.getElementById('mobile-admin-return');
    if (!button) {
      button = document.createElement('button');
      button.id = 'mobile-admin-return';
      button.type = 'button';
      button.textContent = '返回手机管理';
      button.onclick = function () { activate(); button.remove(); };
      document.body.appendChild(button);
    }
  };

  document.addEventListener('click', function (event) {
    if (!isMobile()) return;
    var changed = false;
    if (!event.target.closest('.company-combobox') && (state.recordCompanyOpen || state.examCompanyOpen)) { state.recordCompanyOpen = false; state.examCompanyOpen = false; changed = true; }
    if (!event.target.closest('.download-wrap') && state.downloadOpen) { state.downloadOpen = false; changed = true; }
    if (changed) render();
  });
  if (media.addEventListener) media.addEventListener('change', onBreakpointChange);
  else media.addListener(onBreakpointChange);
  onBreakpointChange();
}());
