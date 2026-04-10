/* Disney Piano Stream — Client-side JS */

(function() {
    'use strict';

    // ── SSE Connection ──────────────────────────────────────────────────────

    let evtSource = null;

    function connectSSE() {
        if (evtSource) evtSource.close();
        evtSource = new EventSource('/events');

        evtSource.onmessage = function(e) {
            try {
                const data = JSON.parse(e.data);
                handleEvent(data);
            } catch (err) {
                // ignore parse errors
            }
        };

        evtSource.onerror = function() {
            // Auto-reconnects after ~3s (browser default)
        };
    }

    function handleEvent(data) {
        // Update stream indicator in footer
        updateStreamIndicator(data);

        // Update progress on dashboard
        if (data.type === 'task_progress' || data.type === 'task_started') {
            updateProgress(data.task);
        }

        if (data.type === 'task_complete') {
            updateProgress(null);
            // Reload page after a short delay to show updated history/library
            setTimeout(() => {
                if (window.location.pathname === '/' || window.location.pathname === '/library') {
                    window.location.reload();
                }
            }, 1500);
        }

        if (data.type === 'heartbeat') {
            updateStreamStatus(data);
        }
    }

    function updateStreamIndicator(data) {
        const dot = document.getElementById('stream-dot');
        const label = document.getElementById('stream-label');
        if (!dot || !label) return;

        const status = data.status || (data.task ? 'unknown' : 'stopped');
        if (status === 'live') {
            dot.className = 'dot live';
            label.textContent = 'LIVE' + (data.uptime_str ? ' - ' + data.uptime_str : '');
        } else if (status === 'error') {
            dot.className = 'dot';
            dot.style.background = '#dc4040';
            label.textContent = 'Error';
        } else {
            dot.className = 'dot';
            dot.style.background = '';
            label.textContent = 'Offline';
        }
    }

    function updateStreamStatus(data) {
        updateStreamIndicator(data);
        if (data.current_task) {
            updateProgress(data.current_task);
        }
    }

    function updateProgress(task) {
        const bar = document.getElementById('progress-fill');
        const text = document.getElementById('progress-text');
        if (!bar || !text) return;

        if (!task) {
            bar.style.width = '0%';
            text.textContent = '';
            return;
        }

        const progress = task.progress || '';
        text.textContent = progress;

        // Try to extract percentage from progress text
        const pctMatch = progress.match(/(\d+)%/);
        if (pctMatch) {
            bar.style.width = pctMatch[1] + '%';
        } else {
            // Estimate based on step
            const stepMap = {
                'generating_notes': '15%',
                'creating_midi': '30%',
                'rendering_audio': '45%',
                'rendering_video': '60%',
                'generating': '40%',
                'loading_model': '10%',
                'merging': '80%',
                'converting': '90%',
                'requesting': '20%',
                'polling': '50%',
                'downloading': '80%',
                'done': '100%',
            };
            const step = progress.split(':')[0];
            bar.style.width = stepMap[step] || '5%';
        }
    }

    // ── Init ────────────────────────────────────────────────────────────────

    // Only connect SSE on pages that need it
    if (document.getElementById('stream-indicator')) {
        connectSSE();
    }

    // Poll stream status periodically for the footer
    setInterval(function() {
        fetch('/stream/status')
            .then(r => r.json())
            .then(data => updateStreamIndicator(data))
            .catch(() => {});
    }, 30000);

})();
