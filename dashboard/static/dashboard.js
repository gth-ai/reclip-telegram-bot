/* =========================================================
   reclip admin — dashboard.js
   Chart.js polling + admin actions
   ========================================================= */

'use strict';

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function fmt(n) {
  if (n == null) return '--';
  return Number(n).toLocaleString();
}

function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <span>${message}</span>
    <button class="toast-close" aria-label="Dismiss">&times;</button>
  `;

  const closeBtn = toast.querySelector('.toast-close');
  closeBtn.addEventListener('click', () => removeToast(toast));

  container.appendChild(toast);

  // Auto-remove after 5 seconds
  setTimeout(() => removeToast(toast), 5000);
}

function removeToast(toast) {
  if (!toast.parentElement) return;
  toast.style.opacity = '0';
  toast.style.transform = 'translateX(20px)';
  toast.style.transition = 'opacity 0.2s ease-in, transform 0.2s ease-in';
  setTimeout(() => toast.remove(), 200);
}

// ---------------------------------------------------------------------------
// Chart configuration helpers
// ---------------------------------------------------------------------------

const CHART_DEFAULTS = {
  color: '#ff6b35',
  gridColor: '#2a2a40',
  tickColor: '#8888a0',
  fontFamily: 'Inter, system-ui, -apple-system, sans-serif',
};

function commonScaleOptions() {
  return {
    grid: { color: CHART_DEFAULTS.gridColor },
    ticks: {
      color: CHART_DEFAULTS.tickColor,
      font: { family: CHART_DEFAULTS.fontFamily, size: 11 },
    },
    border: { color: CHART_DEFAULTS.gridColor },
  };
}

// ---------------------------------------------------------------------------
// Chart instances (module-level so we can update them)
// ---------------------------------------------------------------------------

let downloadsChart = null;
let platformChart = null;

function initCharts() {
  const dlCtx = document.getElementById('downloads-chart');
  const plCtx = document.getElementById('platform-chart');

  if (dlCtx) {
    downloadsChart = new Chart(dlCtx, {
      type: 'line',
      data: {
        labels: [],
        datasets: [{
          label: 'Downloads',
          data: [],
          borderColor: CHART_DEFAULTS.color,
          backgroundColor: 'rgba(255, 107, 53, 0.08)',
          borderWidth: 2,
          pointRadius: 3,
          pointHoverRadius: 5,
          tension: 0.3,
          fill: true,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 400, easing: 'easeOut' },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: '#1a1a2e',
            borderColor: '#2a2a40',
            borderWidth: 1,
            titleColor: '#e0e0e0',
            bodyColor: '#8888a0',
            titleFont: { family: CHART_DEFAULTS.fontFamily, size: 12 },
            bodyFont: { family: CHART_DEFAULTS.fontFamily, size: 12 },
          },
        },
        scales: {
          x: commonScaleOptions(),
          y: {
            ...commonScaleOptions(),
            beginAtZero: true,
            ticks: {
              ...commonScaleOptions().ticks,
              precision: 0,
            },
          },
        },
      },
    });
  }

  if (plCtx) {
    platformChart = new Chart(plCtx, {
      type: 'bar',
      data: {
        labels: [],
        datasets: [{
          label: 'Downloads',
          data: [],
          backgroundColor: 'rgba(255, 107, 53, 0.7)',
          borderColor: CHART_DEFAULTS.color,
          borderWidth: 1,
          borderRadius: 3,
        }],
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 400, easing: 'easeOut' },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: '#1a1a2e',
            borderColor: '#2a2a40',
            borderWidth: 1,
            titleColor: '#e0e0e0',
            bodyColor: '#8888a0',
            titleFont: { family: CHART_DEFAULTS.fontFamily, size: 12 },
            bodyFont: { family: CHART_DEFAULTS.fontFamily, size: 12 },
          },
        },
        scales: {
          x: {
            ...commonScaleOptions(),
            beginAtZero: true,
            ticks: { ...commonScaleOptions().ticks, precision: 0 },
          },
          y: commonScaleOptions(),
        },
      },
    });
  }
}

// ---------------------------------------------------------------------------
// API fetchers
// ---------------------------------------------------------------------------

async function fetchStats() {
  try {
    const res = await fetch('/api/dashboard-stats', { credentials: 'same-origin' });
    if (!res.ok) return;
    const json = await res.json();
    const stats = json.stats || {};
    const disk = json.disk || null;

    // Downloads today
    const dlEl = document.getElementById('kpi-downloads');
    if (dlEl) dlEl.textContent = fmt(stats.downloads_today);

    const dlTrend = document.getElementById('kpi-downloads-trend');
    if (dlTrend) {
      const today = stats.downloads_today ?? 0;
      const yesterday = stats.downloads_yesterday ?? 0;
      if (yesterday === 0 && today === 0) {
        dlTrend.textContent = '';
        dlTrend.className = 'kpi-trend';
      } else if (today >= yesterday) {
        dlTrend.textContent = `↑ vs ${fmt(yesterday)} yesterday`;
        dlTrend.className = 'kpi-trend up';
      } else {
        dlTrend.textContent = `↓ vs ${fmt(yesterday)} yesterday`;
        dlTrend.className = 'kpi-trend down';
      }
    }

    // Active users
    const usersEl = document.getElementById('kpi-users');
    if (usersEl) usersEl.textContent = fmt(stats.active_users_24h);

    // Error rate
    const errEl = document.getElementById('kpi-errors');
    if (errEl) {
      const rate = stats.error_rate != null ? stats.error_rate.toFixed(1) : '--';
      errEl.textContent = rate !== '--' ? rate + '%' : '--';
    }

    const errTrend = document.getElementById('kpi-errors-trend');
    if (errTrend) {
      const today = stats.error_rate ?? 0;
      const yesterday = stats.error_rate_yesterday ?? 0;
      if (yesterday === 0 && today === 0) {
        errTrend.textContent = '';
        errTrend.className = 'kpi-trend';
      } else if (today <= yesterday) {
        // lower error rate is better
        errTrend.textContent = `↓ vs ${yesterday.toFixed(1)}% yesterday`;
        errTrend.className = 'kpi-trend up';
      } else {
        errTrend.textContent = `↑ vs ${yesterday.toFixed(1)}% yesterday`;
        errTrend.className = 'kpi-trend down';
      }
    }

    // Disk
    const diskEl = document.getElementById('kpi-disk');
    const diskBar = document.getElementById('disk-bar');
    if (disk && diskEl) {
      const totalBytes = disk.total_bytes || 0;
      // Use a configured max of 100GB, or actual disk_total from system info
      // The disk snapshot records downloads folder size; compare against a 100GB ceiling
      const MAX_BYTES = 100 * 1073741824; // 100 GB ceiling
      const pct = totalBytes > 0 ? Math.min((totalBytes / MAX_BYTES) * 100, 100) : 0;
      diskEl.textContent = pct.toFixed(1) + '%';

      if (diskBar) {
        diskBar.style.width = pct + '%';
        diskBar.className = 'disk-bar';
        if (pct >= 85) diskBar.classList.add('red');
        else if (pct >= 60) diskBar.classList.add('amber');
      }
    }

  } catch (e) {
    console.warn('fetchStats error', e);
  }
}

async function fetchChartData(range = '1D') {
  try {
    const res = await fetch(`/api/chart-data?range=${range}`, { credentials: 'same-origin' });
    if (!res.ok) return;
    const data = await res.json();

    // Downloads over time chart
    if (downloadsChart && data.labels && data.values) {
      downloadsChart.data.labels = data.labels;
      downloadsChart.data.datasets[0].data = data.values;
      downloadsChart.update();
    }

    // Platform chart
    if (platformChart && data.platforms) {
      platformChart.data.labels = data.platforms.map(p => p.platform);
      platformChart.data.datasets[0].data = data.platforms.map(p => p.count);
      platformChart.update();
    }

    // Top users table
    const tbody = document.getElementById('top-users');
    if (tbody && data.top_users) {
      if (data.top_users.length === 0) {
        tbody.innerHTML = '<tr><td colspan="2" class="empty-state">No data yet.</td></tr>';
      } else {
        tbody.innerHTML = data.top_users.map(u => `
          <tr>
            <td>${escapeHtml(u.username || 'unknown')}</td>
            <td class="mono">${fmt(u.count)}</td>
          </tr>
        `).join('');
      }
    }

  } catch (e) {
    console.warn('fetchChartData error', e);
  }
}

async function fetchActiveDownloads() {
  try {
    const res = await fetch('/api/active-downloads', { credentials: 'same-origin' });
    if (!res.ok) return;
    const active = await res.json();

    const section = document.getElementById('active-downloads');
    if (!section) return;

    if (!active || active.length === 0) {
      section.style.display = 'none';
      return;
    }

    section.style.display = '';

    const countBadge = document.getElementById('active-downloads-count');
    if (countBadge) countBadge.textContent = active.length;

    const tbody = document.getElementById('active-downloads-body');
    if (tbody) {
      tbody.innerHTML = active.map(dl => `
        <tr>
          <td>${escapeHtml(dl.username || dl.user_id || '—')}</td>
          <td class="url-cell">${escapeHtml((dl.url || '').slice(0, 50))}${(dl.url || '').length > 50 ? '…' : ''}</td>
          <td>${dl.platform ? `<span class="badge badge-platform">${escapeHtml(dl.platform)}</span>` : '—'}</td>
          <td class="mono">${dl.progress != null ? dl.progress.toFixed(0) + '%' : '—'}</td>
        </tr>
      `).join('');
    }
  } catch (e) {
    console.warn('fetchActiveDownloads error', e);
  }
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ---------------------------------------------------------------------------
// Range button handlers
// ---------------------------------------------------------------------------

function initRangeButtons() {
  const buttons = document.querySelectorAll('.range-btn');
  buttons.forEach(btn => {
    btn.addEventListener('click', () => {
      buttons.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      fetchChartData(btn.dataset.range);
    });
  });
}

// ---------------------------------------------------------------------------
// Admin actions
// ---------------------------------------------------------------------------

function deleteSelected() {
  const checked = Array.from(document.querySelectorAll('.file-check:checked'));
  if (checked.length === 0) {
    showToast('No files selected.', 'warning');
    return;
  }

  const paths = checked.map(el => el.value);

  fetch('/api/files', {
    method: 'DELETE',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ paths }),
  })
    .then(res => res.json())
    .then(data => {
      const deleted = data.deleted || [];
      const errors = data.errors || [];

      if (deleted.length > 0) {
        showToast(`Deleted ${deleted.length} file${deleted.length > 1 ? 's' : ''}.`, 'success');
        // Remove rows from DOM
        deleted.forEach(name => {
          const checkbox = document.querySelector(`.file-check[value="${CSS.escape(name)}"]`);
          if (checkbox) {
            const row = checkbox.closest('tr');
            if (row) row.remove();
          }
        });
      }

      if (errors.length > 0) {
        showToast(`${errors.length} file${errors.length > 1 ? 's' : ''} could not be deleted.`, 'danger');
      }
    })
    .catch(err => {
      console.error('deleteSelected error', err);
      showToast('Delete failed. See console.', 'danger');
    });
}

function showPurgeModal() {
  const modal = document.getElementById('purge-modal');
  if (modal) {
    modal.style.display = 'flex';
    const input = document.getElementById('purge-confirm');
    if (input) {
      input.value = '';
      input.focus();
    }
  }
}

function closePurgeModal() {
  const modal = document.getElementById('purge-modal');
  if (modal) modal.style.display = 'none';
}

function executePurge() {
  const input = document.getElementById('purge-confirm');
  if (!input || input.value !== 'PURGE') {
    showToast('Type PURGE to confirm.', 'warning');
    return;
  }

  fetch('/api/files/all', {
    method: 'DELETE',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ confirm: 'PURGE' }),
  })
    .then(res => {
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res.json();
    })
    .then(() => {
      showToast('All files purged.', 'success');
      closePurgeModal();
      setTimeout(() => location.reload(), 1200);
    })
    .catch(err => {
      console.error('executePurge error', err);
      showToast('Purge failed. See console.', 'danger');
    });
}

// ---------------------------------------------------------------------------
// Select-all checkbox
// ---------------------------------------------------------------------------

function initSelectAll() {
  const selectAll = document.getElementById('select-all');
  if (!selectAll) return;

  selectAll.addEventListener('change', () => {
    const checkboxes = document.querySelectorAll('.file-check');
    checkboxes.forEach(cb => { cb.checked = selectAll.checked; });
  });

  // Update select-all state when individual checkboxes change
  document.addEventListener('change', (e) => {
    if (e.target.classList.contains('file-check')) {
      const all = document.querySelectorAll('.file-check');
      const checked = document.querySelectorAll('.file-check:checked');
      selectAll.indeterminate = checked.length > 0 && checked.length < all.length;
      selectAll.checked = checked.length === all.length && all.length > 0;
    }
  });
}

// ---------------------------------------------------------------------------
// Polling loop
// ---------------------------------------------------------------------------

let _pollInterval = null;

function startPolling() {
  // Run immediately
  fetchStats();
  fetchChartData('1D');
  fetchActiveDownloads();

  // Then every 30 seconds
  _pollInterval = setInterval(() => {
    fetchStats();
    fetchActiveDownloads();
    // Chart data only re-fetched on range button click (not auto-polled)
  }, 30000);
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
  const isDashboard = document.getElementById('downloads-chart');
  const isAdmin = document.getElementById('file-table');

  if (isDashboard) {
    initCharts();
    initRangeButtons();
    startPolling();
  }

  if (isAdmin) {
    initSelectAll();
  }
});

// Expose admin functions to inline onclick handlers in templates
window.deleteSelected = deleteSelected;
window.showPurgeModal = showPurgeModal;
window.closePurgeModal = closePurgeModal;
window.executePurge = executePurge;
