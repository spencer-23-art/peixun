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
    composing: { record: false, exam: false, pending: false, restore: false },
    pendingQuery: '',
    pendingCompanyOpen: false,
    pendingCompany: '',
    restoreQuery: '',
    examCompanyOpen: false,
    examFiltersOpen: false,
    examHistoryId: null,
    settingsView: 'home',
    settings: {
      config: null,
      subjects: null,
      admins: null,
      blacklist: null,
      blacklistQuery: '',
      notice: '',
      error: '',
      busy: false,
      adminEditor: null,
      cleanupStart: '',
      cleanupEnd: '',
      cleanupPreview: null,
      cleanupResult: null
    }
  };

  function isMobile() { return media.matches; }
  function isPrimaryAdmin() {
    try { return String(getSessionItem('username') || '').trim() === 'admin'; } catch (e) { return false; }
  }
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
      logout: '<svg viewBox="0 0 24 24"><path d="M10 17l5-5-5-5"></path><path d="M15 12H3"></path><path d="M21 19V5a2 2 0 0 0-2-2h-7"></path></svg>',
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
    var specialWorkEnabled = Boolean(state.settings.config && state.settings.config.special_work_enabled);
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
        '<input type="search" id="live-record-search" value="' + esc(query) + '" placeholder="姓名、单位、身份证、手机号" oncompositionstart="mobileAdminCompositionStart(\'record\')" oncompositionend="mobileAdminCompositionEnd(\'record\',this.value)" oninput="mobileAdminRecordSearch(this.value,event)">' +
        '<button class="company-toggle" type="button" aria-label="选择培训单位" onclick="mobileAdminToggleRecordCompany(event)">' + icon('down') + '</button>' +
        '<div class="company-options ' + (state.recordCompanyOpen ? 'is-open' : '') + '">' + companyButtons + '</div></div>' +
      '<button class="toolbar-btn" type="button" aria-label="筛选培训记录" onclick="mobileAdminToggleRecordFilters(event)">' + icon('filter') + '</button>' +
      '<div class="download-wrap"><button class="toolbar-btn" type="button" aria-label="下载所选人员" onclick="mobileAdminToggleDownload(event)">' + icon('download') + '</button>' +
        '<div class="download-chooser ' + (state.downloadOpen ? 'is-open' : '') + '"><h3>选择下载内容</h3><p>可按需要只下载一种内容。</p><div class="download-options"><button type="button" onclick="mobileAdminExport(\'excel\')">下载 Excel</button><button type="button" onclick="mobileAdminExport(\'csv\')">下载 CSV</button><button type="button" onclick="mobileAdminExport(\'photos\')">下载照片包</button>' + (specialWorkEnabled ? '<button type="button" onclick="mobileAdminExport(\'special_work\')">下载特殊工种证件</button>' : '') + '</div></div></div></div>' +
      '<div class="filter-panel ' + (state.recordFiltersOpen ? 'is-open' : '') + '"><div class="filter-group"><span class="filter-group-label">下载状态</span><div class="filter-options">' + status('all', '全部') + status('pending', '未下载') + status('downloaded', '已下载') + status('today', '今日录入') + '</div></div>' +
        '<div class="filter-panel-actions"><button type="button" onclick="mobileAdminClearRecordFilters()">重置</button><button type="button" class="apply-filter" onclick="mobileAdminToggleRecordFilters()">完成</button></div></div>' +
      '<div class="section-heading"><h3>' + esc(selectedCompany || '全部培训单位') + '</h3><span>当前 ' + records.length + ' 人</span></div><div class="record-stack">' +
      (records.length ? records.map(recordCard).join('') : '<div class="empty-state">没有符合条件的培训记录</div>') + '</div>' + recordPager() + '</section>';
  }
  function recordCard(r) {
    var downloaded = Number(r.is_gate_downloaded) === 1;
    var image = photoUrl(r.photo_path);
    var checked = selectedRecord(r.id);
    var passed = Number(r.is_exam_passed) === 1;
    return '<article class="record-card ' + (downloaded ? 'is-downloaded' : '') + ' ' + (checked ? 'is-selected' : '') + '"><div class="record-head"><input class="record-select" type="checkbox" ' + (checked ? 'checked' : '') + ' aria-label="选择' + esc(r.name) + '" onchange="mobileAdminToggleRecord(' + Number(r.id) + ',this.checked)"><div class="person-line"><div class="person">' +
      (image ? '<button class="photo-thumb" type="button" aria-label="放大' + esc(r.name) + '照片" onclick="zoomImage(' + jsArg(image) + ')"><img src="' + esc(image) + '" alt="' + esc(r.name) + '照片"></button>' : '<div class="avatar">' + esc(initials(r.name)) + '</div>') +
      '<div><div class="person-name">' + esc(r.name) + '</div><div class="person-meta">' + esc(r.gender || '--') + ' · ' + esc(r.age || '--') + '岁 · ' + esc(r.education || '--') + '</div></div></div><span class="state-pill ' + (downloaded ? '' : 'warning') + '">' + (downloaded ? '已下载' : '待下载') + '</span></div></div>' +
      '<div class="record-details"><div><span>工作单位</span><strong>' + esc(r.company || '暂无单位') + '</strong></div><div><span>联系电话</span><strong>' + esc(r.phone || '--') + '</strong></div><div><span>身份证号</span><strong>' + esc(r.id_card || '--') + '</strong></div><div><span>岗位 / 区域</span><strong>' + esc(r.job || '--') + ' · ' + esc(r.region_auth || '--') + '</strong></div>' +
      (r.remark ? '<div class="wide"><span>备注</span><strong>' + esc(r.remark) + '</strong></div>' : '') + '</div>' +
      '<div class="card-footer"><span class="record-time">录入 ' + esc(displayTime(r.created_at)) + '</span><span>' + (passed ? '<span class="small-action" style="display:inline-flex; align-items:center; justify-content:center; padding:4px 8px; font-size:.78rem; color:#fff; background:#dc2626; border-color:#dc2626; cursor:default;">合格</span> ' : '') + '<button class="small-action" type="button" onclick="openRecordDetail(' + Number(r.id) + ')">详情</button> <button class="small-action" type="button" onclick="deleteRecord(' + Number(r.id) + ')">删除</button></span></div></article>';
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
    var selectedCompany = String(state.pendingCompany || '');
    var allUsers = getGlobalArray('users').filter(function (u) {
      return u && (u.status === 'approved' || u.status === 'disabled');
    });
    var companies = Array.from(new Set(allUsers.map(function (u) { return String(u.company || '').trim(); }).filter(Boolean))).sort();
    var companyOptions = [''].concat(companies).map(function (company) {
      return '<button type="button" onclick="mobileAdminSelectPendingCompany(' + jsArg(company) + ')">' + esc(company || '全部工作单位') + '</button>';
    }).join('');
    var users = allUsers.filter(function (u) {
      var companyMatch = !selectedCompany || String(u.company || '') === selectedCompany;
      return companyMatch && (!query || [u.username, u.real_name, u.company, u.phone].some(function (x) { return String(x || '').toLowerCase().indexOf(query) !== -1; }));
    });
    return '<section class="tab-panel ' + (state.tab === 'pending' ? 'is-active' : '') + '" data-panel="pending">' +
      '<div class="sheet"><h3 class="sheet-title">注册用户管理</h3><div class="list-line"><div>这里仅展示已通过或已停用的注册用户<small>待审核和已拒绝申请统一在右上角铃铛处理。</small></div><span class="state-pill">' + users.length + ' 人</span></div></div>' +
      '<div class="page-toolbar"><div class="company-combobox"><span class="search-glyph">' + icon('search') + '</span><input type="search" value="' + esc(state.pendingQuery) + '" placeholder="用户名、姓名、单位、手机号" oncompositionstart="mobileAdminCompositionStart(\'pending\')" oncompositionend="mobileAdminCompositionEnd(\'pending\',this.value)" oninput="mobileAdminPendingSearch(this.value,event)"><button class="company-toggle" type="button" aria-label="选择工作单位" onclick="mobileAdminTogglePendingCompany(event)">' + icon('down') + '</button><div class="company-options ' + (state.pendingCompanyOpen ? 'is-open' : '') + '">' + companyOptions + '</div></div></div>' +
      '<div class="section-heading"><h3>' + esc(selectedCompany || '全部工作单位') + '</h3><span>当前 ' + users.length + ' 人</span></div><div class="record-stack">' + (users.length ? users.map(userCard).join('') : '<div class="empty-state">没有符合条件的注册用户</div>') + '</div></section>';
  }
  function userCard(u) {
    var status = u.status === 'approved' ? '已通过' : (u.status === 'rejected' ? '已拒绝' : '待审批');
    if (u.status === 'disabled') status = '已停用';
    var registrationTime = u.created_at ? displayTime(u.created_at) : (u.first_record_at ? '历史账号 · 首次录入 ' + displayTime(u.first_record_at) : '历史账号（未留存时间）');
    var toggleLabel = u.status === 'disabled' ? '启用' : '停用';
    var toggleStatus = u.status === 'disabled' ? 'approved' : 'disabled';
    return '<article class="record-card"><div class="record-head"><div class="person-line"><div class="person"><div class="avatar">' + esc(initials(u.real_name || u.username)) + '</div><div><div class="person-name">' + esc(u.real_name || u.username) + '</div><div class="person-meta">账号：' + esc(u.username || '--') + '</div></div></div><span class="state-pill ' + (u.status === 'pending' ? 'warning' : '') + '">' + status + '</span></div></div>' +
      '<div class="record-details"><div class="wide"><span>工作单位</span><strong>' + esc(u.company || '--') + '</strong></div><div><span>联系电话</span><strong>' + esc(u.phone || u.username || '--') + '</strong></div><div><span>注册时间</span><strong>' + esc(registrationTime) + '</strong></div></div>' +
      '<div class="card-footer"><span class="record-time">审批请点右上角铃铛</span><span class="mobile-actions"><button class="small-action" type="button" onclick="openEditUserModal(' + Number(u.id) + ',' + jsArg(u.username) + ',' + jsArg(u.real_name) + ',' + jsArg(u.company) + ')">编辑</button><button class="small-action warning-action" type="button" onclick="mobileAdminSetUserStatus(' + Number(u.id) + ',' + jsArg(toggleStatus) + ')">' + toggleLabel + '</button><button class="small-action danger-action" type="button" onclick="handleDeleteUser(' + Number(u.id) + ')">删除</button></span></div></article>';
  }
  function restorePanel() {
    var query = String(state.restoreQuery || '').trim().toLowerCase();
    var records = getGlobalArray('restore').filter(function (r) {
      return !query || [r.name, r.company, r.phone, r.id_card].some(function (x) { return String(x || '').toLowerCase().indexOf(query) !== -1; });
    });
    return '<section class="tab-panel ' + (state.tab === 'restore' ? 'is-active' : '') + '" data-panel="restore">' +
      '<div class="sheet"><h3 class="sheet-title">门禁恢复管理</h3><div class="list-line"><div>待恢复人员默认已勾选<small>已恢复下载的人员会变灰，仍保留历史。</small></div><button class="small-action" type="button" onclick="exportRestoreData()">下载所选</button></div></div>' +
      '<div class="page-toolbar"><div class="company-combobox"><span class="search-glyph">' + icon('search') + '</span><input type="search" value="' + esc(state.restoreQuery) + '" placeholder="姓名、单位、身份证、手机号" oncompositionstart="mobileAdminCompositionStart(\'restore\')" oncompositionend="mobileAdminCompositionEnd(\'restore\',this.value)" oninput="mobileAdminRestoreSearch(this.value,event)"></div></div>' +
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
      '<div class="page-toolbar"><div class="company-combobox"><span class="search-glyph">' + icon('search') + '</span><input type="search" value="' + esc(query) + '" placeholder="姓名、单位、身份证、手机号" oncompositionstart="mobileAdminCompositionStart(\'exam\')" oncompositionend="mobileAdminCompositionEnd(\'exam\',this.value)" oninput="mobileAdminExamSearch(this.value,event)"><button class="company-toggle" type="button" onclick="mobileAdminToggleExamCompany(event)">' + icon('down') + '</button><div class="company-options ' + (state.examCompanyOpen ? 'is-open' : '') + '">' + companyOptions + '</div></div><button class="toolbar-btn" type="button" aria-label="筛选考试信息" onclick="mobileAdminToggleExamFilters(event)">' + icon('filter') + '</button></div>' +
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
    if (!isPrimaryAdmin()) {
      return '<section class="tab-panel ' + (state.tab === 'settings' ? 'is-active' : '') + '" data-panel="settings">' + settingsLogoutRow() + '</section>';
    }
    if (state.settingsView !== 'home') return settingsDetailPanel();
    var config = state.settings.config;
    var start = config ? config.start_time : '--';
    var end = config ? config.end_time : '--';
    var regions = config && config.regions.length ? config.regions.join('、') : '未配置';
    return '<section class="tab-panel ' + (state.tab === 'settings' ? 'is-active' : '') + '" data-panel="settings">' +
      settingsRow('系统配置', '考试 ' + start + ' – ' + end + ' · 区域 ' + regions, 'core') + settingsRow('培训单位', '查看当前单位与归属来源', 'units') + settingsRow('考试题库', '科目、题目、导入与更新', 'bank') + settingsRow('二级管理员', '账号、权限与状态', 'admins') + settingsRow('修改密码', '更新当前管理员密码', 'password') + settingsRow('测试功能', '特殊工种证件与黑名单开关', 'test') + (config && config.blacklist_enabled ? settingsRow('黑名单', '查看已拉黑人员并移除', 'blacklist') : '') + settingsRow('清理资料', '按日期清理录入档案与上传文件', 'cleanup') + settingsLogoutRow() + settingsNotice() + '</section>';
  }
  function settingsRow(title, detail, view) {
    return '<button class="settings-row" type="button" onclick="mobileAdminOpenSettings(\'' + view + '\')"><span class="settings-icon">' + icon('settings') + '</span><span class="settings-copy"><strong>' + title + '</strong><span>' + detail + '</span></span>' + icon('arrow') + '</button>';
  }
  function settingsLogoutRow() {
    return '<button class="settings-row settings-logout-row" type="button" onclick="mobileAdminLogout()"><span class="settings-icon">' + icon('logout') + '</span><span class="settings-copy"><strong>退出登录</strong><span>清除本机登录状态并返回登录页</span></span></button>';
  }
  function settingsNotice() {
    if (!state.settings.notice && !state.settings.error) return '';
    return '<div class="settings-notice ' + (state.settings.error ? 'is-error' : '') + '">' + esc(state.settings.error || state.settings.notice) + '</div>';
  }
  function settingsDetailHeader(title, detail) {
    return '<div class="settings-detail-header"><button type="button" class="settings-back" onclick="mobileAdminOpenSettings(\'home\')">‹</button><div><h3>' + esc(title) + '</h3><p>' + esc(detail) + '</p></div></div>';
  }
  function settingsDetailPanel() {
    var body = '';
    if (state.settingsView === 'core') body = settingsCorePanel();
    if (state.settingsView === 'units') body = settingsUnitsPanel();
    if (state.settingsView === 'bank') body = settingsBankPanel();
    if (state.settingsView === 'admins') body = settingsAdminsPanel();
    if (state.settingsView === 'password') body = settingsPasswordPanel();
    if (state.settingsView === 'test') body = settingsTestPanel();
    if (state.settingsView === 'blacklist') body = settingsBlacklistPanel();
    if (state.settingsView === 'cleanup') body = settingsCleanupPanel();
    return '<section class="tab-panel is-active settings-detail" data-panel="settings">' + body + settingsNotice() + '</section>';
  }
  function settingsCorePanel() {
    var config = state.settings.config;
    if (!config) return settingsDetailHeader('系统配置', '考试时间、区域和岗位') + '<div class="empty-state">正在读取系统配置…</div>';
    return settingsDetailHeader('系统配置', '考试时间、开放区域与岗位') + '<div class="sheet settings-form">' +
      '<div class="settings-field"><span>每日考试时间</span><div class="settings-time-row"><label class="settings-time-control"><span>开始</span><input id="mobile-config-start" type="time" value="' + esc(config.start_time) + '"></label><span class="settings-time-divider" aria-hidden="true">至</span><label class="settings-time-control"><span>截止</span><input id="mobile-config-end" type="time" value="' + esc(config.end_time) + '"></label></div></div>' +
      settingsTagEditor('开放区域', 'regions', config.regions, '如：尿素塔') + settingsTagEditor('岗位 / 工种', 'jobs', config.jobs, '如：电工') +
      '<button class="settings-primary" type="button" ' + (state.settings.busy ? 'disabled' : '') + ' onclick="mobileAdminSaveSettingsCore()">' + (state.settings.busy ? '保存中…' : '保存系统配置') + '</button></div>';
  }
  function settingsTestPanel() {
    var config = state.settings.config;
    if (!config) return settingsDetailHeader('测试功能', '功能开关') + '<div class="empty-state">正在读取测试功能配置…</div>';
    var checked = config.special_work_enabled ? ' checked' : '';
    var blacklistChecked = config.blacklist_enabled ? ' checked' : '';
    return settingsDetailHeader('测试功能', '只在启用后对客户端和下载入口生效') + '<div class="sheet settings-form">' +
      '<label class="settings-test-toggle"><span><strong>特殊工种</strong><small>客户端显示特殊工种证件拍摄框；下载菜单显示证件照压缩包。</small></span><input id="mobile-special-work-enabled" type="checkbox"' + checked + '></label>' +
      '<button class="settings-primary" type="button" ' + (state.settings.busy ? 'disabled' : '') + ' onclick="mobileAdminSaveSpecialWorkFeature()">' + (state.settings.busy ? '保存中…' : '保存特殊工种功能') + '</button>' +
      '<label class="settings-test-toggle" style="border-color:rgba(248,113,113,.32); background:rgba(127,29,29,.18);"><span><strong>黑名单</strong><small>人员详情底部显示加入黑名单按钮；设置中可查看并移除已拉黑人员。</small></span><input id="mobile-blacklist-enabled" type="checkbox"' + blacklistChecked + '></label>' +
      '<button class="settings-primary" type="button" style="background:#dc2626; border-color:#ef4444;" ' + (state.settings.busy ? 'disabled' : '') + ' onclick="mobileAdminSaveBlacklistFeature()">' + (state.settings.busy ? '保存中…' : '保存黑名单功能') + '</button></div>';
  }

  function settingsBlacklistPanel() {
    var entries = state.settings.blacklist;
    if (!entries) return settingsDetailHeader('黑名单', '已拉黑人员') + '<div class="empty-state">正在加载黑名单…</div>';
    var query = String(state.settings.blacklistQuery || '').trim().toLowerCase();
    var filtered = entries.filter(function (entry) {
      if (!query) return true;
      return [entry.name, entry.company, entry.phone, entry.id_card].some(function (value) { return String(value || '').toLowerCase().indexOf(query) !== -1; });
    });
    return settingsDetailHeader('黑名单', '名单按身份证号去重保存') + '<div class="settings-list">' +
      '<input class="form-control" type="search" value="' + esc(state.settings.blacklistQuery || '') + '" placeholder="搜索姓名、单位、电话或身份证号" oninput="mobileAdminFilterBlacklist(this.value)">' +
      (filtered.length ? filtered.map(function (entry) {
        return '<article class="settings-list-card"><div><strong>' + esc(entry.name || '--') + '</strong><small>' + esc(entry.company || '--') + ' · ' + esc(entry.phone || '--') + '</small><small>身份证：' + esc(entry.id_card || '--') + ' · 加入：' + esc(displayDateTime(entry.created_at)) + '</small></div><div class="settings-list-actions"><button class="small-action danger-action" type="button" onclick="mobileAdminRemoveBlacklistEntry(' + jsArg(entry.id_card) + ')">移除</button></div></article>';
      }).join('') : '<div class="empty-state">' + (query ? '未找到匹配的黑名单人员' : '暂无黑名单人员') + '</div>') + '</div>';
  }
  function settingsTagEditor(label, type, values, placeholder) {
    var tags = values.length ? values.map(function (value, index) { return '<span class="settings-tag">' + esc(value) + '<button type="button" aria-label="删除' + esc(value) + '" onclick="mobileAdminRemoveSettingsTag(\'' + type + '\',' + index + ')">×</button></span>'; }).join('') : '<span class="settings-empty">暂未添加</span>';
    return '<div class="settings-field"><span>' + label + '</span><div class="settings-tags">' + tags + '</div><div class="settings-inline-add"><input id="mobile-config-' + type + '" type="text" placeholder="' + esc(placeholder) + '"><button type="button" onclick="mobileAdminAddSettingsTag(\'' + type + '\')">添加</button></div></div>';
  }
  function settingsUnitsPanel() {
    var companies = [];
    try { companies = typeof recordsAllCompanies !== 'undefined' && Array.isArray(recordsAllCompanies) ? recordsAllCompanies : []; } catch (e) { /* ignore */ }
    return settingsDetailHeader('培训单位', '当前系统中已出现的工作单位') + '<div class="sheet"><p class="settings-hint">培训单位由注册账号的工作单位自动汇集。要调整归属，请编辑对应注册用户，不会影响已经录入的历史培训单位。</p>' +
      (companies.length ? companies.map(function (company) { return '<div class="list-line"><div>' + esc(company) + '<small>已在培训记录中使用</small></div><span class="value-tag">单位</span></div>'; }).join('') : '<div class="empty-state">暂未发现培训单位</div>') +
      '<button type="button" class="settings-primary" onclick="mobileAdminGo(\'pending\')">前往注册用户管理</button></div>';
  }
  function settingsBankPanel() {
    var subjects = state.settings.subjects;
    if (!subjects) return settingsDetailHeader('考试题库', '科目、题目与导入更新') + '<div class="empty-state">正在读取考试科目…</div>';
    return settingsDetailHeader('考试题库', '科目、题目与导入更新') + '<div class="sheet"><div class="settings-inline-add"><input id="mobile-bank-subject" type="text" placeholder="输入新科目名称"><button type="button" onclick="mobileAdminAddExamSubject()">新增科目</button></div><div class="settings-list">' +
      (subjects.length ? subjects.map(function (subject) { return '<div class="settings-list-card"><div><strong>' + esc(subject.name) + '</strong><small>Excel 题库可直接上传更新</small></div><div class="settings-list-actions"><label class="small-action">上传<input type="file" accept=".xlsx" onchange="mobileAdminUploadExamSubject(' + jsArg(subject.name) + ',this)"></label><button class="small-action danger-action" type="button" onclick="mobileAdminDeleteExamSubject(' + jsArg(subject.name) + ')">删除</button></div></div>'; }).join('') : '<div class="empty-state">暂未配置考试科目</div>') + '</div></div>';
  }
  function settingsAdminsPanel() {
    var admins = state.settings.admins;
    if (!admins) return settingsDetailHeader('二级管理员', '账号、权限与状态') + '<div class="empty-state">正在读取二级管理员…</div>';
    var editor = state.settings.adminEditor;
    var editorHtml = editor ? '<div class="sheet settings-form"><h4>' + (editor.id ? '编辑二级管理员' : '新增二级管理员') + '</h4><label>账号<input id="mobile-subadmin-username" value="' + esc(editor.username || '') + '" placeholder="手机号或用户名"></label><label>真实姓名<input id="mobile-subadmin-realname" value="' + esc(editor.real_name || '') + '" placeholder="真实姓名"></label><label>公司 / 部门<input id="mobile-subadmin-company" value="' + esc(editor.company || '') + '" placeholder="公司或部门"></label><label>' + (editor.id ? '新密码（留空不修改）' : '密码') + '<input id="mobile-subadmin-password" type="password" placeholder="至少 6 位"></label><div class="settings-form-actions"><button type="button" onclick="mobileAdminCancelSubAdminEdit()">取消</button><button class="settings-primary" type="button" onclick="mobileAdminSaveSubAdmin()">保存</button></div></div>' : '<button type="button" class="settings-primary" onclick="mobileAdminNewSubAdmin()">新增二级管理员</button>';
    return settingsDetailHeader('二级管理员', '账号、权限与状态') + editorHtml + '<div class="settings-list">' +
      (admins.length ? admins.map(function (admin) { return '<article class="settings-list-card"><div><strong>' + esc(admin.real_name || admin.username) + '</strong><small>' + esc(admin.username) + ' · ' + esc(admin.company || '--') + '</small></div><div class="settings-list-actions"><button class="small-action" type="button" onclick="mobileAdminEditSubAdmin(' + Number(admin.id) + ')">编辑</button><button class="small-action danger-action" type="button" onclick="mobileAdminDeleteSubAdmin(' + Number(admin.id) + ',' + jsArg(admin.username) + ')">删除</button></div></article>'; }).join('') : '<div class="empty-state">暂无二级管理员</div>') + '</div>';
  }
  function formatCleanupBytes(value) {
    var bytes = Number(value || 0);
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
  }
  function settingsCleanupPanel() {
    var preview = state.settings.cleanupPreview;
    var result = state.settings.cleanupResult;
    var feedback = '';
    if (preview) {
      feedback = '<div class="settings-notice"><strong>清理预览</strong><br>' + esc(preview.start_date) + ' 至 ' + esc(preview.end_date) + '：将删除 ' + Number(preview.record_count || 0) + ' 条录入档案、' + Number(preview.update_request_count || 0) + ' 条关联修改申请、' + Number(preview.file_count || 0) + ' 个文件，预计释放 ' + formatCleanupBytes(preview.estimated_bytes) + '。<br><small>考试记录、注册账号、系统配置和题库不会删除。</small></div>';
    }
    if (result) {
      feedback = '<div class="settings-notice"><strong>清理完成</strong><br>已删除 ' + Number(result.record_count || 0) + ' 条录入档案、' + Number(result.file_count || 0) + ' 个文件，实际释放 ' + formatCleanupBytes(result.bytes_reclaimed) + '。考试记录仍已保留。</div>';
    }
    return settingsDetailHeader('清理资料', '按录入日期清理服务器中的培训档案') + '<div class="sheet settings-form">' +
      '<p class="settings-hint">此操作永久删除人员档案、现场照片、身份证裁切图、登记卡及该档案关联的待审核修改申请。注册用户、题库和考试记录会保留。</p>' +
      '<label>开始日期<input type="date" value="' + esc(state.settings.cleanupStart) + '" onchange="mobileAdminSetCleanupDate(\'start\',this.value)"></label>' +
      '<label>结束日期<input type="date" value="' + esc(state.settings.cleanupEnd) + '" onchange="mobileAdminSetCleanupDate(\'end\',this.value)"></label>' +
      '<div class="settings-form-actions"><button type="button" onclick="mobileAdminPreviewCleanup()">预览范围</button><button class="settings-primary" type="button" style="background:#dc2626;border-color:#ef4444;" ' + (state.settings.busy ? 'disabled' : '') + ' onclick="mobileAdminRunCleanup()">永久清理</button></div>' + feedback + '</div>';
  }
  function settingsPasswordPanel() {
    return settingsDetailHeader('修改密码', '更新当前管理员密码') + '<div class="sheet settings-form"><label>当前密码<input id="mobile-password-old" type="password" autocomplete="current-password"></label><label>新密码<input id="mobile-password-new" type="password" autocomplete="new-password" placeholder="至少 6 位"></label><label>确认新密码<input id="mobile-password-confirm" type="password" autocomplete="new-password"></label><button class="settings-primary" type="button" onclick="mobileAdminChangePassword()">保存新密码</button></div>';
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
    if (!state.settings.config) loadSettingsCore();
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
    if (tab === 'settings') { if (!state.settings.config) loadSettingsCore(); render(); return; }
    if (typeof window.switchAdminTab === 'function') window.switchAdminTab(tab);
    else { render(); loadCurrentTab(); }
  };
  window.mobileAdminToggleRecordCompany = function (event) { if (event) event.stopPropagation(); state.recordCompanyOpen = !state.recordCompanyOpen; state.downloadOpen = false; render(); };
  window.mobileAdminSelectRecordCompany = function (company) {
    state.recordCompanyOpen = false;
    try { filterCompany = company; recordsPage = 1; document.getElementById('filter-company').value = company; } catch (e) { /* page loading */ }
    if (typeof window.loadRecords === 'function') window.loadRecords(); else render();
  };
  window.mobileAdminCompositionStart = function (field) {
    if (!state.composing.hasOwnProperty(field)) return;
    state.composing[field] = true;
    if (field === 'record') clearTimeout(searchTimer);
    if (field === 'exam') clearTimeout(examSearchTimer);
  };
  window.mobileAdminCompositionEnd = function (field, value) {
    if (!state.composing.hasOwnProperty(field)) return;
    state.composing[field] = false;
    if (field === 'record') window.mobileAdminRecordSearch(value);
    else if (field === 'exam') window.mobileAdminExamSearch(value);
    else if (field === 'pending') window.mobileAdminPendingSearch(value);
    else if (field === 'restore') window.mobileAdminRestoreSearch(value);
  };
  window.mobileAdminRecordSearch = function (value, event) {
    if (state.composing.record || (event && event.isComposing)) return;
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
  window.mobileAdminPendingSearch = function (value, event) { if (state.composing.pending || (event && event.isComposing)) return; state.pendingQuery = value; render(); };
  window.mobileAdminTogglePendingCompany = function (event) { if (event) event.stopPropagation(); state.pendingCompanyOpen = !state.pendingCompanyOpen; state.recordCompanyOpen = false; state.examCompanyOpen = false; render(); };
  window.mobileAdminSelectPendingCompany = function (company) { state.pendingCompany = company || ''; state.pendingCompanyOpen = false; render(); };
  window.mobileAdminRestoreSearch = function (value, event) { if (state.composing.restore || (event && event.isComposing)) return; state.restoreQuery = value; render(); };
  window.mobileAdminToggleRestore = function (id, checked) { if (typeof window.handleSingleRestoreCheckboxChange === 'function') window.handleSingleRestoreCheckboxChange({ checked: checked }, id); else render(); };
  window.mobileAdminToggleExamCompany = function (event) { if (event) event.stopPropagation(); state.examCompanyOpen = !state.examCompanyOpen; render(); };
  window.mobileAdminSelectExamCompany = function (company) {
    state.examCompanyOpen = false;
    var input = document.getElementById('exam-filter-company');
    if (input) input.value = company;
    try { examRecordsPage = 1; } catch (e) { /* ignore */ }
    if (typeof window.loadExamRecords === 'function') window.loadExamRecords(); else render();
  };
  window.mobileAdminExamSearch = function (value, event) {
    if (state.composing.exam || (event && event.isComposing)) return;
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
  function authHeaders() {
    try { return { 'Authorization': token }; } catch (e) { return {}; }
  }
  function setSettingsMessage(message, isError) {
    state.settings.notice = isError ? '' : message;
    state.settings.error = isError ? message : '';
  }
  async function requestSettings(url, options) {
    var response = await fetch(url, options || { headers: authHeaders() });
    var result = await response.json().catch(function () { return {}; });
    if (!response.ok || result.code !== 200) throw new Error(result.detail || result.message || '操作失败');
    return result;
  }
  async function loadSettingsCore() {
    try {
      state.settings.error = '';
      var result = await requestSettings('/api/admin/config', { headers: authHeaders() });
      var data = result.data || {};
      state.settings.config = {
        start_time: data.exam_start_time || '08:00',
        end_time: data.exam_end_time || '12:00',
        regions: String(data.regions || '').split(',').map(function (item) { return item.trim(); }).filter(Boolean),
        jobs: String(data.job_types || '').split(',').map(function (item) { return item.trim(); }).filter(Boolean),
        special_work_enabled: data.special_work_enabled === true || String(data.special_work_enabled).toLowerCase() === 'true',
        blacklist_enabled: data.blacklist_enabled === true || String(data.blacklist_enabled).toLowerCase() === 'true'
      };
      if (typeof window.loadSystemConfig === 'function') window.loadSystemConfig();
    } catch (error) { setSettingsMessage(error.message || '读取系统配置失败', true); }
    if (isMobile()) render();
  }
  async function loadSettingsSubjects() {
    try {
      state.settings.error = '';
      var result = await requestSettings('/api/exam_subjects', { headers: authHeaders() });
      state.settings.subjects = result.data || [];
    } catch (error) { setSettingsMessage(error.message || '读取考试科目失败', true); state.settings.subjects = []; }
    if (isMobile() && state.tab === 'settings') render();
  }
  async function loadSettingsAdmins() {
    try {
      state.settings.error = '';
      var result = await requestSettings('/api/admin/sub_admins', { headers: authHeaders() });
      state.settings.admins = result.data || [];
    } catch (error) { setSettingsMessage(error.message || '读取二级管理员失败', true); state.settings.admins = []; }
    if (isMobile() && state.tab === 'settings') render();
  }
  async function loadSettingsBlacklist() {
    try {
      state.settings.error = '';
      var result = await requestSettings('/api/admin/blacklist', { headers: authHeaders() });
      state.settings.blacklist = result.data || [];
    } catch (error) { setSettingsMessage(error.message || '加载黑名单失败', true); state.settings.blacklist = []; }
    if (isMobile() && state.tab === 'settings') render();
  }
  window.mobileAdminOpenSettings = function (view) {
    if (!isPrimaryAdmin()) view = 'home';
    state.settingsView = view;
    state.settings.notice = '';
    state.settings.error = '';
    if (view === 'home' && !state.settings.config) loadSettingsCore();
    if (view === 'core' || view === 'test') { state.settings.config = null; loadSettingsCore(); }
    if (view === 'units' && typeof window.loadCompanies === 'function') Promise.resolve(window.loadCompanies()).then(function () { if (isMobile() && state.tab === 'settings') render(); });
    if (view === 'bank') { state.settings.subjects = null; loadSettingsSubjects(); }
    if (view === 'admins') { state.settings.admins = null; state.settings.adminEditor = null; loadSettingsAdmins(); }
    if (view === 'blacklist') { state.settings.blacklist = null; state.settings.blacklistQuery = ''; loadSettingsBlacklist(); }
    if (view === 'cleanup') { state.settings.cleanupPreview = null; state.settings.cleanupResult = null; }
    render();
  };
  window.mobileAdminSetCleanupDate = function (kind, value) {
    if (kind === 'start') state.settings.cleanupStart = value || '';
    if (kind === 'end') state.settings.cleanupEnd = value || '';
    state.settings.cleanupPreview = null;
    state.settings.cleanupResult = null;
  };
  function getCleanupDates() {
    var start = state.settings.cleanupStart;
    var end = state.settings.cleanupEnd;
    if (!start || !end) throw new Error('请选择完整的清理日期范围');
    if (start > end) throw new Error('开始日期不能晚于结束日期');
    return { start: start, end: end };
  }
  window.mobileAdminPreviewCleanup = async function () {
    try {
      var dates = getCleanupDates();
      state.settings.busy = true;
      render();
      var result = await requestSettings('/api/admin/storage-cleanup/preview?start_date=' + encodeURIComponent(dates.start) + '&end_date=' + encodeURIComponent(dates.end), { headers: authHeaders() });
      state.settings.cleanupPreview = result.data || null;
      state.settings.cleanupResult = null;
      setSettingsMessage('', false);
    } catch (error) {
      setSettingsMessage(error.message || '无法预览清理范围', true);
    }
    state.settings.busy = false;
    render();
  };
  window.mobileAdminRunCleanup = async function () {
    try {
      var dates = getCleanupDates();
      var phrase = window.prompt('此操作不可恢复。请输入“清理资料”确认永久删除：');
      if (phrase === null) return;
      if (phrase !== '清理资料') throw new Error('确认文字不正确，未执行清理');
      state.settings.busy = true;
      render();
      var formData = new FormData();
      formData.append('start_date', dates.start);
      formData.append('end_date', dates.end);
      formData.append('confirm_phrase', phrase);
      var result = await requestSettings('/api/admin/storage-cleanup', { method: 'POST', headers: authHeaders(), body: formData });
      state.settings.cleanupResult = result.data || null;
      state.settings.cleanupPreview = null;
      setSettingsMessage(result.message || '资料清理完成', false);
      if (typeof window.loadRecords === 'function') window.loadRecords();
    } catch (error) {
      setSettingsMessage(error.message || '资料清理失败', true);
    }
    state.settings.busy = false;
    render();
  };
  window.mobileAdminLogout = function () {
    if (!confirm('确定退出当前管理员账号吗？')) return;
    if (typeof window.logout === 'function') {
      window.logout();
      return;
    }
    localStorage.clear();
    sessionStorage.clear();
    window.location.href = '/login';
  };
  window.addEventListener('adminidentityready', function () {
    if (isMobile() && state.tab === 'settings') render();
  });
  window.mobileAdminAddSettingsTag = function (type) {
    var config = state.settings.config;
    var input = document.getElementById('mobile-config-' + type);
    var value = input ? input.value.trim() : '';
    if (!config || !value) return;
    var target = type === 'regions' ? config.regions : config.jobs;
    if (target.indexOf(value) !== -1) { setSettingsMessage('该项已经存在', true); render(); return; }
    target.push(value);
    render();
  };
  window.mobileAdminRemoveSettingsTag = function (type, index) {
    var config = state.settings.config;
    if (!config) return;
    var target = type === 'regions' ? config.regions : config.jobs;
    target.splice(index, 1);
    render();
  };
  window.mobileAdminSaveSettingsCore = async function () {
    var config = state.settings.config;
    var start = document.getElementById('mobile-config-start');
    var end = document.getElementById('mobile-config-end');
    if (!config || !start || !end || !start.value || !end.value) { setSettingsMessage('请完整填写考试时间', true); render(); return; }
    config.start_time = start.value;
    config.end_time = end.value;
    state.settings.busy = true;
    render();
    try {
      var formData = new FormData();
      formData.append('start_time', config.start_time);
      formData.append('end_time', config.end_time);
      formData.append('regions', config.regions.join(','));
      formData.append('job_types', config.jobs.join(','));
      await requestSettings('/api/admin/config', { method: 'POST', headers: authHeaders(), body: formData });
      setSettingsMessage('系统配置已保存', false);
      if (typeof window.loadSystemConfig === 'function') window.loadSystemConfig();
    } catch (error) { setSettingsMessage(error.message || '保存系统配置失败', true); }
    state.settings.busy = false;
    render();
  };
  window.mobileAdminSaveSpecialWorkFeature = async function () {
    var config = state.settings.config;
    var input = document.getElementById('mobile-special-work-enabled');
    if (!config || !input) return;
    var enabled = Boolean(input.checked);
    state.settings.busy = true;
    render();
    try {
      var formData = new FormData();
      formData.append('enabled', enabled ? 'true' : 'false');
      var result = await requestSettings('/api/admin/features/special-work', { method: 'POST', headers: authHeaders(), body: formData });
      config.special_work_enabled = Boolean(result.data && result.data.special_work_enabled);
      setSettingsMessage(result.message || '测试功能已保存', false);
      if (typeof window.applySpecialWorkFeatureControls === 'function') window.applySpecialWorkFeatureControls(config.special_work_enabled);
    } catch (error) {
      setSettingsMessage(error.message || '保存测试功能失败', true);
    }
    state.settings.busy = false;
    render();
  };
  window.mobileAdminSaveBlacklistFeature = async function () {
    var config = state.settings.config;
    var input = document.getElementById('mobile-blacklist-enabled');
    if (!config || !input) return;
    var enabled = Boolean(input.checked);
    state.settings.busy = true;
    render();
    try {
      var formData = new FormData();
      formData.append('enabled', enabled ? 'true' : 'false');
      var result = await requestSettings('/api/admin/features/blacklist', { method: 'POST', headers: authHeaders(), body: formData });
      config.blacklist_enabled = Boolean(result.data && result.data.blacklist_enabled);
      if (!config.blacklist_enabled) state.settings.blacklist = null;
      setSettingsMessage(result.message || '黑名单功能已保存', false);
    } catch (error) {
      setSettingsMessage(error.message || '保存黑名单功能失败', true);
    }
    state.settings.busy = false;
    render();
  };
  window.mobileAdminRemoveBlacklistEntry = async function (idCard) {
    if (!confirm('确定将该人员移出黑名单吗？')) return;
    try {
      var formData = new FormData();
      formData.append('id_card', idCard);
      var result = await requestSettings('/api/admin/blacklist/remove', { method: 'POST', headers: authHeaders(), body: formData });
      setSettingsMessage(result.message || '已移出黑名单', false);
      await loadSettingsBlacklist();
      if (typeof window.loadRecords === 'function') window.loadRecords();
    } catch (error) {
      setSettingsMessage(error.message || '移除黑名单失败', true);
      render();
    }
  };
  window.mobileAdminFilterBlacklist = function (query) {
    state.settings.blacklistQuery = query || '';
    render();
  };
  window.mobileAdminAddExamSubject = async function () {
    var input = document.getElementById('mobile-bank-subject');
    var name = input ? input.value.trim() : '';
    if (!name) { setSettingsMessage('请输入科目名称', true); render(); return; }
    try {
      var formData = new FormData(); formData.append('name', name);
      await requestSettings('/api/admin/add_exam_subject', { method: 'POST', headers: authHeaders(), body: formData });
      setSettingsMessage('已新增科目：' + name, false);
      await loadSettingsSubjects();
    } catch (error) { setSettingsMessage(error.message || '新增科目失败', true); render(); }
  };
  window.mobileAdminDeleteExamSubject = async function (name) {
    if (!confirm('确定删除科目“' + name + '”吗？题库文件会保留，但该科目不能再用于考试。')) return;
    try {
      var formData = new FormData(); formData.append('name', name);
      await requestSettings('/api/admin/delete_exam_subject', { method: 'POST', headers: authHeaders(), body: formData });
      setSettingsMessage('已删除科目：' + name, false);
      await loadSettingsSubjects();
    } catch (error) { setSettingsMessage(error.message || '删除科目失败', true); render(); }
  };
  window.mobileAdminUploadExamSubject = async function (name, input) {
    var file = input && input.files ? input.files[0] : null;
    if (!file) return;
    try {
      var formData = new FormData(); formData.append('exam_type', name); formData.append('file', file);
      var result = await requestSettings('/api/admin/upload_exam_bank', { method: 'POST', headers: authHeaders(), body: formData });
      setSettingsMessage(name + '题库已更新，共 ' + (result.question_count || 0) + ' 道题', false);
    } catch (error) { setSettingsMessage(error.message || '上传题库失败', true); }
    if (input) input.value = '';
    render();
  };
  window.mobileAdminNewSubAdmin = function () { state.settings.adminEditor = {}; render(); };
  window.mobileAdminCancelSubAdminEdit = function () { state.settings.adminEditor = null; render(); };
  window.mobileAdminEditSubAdmin = function (id) {
    var source = (state.settings.admins || []).filter(function (item) { return Number(item.id) === Number(id); })[0];
    if (!source) return;
    state.settings.adminEditor = { id: source.id, username: source.username, real_name: source.real_name, company: source.company };
    render();
  };
  window.mobileAdminSaveSubAdmin = async function () {
    var editor = state.settings.adminEditor || {};
    var username = (document.getElementById('mobile-subadmin-username') || {}).value || '';
    var realName = (document.getElementById('mobile-subadmin-realname') || {}).value || '';
    var company = (document.getElementById('mobile-subadmin-company') || {}).value || '';
    var password = (document.getElementById('mobile-subadmin-password') || {}).value || '';
    username = username.trim(); realName = realName.trim(); company = company.trim(); password = password.trim();
    if (!username || !realName || !company || (!editor.id && !password)) { setSettingsMessage('请填写所有必填项；新增管理员必须设置密码', true); render(); return; }
    if (password && password.length < 6) { setSettingsMessage('密码长度不能少于 6 位', true); render(); return; }
    try {
      var formData = new FormData();
      formData.append('username', username); formData.append('real_name', realName); formData.append('company', company);
      var url = '/api/admin/add_sub_admin';
      if (editor.id) { url = '/api/admin/update_sub_admin'; formData.append('sub_admin_id', editor.id); formData.append('new_username', username); formData.append('new_password', password); }
      else formData.append('password', password);
      await requestSettings(url, { method: 'POST', headers: authHeaders(), body: formData });
      state.settings.adminEditor = null;
      setSettingsMessage(editor.id ? '二级管理员已更新' : '二级管理员已添加', false);
      await loadSettingsAdmins();
    } catch (error) { setSettingsMessage(error.message || '保存二级管理员失败', true); render(); }
  };
  window.mobileAdminDeleteSubAdmin = async function (id, name) {
    if (!confirm('确定删除二级管理员“' + name + '”吗？')) return;
    try {
      var formData = new FormData(); formData.append('sub_admin_id', id);
      await requestSettings('/api/admin/delete_sub_admin', { method: 'POST', headers: authHeaders(), body: formData });
      setSettingsMessage('二级管理员已删除', false);
      await loadSettingsAdmins();
    } catch (error) { setSettingsMessage(error.message || '删除二级管理员失败', true); render(); }
  };
  window.mobileAdminChangePassword = async function () {
    var oldPassword = (document.getElementById('mobile-password-old') || {}).value || '';
    var newPassword = (document.getElementById('mobile-password-new') || {}).value || '';
    var confirmPassword = (document.getElementById('mobile-password-confirm') || {}).value || '';
    if (!oldPassword || !newPassword || !confirmPassword) { setSettingsMessage('请完整填写密码', true); render(); return; }
    if (newPassword.length < 6) { setSettingsMessage('新密码长度不能少于 6 位', true); render(); return; }
    if (newPassword !== confirmPassword) { setSettingsMessage('两次输入的新密码不一致', true); render(); return; }
    if (!confirm('确定修改管理员密码吗？修改后需要重新登录。')) return;
    try {
      var formData = new FormData(); formData.append('old_password', oldPassword); formData.append('new_password', newPassword);
      await requestSettings('/api/admin/update_password', { method: 'POST', headers: authHeaders(), body: formData });
      setSettingsMessage('密码修改成功，即将重新登录', false);
      render();
      setTimeout(function () { if (typeof window.logout === 'function') window.logout(); }, 1200);
    } catch (error) { setSettingsMessage(error.message || '修改密码失败', true); render(); }
  };
  window.mobileAdminSetUserStatus = async function (id, status) {
    var action = status === 'disabled' ? '停用' : '启用';
    var hint = status === 'disabled' ? '停用后该账号不能登录，过去录入的人员和培训记录不会删除。' : '启用后该账号可以重新登录。';
    if (!confirm('确定' + action + '该注册账号吗？\n' + hint)) return;
    try {
      var formData = new FormData(); formData.append('user_id', id); formData.append('status', status);
      var result = await requestSettings('/api/admin/user/status', { method: 'POST', headers: authHeaders(), body: formData });
      if (typeof window.showAlert === 'function') window.showAlert('success', result.message || ('账号已' + action));
      if (typeof window.loadPendingUsers === 'function') window.loadPendingUsers();
    } catch (error) {
      if (typeof window.showAlert === 'function') window.showAlert('error', error.message || (action + '失败'));
    }
  };

  document.addEventListener('click', function (event) {
    if (!isMobile()) return;
    var changed = false;
    if (!event.target.closest('.company-combobox') && (state.recordCompanyOpen || state.pendingCompanyOpen || state.examCompanyOpen)) { state.recordCompanyOpen = false; state.pendingCompanyOpen = false; state.examCompanyOpen = false; changed = true; }
    if (!event.target.closest('.download-wrap') && state.downloadOpen) { state.downloadOpen = false; changed = true; }
    if (changed) render();
  });
  if (media.addEventListener) media.addEventListener('change', onBreakpointChange);
  else media.addListener(onBreakpointChange);
  onBreakpointChange();
}());
