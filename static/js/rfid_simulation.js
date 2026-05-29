/**
 * Library RFID — Real hardware only (HID USB reader + Serial COM reader)
 */

const scannedFields = {};
let rfidConfig = { mode: 'hid', running: false };
let activeScanField = null;
let lastPollId = 0;
let pollTimer = null;
let hidTimer = null;

async function loadRfidConfig() {
    try {
        const res = await fetch('/rfid/api/config');
        rfidConfig = await res.json();
        if (rfidConfig.mode === 'simulation') {
            rfidConfig.mode = 'hid';
        }
    } catch {
        rfidConfig = { mode: 'hid', running: false };
    }
    return rfidConfig;
}

async function pollRfidConnection() {
    const badge = document.getElementById('rfidConnectionBadge');
    const dot = document.getElementById('rfidStatusDot');
    const label = document.getElementById('rfidStatusLabel');
    if (!badge || !dot || !label) return;

    try {
        const res = await fetch('/rfid/api/connection-status');
        const data = await res.json();
        const state = data.connected ? 'connected' : 'not-connected';

        badge.className = `rfid-connection-badge ${state}`;
        badge.title = data.message || data.label;
        dot.className = `rfid-status-dot ${state}`;
        label.textContent = data.label;
    } catch {
        badge.className = 'rfid-connection-badge not-connected';
        dot.className = 'rfid-status-dot not-connected';
        label.textContent = 'Not Connected';
        badge.title = 'Cannot check RFID status';
    }
}

function startConnectionPolling() {
    pollRfidConnection();
    setInterval(pollRfidConnection, 2500);
}

document.addEventListener('DOMContentLoaded', () => {
    loadRfidConfig();
    startConnectionPolling();
    initThemeToggle();
    initSidebarScroll();
});

document.getElementById('sidebarToggle')?.addEventListener('click', function () {
    document.getElementById('sidebar').classList.toggle('show');
    document.getElementById('sidebarOverlay').classList.toggle('show');
});

document.getElementById('sidebarOverlay')?.addEventListener('click', function () {
    document.getElementById('sidebar').classList.remove('show');
    this.classList.remove('show');
});

async function initRfidScan(config) {
    await loadRfidConfig();
    window._rfidScanConfig = config;
    initRealRfidMode(config);

    if (rfidConfig.mode === 'serial') {
        startSerialPolling(config);
    }
}

function initRealRfidMode(config) {
    config.scans.forEach((scan, idx) => {
        const input = document.getElementById(scan.targetId);
        if (!input) return;

        input.readOnly = false;
        input.placeholder = rfidConfig.mode === 'serial'
            ? 'Waiting for serial RFID scan...'
            : 'Focus here and scan RFID tag with reader...';
        input.dataset.scanType = scan.type;
        input.dataset.scanIdx = idx;
        input.classList.add('rfid-live');

        input.addEventListener('focus', () => {
            activeScanField = scan.targetId;
            highlightActiveField(config);
            input.select();
        });

        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                handleTagSubmit(input.value.trim(), scan, config);
            }
        });

        input.addEventListener('input', () => {
            if (rfidConfig.mode === 'hid') {
                handleHidInput(input, scan, config);
            }
        });
    });

    if (config.scans[0]) {
        const first = document.getElementById(config.scans[0].targetId);
        first?.focus();
    }

    showRfidHint(config);
}

function showRfidHint(config) {
    const panel = document.querySelector('.rfid-panel .card-body');
    if (!panel || panel.querySelector('.rfid-real-hint')) return;
    const hint = document.createElement('div');
    hint.className = 'alert alert-success rfid-real-hint py-2';
    hint.innerHTML = rfidConfig.mode === 'serial'
        ? '<i class="bi bi-usb-plug me-2"></i><strong>Real Serial RFID:</strong> USB reader plug pannitu tag scan pannunga — auto-fill aagum.'
        : '<i class="bi bi-usb-symbol me-2"></i><strong>Real HID RFID:</strong> USB reader plug pannitu field focus pannitu tag scan pannunga.';
    panel.insertBefore(hint, panel.firstChild.nextSibling);
}

function highlightActiveField(config) {
    config.scans.forEach((s) => {
        const el = document.getElementById(s.targetId);
        if (el) el.classList.toggle('rfid-field-active', s.targetId === activeScanField);
    });
}

function handleHidInput(input, scanConfig, config) {
    clearTimeout(hidTimer);
    hidTimer = setTimeout(() => {
        const val = input.value.trim();
        if (val.length >= 4) {
            handleTagSubmit(val, scanConfig, config);
        }
    }, 120);
}

function startSerialPolling(config) {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(async () => {
        try {
            const res = await fetch(`/rfid/api/last-scan?since=${lastPollId}`);
            const data = await res.json();
            if (data.success && data.id > lastPollId) {
                lastPollId = data.id;
                const fieldId = activeScanField || config.scans[0]?.targetId;
                const scanConfig = config.scans.find((s) => s.targetId === fieldId) || config.scans[0];
                if (scanConfig) {
                    const input = document.getElementById(scanConfig.targetId);
                    if (input) input.value = data.tag;
                    await handleTagSubmit(data.tag, scanConfig, config);
                }
            }
        } catch { /* ignore */ }
    }, 300);
}

async function handleTagSubmit(tag, scanConfig, config) {
    if (!tag) return;
    const input = document.getElementById(scanConfig.targetId);
    const feedback = document.getElementById(scanConfig.feedbackId);
    input.value = tag;
    input.classList.remove('scan-success', 'scan-error');
    input.classList.add('scanning');
    feedback.innerHTML = '<span class="text-muted"><i class="bi bi-broadcast"></i> Validating tag...</span>';

    try {
        const validateRes = await fetch('/transactions/api/rfid/validate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ type: scanConfig.type, tag }),
        });
        const data = await validateRes.json();

        if (data.valid) {
            showScanSuccess(input, feedback, scanConfig.type, data, scanConfig);
            scannedFields[scanConfig.targetId] = true;
            if (rfidConfig.mode === 'hid') {
                fetch('/rfid/api/push-scan', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ tag }),
                });
            }
            focusNextField(scanConfig, config);
        } else {
            showScanError(input, feedback, data.message || 'Invalid tag');
            scannedFields[scanConfig.targetId] = false;
            input.select();
        }
    } catch {
        showScanError(input, feedback, 'Validation error');
        scannedFields[scanConfig.targetId] = false;
    }

    input.classList.remove('scanning');
    updateSubmitButton(config);
}

function focusNextField(currentScan, config) {
    const idx = config.scans.findIndex((s) => s.targetId === currentScan.targetId);
    if (idx >= 0 && idx < config.scans.length - 1) {
        const next = document.getElementById(config.scans[idx + 1].targetId);
        activeScanField = config.scans[idx + 1].targetId;
        next?.focus();
        highlightActiveField(config);
    }
}

function showScanSuccess(input, feedback, scanType, data, scanConfig) {
    input.classList.remove('scanning');
    input.classList.add('scan-success');
    let message = '<span class="valid"><i class="bi bi-check-circle-fill"></i> Scan OK!</span>';
    if (scanType === 'member') message += ` — ${data.name}`;
    else if (scanType === 'book') message += ` — ${data.title} (${data.available} available)`;
    else if (scanType === 'book-return') {
        message += ` — ${data.title} (Member: ${data.member})`;
        if (scanConfig.memberInfoId) {
            document.getElementById(scanConfig.memberInfoId).textContent = data.member;
            document.getElementById(scanConfig.memberPanelId)?.classList.remove('d-none');
        }
    }
    feedback.innerHTML = message;
}

function showScanError(input, feedback, message) {
    input.classList.remove('scanning');
    input.classList.add('scan-error');
    feedback.innerHTML = `<span class="invalid"><i class="bi bi-x-circle-fill"></i> ${message}</span>`;
}

function updateSubmitButton(config) {
    const submitBtn = document.getElementById(config.submitBtnId);
    if (!submitBtn) return;
    submitBtn.disabled = !config.scans.every((s) => scannedFields[s.targetId] === true);
}

const THEME_KEY = 'library-theme';

function getCurrentTheme() {
    return document.documentElement.getAttribute('data-theme') || localStorage.getItem(THEME_KEY) || 'light';
}

function updateThemeToggleButton(theme) {
    const btn = document.getElementById('themeToggle');
    if (!btn) return;
    const isDark = theme === 'dark';
    btn.innerHTML = isDark ? '<i class="bi bi-sun"></i>' : '<i class="bi bi-moon"></i>';
    btn.title = isDark ? 'Switch to light mode' : 'Switch to dark mode';
}

function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(THEME_KEY, theme);
    updateThemeToggleButton(theme);
    window.dispatchEvent(new CustomEvent('library-theme-change', { detail: { theme } }));
}

function initThemeToggle() {
    updateThemeToggleButton(getCurrentTheme());
    document.getElementById('themeToggle')?.addEventListener('click', function () {
        applyTheme(getCurrentTheme() === 'dark' ? 'light' : 'dark');
    });
}

const SIDEBAR_SCROLL_KEY = 'library-sidebar-scroll';

function isVisibleInContainer(element, container) {
    if (!element || !container) return true;
    const elRect = element.getBoundingClientRect();
    const boxRect = container.getBoundingClientRect();
    return elRect.top >= boxRect.top && elRect.bottom <= boxRect.bottom;
}

function initSidebarScroll() {
    const container = document.getElementById('sidebarScroll');
    if (!container) return;

    if ('scrollRestoration' in history) {
        history.scrollRestoration = 'manual';
    }
    window.scrollTo(0, 0);

    const saved = sessionStorage.getItem(SIDEBAR_SCROLL_KEY);
    if (saved !== null) {
        container.scrollTop = parseInt(saved, 10) || 0;
    }

    const activeInScroll = container.querySelector('.sidebar-link.active');
    if (activeInScroll && !isVisibleInContainer(activeInScroll, container)) {
        activeInScroll.scrollIntoView({ block: 'nearest', inline: 'nearest' });
        sessionStorage.setItem(SIDEBAR_SCROLL_KEY, String(container.scrollTop));
    }

    let scrollTimer;
    container.addEventListener('scroll', () => {
        clearTimeout(scrollTimer);
        scrollTimer = setTimeout(() => {
            sessionStorage.setItem(SIDEBAR_SCROLL_KEY, String(container.scrollTop));
        }, 100);
    }, { passive: true });

    document.querySelectorAll('#sidebar .sidebar-link').forEach((link) => {
        link.addEventListener('click', () => {
            sessionStorage.setItem(SIDEBAR_SCROLL_KEY, String(container.scrollTop));
            if (window.innerWidth < 992) {
                document.getElementById('sidebar')?.classList.remove('show');
                document.getElementById('sidebarOverlay')?.classList.remove('show');
            }
        });
    });
}
