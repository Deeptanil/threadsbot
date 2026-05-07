let currentEditAccount = null;
let currentEditType = null; // 'role' or 'posts'

async function fetchStatus(isManualRefresh = false) {
    if (isManualRefresh) {
        const refreshIcon = document.getElementById('refresh-icon');
        if (refreshIcon) refreshIcon.classList.add('spinning');
    }
    
    try {
        const response = await fetch('/api/status');
        const data = await response.json();
        renderDashboard(data);
        renderChart(data);
    } catch (error) {
        console.error("Failed to fetch status:", error);
    } finally {
        if (isManualRefresh) {
            const refreshIcon = document.getElementById('refresh-icon');
            if (refreshIcon) setTimeout(() => refreshIcon.classList.remove('spinning'), 500); // Give it a sec so the spin is visible
        }
    }
}


function timeSince(timestamp) {
    if (!timestamp) return "Never";
    const seconds = Math.floor((new Date().getTime() / 1000) - timestamp);
    let interval = seconds / 3600;
    if (interval > 1) return Math.floor(interval) + " hours ago";
    interval = seconds / 60;
    if (interval > 1) return Math.floor(interval) + " mins ago";
    return Math.floor(seconds) + " seconds ago";
}

function timeUntil(timestamp) {
    if (!timestamp) return "Not Scheduled";
    const seconds = Math.floor(timestamp - (new Date().getTime() / 1000));
    if (seconds < 0) return "Due Now";
    let interval = seconds / 3600;
    if (interval > 1) return Math.floor(interval) + "h " + Math.floor((seconds % 3600)/60) + "m";
    interval = seconds / 60;
    return Math.floor(interval) + " mins";
}

// Account names are now sent from the backend dynamically


function renderDashboard(data) {
    const grid = document.getElementById('dashboard-grid');
    grid.innerHTML = '';

    for (const [acc, info] of Object.entries(data)) {
        const card = document.createElement('div');
        card.className = 'card';
        
        if (!info.has_role_file) {
            card.innerHTML = `
                <div class="card-header">
                    <h2>
                        <div class="status-indicator"></div>
                        ${info.name || acc}
                    </h2>
                    <span class="badge-warning">Not Configured</span>
                </div>
                <div style="color: var(--text-muted); margin-top: 10px;">
                    This account has not been set up yet. Missing role configuration file.
                </div>
            `;
            grid.appendChild(card);
            continue;
        }

        const isWarning = info.upcoming_posts && info.upcoming_posts.length === 0;
        const statusClass = info.is_active ? 'active' : (isWarning ? 'warning' : '');
        
        let pendingHTML = '';
        if (info.pending_approvals && info.pending_approvals.length > 0) {
            pendingHTML = `
                <div class="pending-banner">
                    <div style="font-weight: bold; color: var(--accent-yellow); margin-bottom: 8px;">
                        <i class="ph ph-warning-circle"></i> ${info.pending_approvals.length} Post(s) Pending Approval
                    </div>
            `;
            info.pending_approvals.forEach((text, i) => {
                pendingHTML += `
                    <div class="pending-item">
                        <div class="pending-text">${text}</div>
                        <div style="display: flex; gap: 8px;">
                            <button class="btn-primary" onclick="approvePost('${acc}', ${i}, 'approve')"><i class="ph ph-check"></i></button>
                            <button class="btn-secondary" onclick="approvePost('${acc}', ${i}, 'reject')"><i class="ph ph-x"></i></button>
                        </div>
                    </div>
                `;
            });
            pendingHTML += `</div>`;
        }
        
        let reviewHTML = '';
        if (info.review_requests && info.review_requests.length > 0) {
            reviewHTML = `
                <div class="pending-banner" style="background-color: rgba(231, 76, 60, 0.1); border-color: #e74c3c;">
                    <div style="font-weight: bold; color: #e74c3c; margin-bottom: 8px;">
                        <i class="ph ph-hand-waving"></i> ${info.review_requests.length} Comment(s) Need Your Reply
                    </div>
            `;
            info.review_requests.forEach((req, i) => {
                reviewHTML += `
                    <div class="pending-item" style="flex-direction: column; gap: 8px;">
                        <div style="font-size: 12px; color: var(--text-muted);"><i class="ph ph-user"></i> @${req.username} commented:</div>
                        <div class="pending-text" style="font-style: italic;">"${req.text}"</div>
                        <textarea id="review-reply-${acc}-${i}" style="width: 100%; height: 60px; background: var(--bg-card); color: white; border: 1px solid var(--border-color); border-radius: 4px; padding: 8px; font-family: inherit; margin-top: 4px;" placeholder="Type your reply here...">${req.suggested_reply || ''}</textarea>
                        <div style="display: flex; gap: 8px; justify-content: flex-end; width: 100%;">
                            <button class="btn-primary" onclick="submitReviewReply('${acc}', ${i})"><i class="ph ph-paper-plane-tilt"></i> Send Reply</button>
                            <button class="btn-secondary" onclick="dismissReview('${acc}', ${i})">Dismiss</button>
                        </div>
                    </div>
                `;
            });
            reviewHTML += `</div>`;
        }
        
        card.innerHTML = `
            <div class="card-header">
                <h2 style="display: flex; align-items: center; gap: 10px;">
                    <div class="status-indicator ${statusClass}"></div>
                    ${info.name || acc}
                    <div style="display: flex; gap: 8px; margin-left: 8px;">
                        ${info.threads_url ? `<a href="${info.threads_url}" target="_blank" class="social-link" title="Open Threads Profile"><i class="ph ph-threads-logo"></i></a>` : ''}
                        ${info.twitter_url ? `<a href="${info.twitter_url}" target="_blank" class="social-link" title="Open X (Twitter) Profile"><i class="ph ph-x-logo"></i></a>` : ''}
                    </div>
                </h2>
                <span style="font-size: 12px; color: var(--text-muted);">
                    <i class="ph ph-clock"></i> Checked ${timeSince(info.last_reply_check)}
                </span>
            </div>
            
            ${reviewHTML}
            ${pendingHTML}
            
            <div class="metrics">
                <div class="metric">
                    <span>Total Posts</span>
                    <strong>${info.post_count}</strong>
                </div>
                <div class="metric">
                    <span>Replies Made</span>
                    <strong>${info.replied_count}</strong>
                </div>
                <div class="metric">
                    <span>Next Post In</span>
                    <strong style="color: ${info.next_post_time < new Date().getTime()/1000 ? 'var(--accent-yellow)' : 'var(--text-main)'}">
                        ${timeUntil(info.next_post_time)}
                    </strong>
                </div>
            </div>

            <div class="card-actions">
                <button class="btn-primary" onclick="triggerRun('${acc}')" id="btn-run-${acc}">
                    <i class="ph ph-play" id="icon-run-${acc}"></i> Force Run
                </button>
                <button class="btn-secondary" onclick="editRole('${acc}')">
                    <i class="ph ph-user"></i> Edit Persona
                </button>
                <button class="btn-secondary" onclick="editPosts('${acc}')">
                    <i class="ph ph-list-dashes"></i> Edit Queue
                </button>
            </div>
        `;
        grid.appendChild(card);
    }
}

async function triggerRun(account) {
    const btnIcon = document.getElementById(`icon-run-${account}`);
    if (btnIcon) {
        btnIcon.className = "ph ph-spinner spinning"; // Set to spinner
    }

    try {
        await fetch(`/api/trigger/${account}`, { method: 'POST' });
        
        // Show success briefly
        if (btnIcon) btnIcon.className = "ph ph-check";
        
        setTimeout(() => {
            if (btnIcon) btnIcon.className = "ph ph-play";
            fetchStatus(); // Refresh data
        }, 1500);

    } catch (e) {
        alert('Failed to trigger run.');
        if (btnIcon) btnIcon.className = "ph ph-play";
    }
}

async function editRole(account) {
    currentEditAccount = account;
    currentEditType = 'role';
    document.getElementById('modal-title').innerText = `Edit Persona: ${account}`;
    
    try {
        const res = await fetch('/api/roles');
        const roles = await res.json();
        document.getElementById('modal-editor').value = roles[account] || '';
        document.getElementById('edit-modal').classList.add('active');
    } catch(e) {
        alert('Failed to load role.');
    }
}

async function editPosts(account) {
    currentEditAccount = account;
    currentEditType = 'posts';
    document.getElementById('modal-title').innerText = `Edit Queue: ${account}`;
    
    try {
        const res = await fetch('/api/status');
        const status = await res.json();
        const posts = status[account].upcoming_posts || [];
        document.getElementById('modal-editor').value = JSON.stringify(posts, null, 4);
        document.getElementById('edit-modal').classList.add('active');
    } catch(e) {
        alert('Failed to load posts queue.');
    }
}

function closeModal(modalId) {
    document.getElementById(modalId || 'edit-modal').classList.remove('active');
    if(modalId === 'edit-modal' || !modalId) {
        currentEditAccount = null;
        currentEditType = null;
    }
}

async function saveModalData() {
    const editorValue = document.getElementById('modal-editor').value;
    
    try {
        if (currentEditType === 'role') {
            await fetch(`/api/roles/${currentEditAccount}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ role_text: editorValue })
            });
        } else if (currentEditType === 'posts') {
            let parsedPosts;
            try {
                parsedPosts = JSON.parse(editorValue);
            } catch(e) {
                alert('Invalid JSON! Please check your formatting before saving.');
                return;
            }
            await fetch(`/api/posts/${currentEditAccount}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ posts: parsedPosts })
            });
        }
        closeModal('edit-modal');
        fetchStatus();
    } catch(e) {
        alert('Failed to save data.');
    }
}

let chartInstance = null;
function renderChart(data) {
    const ctx = document.getElementById('performanceChart').getContext('2d');
    const labels = [];
    const posts = [];
    const replies = [];
    
    for (const [acc, info] of Object.entries(data)) {
        if (!info.has_role_file) continue;
        labels.push(info.name || acc);
        posts.push(info.post_count);
        replies.push(info.replied_count);
    }
    
    if (chartInstance) {
        chartInstance.data.labels = labels;
        chartInstance.data.datasets[0].data = posts;
        chartInstance.data.datasets[1].data = replies;
        chartInstance.update();
        return;
    }
    
    chartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Total Posts',
                    data: posts,
                    backgroundColor: 'rgba(16, 185, 129, 0.7)',
                    borderColor: '#10b981',
                    borderWidth: 1
                },
                {
                    label: 'Total Replies',
                    data: replies,
                    backgroundColor: 'rgba(251, 191, 36, 0.7)',
                    borderColor: '#fbbf24',
                    borderWidth: 1
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { beginAtZero: true, grid: { color: '#333' }, ticks: { color: '#a0a0a0' } },
                x: { grid: { display: false }, ticks: { color: '#a0a0a0' } }
            },
            plugins: {
                legend: { labels: { color: '#f5f5f5' } }
            }
        }
    });
}

async function openSettings() {
    try {
        const resSettings = await fetch('/api/settings');
        const settings = await resSettings.json();
        
        const resStatus = await fetch('/api/status');
        const statusData = await resStatus.json();
        
        document.getElementById('settings-blocklist').value = (settings.global?.blocklist || []).join(', ');
        
        const container = document.getElementById('account-settings-container');
        container.innerHTML = '';
        
        ['account1', 'account2', 'account3'].forEach((acc) => {
            const accSet = settings[acc] || {};
            const minG = accSet.min_gap_hours || 2;
            const maxG = accSet.max_gap_hours || 3.5;
            const isAppr = accSet.approval_mode || false;
            const isSync = accSet.sync_x || false;
            
            const displayName = (statusData[acc] && statusData[acc].name) ? statusData[acc].name : acc;
            
            container.innerHTML += `
                <div class="settings-group">
                    <h3>${displayName} Settings</h3>
                    <div class="setting-item">
                        <span>Approval Mode (No Auto-Post)</span>
                        <label class="switch">
                            <input type="checkbox" id="set-${acc}-approval" ${isAppr ? 'checked' : ''}>
                            <span class="slider"></span>
                        </label>
                    </div>
                    <div class="setting-item">
                        <span>Enable X (Twitter) Sync</span>
                        <label class="switch">
                            <input type="checkbox" id="set-${acc}-xsync" ${isSync ? 'checked' : ''}>
                            <span class="slider"></span>
                        </label>
                    </div>
                    <div class="setting-item">
                        <span>Post Gap (Min / Max Hrs)</span>
                        <div style="display: flex; gap: 8px; align-items: center;">
                            <input type="number" id="set-${acc}-min" value="${minG}" step="0.5" min="0.5">
                            <span>-</span>
                            <input type="number" id="set-${acc}-max" value="${maxG}" step="0.5" min="1">
                        </div>
                    </div>
                </div>
            `;
        });
        
        document.getElementById('settings-modal').classList.add('active');
    } catch(e) {
        alert('Failed to load settings');
    }
}

async function saveSettings() {
    const blocklistRaw = document.getElementById('settings-blocklist').value;
    const blocklist = blocklistRaw.split(',').map(s => s.trim()).filter(s => s);
    
    const settings = {
        global: { blocklist }
    };
    
    ['account1', 'account2', 'account3'].forEach((acc) => {
        settings[acc] = {
            approval_mode: document.getElementById(`set-${acc}-approval`).checked,
            sync_x: document.getElementById(`set-${acc}-xsync`).checked,
            min_gap_hours: parseFloat(document.getElementById(`set-${acc}-min`).value),
            max_gap_hours: parseFloat(document.getElementById(`set-${acc}-max`).value)
        };
    });
    
    try {
        await fetch('/api/settings', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(settings)
        });
        closeModal('settings-modal');
        fetchStatus(true);
    } catch(e) {
        alert('Failed to save settings');
    }
}

async function approvePost(account, index, action) {
    try {
        await fetch(`/api/approve_post/${account}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ index, action })
        });
        fetchStatus(true);
    } catch(e) {
        alert('Failed to ' + action + ' post.');
    }
}

async function submitReviewReply(account, index) {
    const textObj = document.getElementById(`review-reply-${account}-${index}`);
    if (!textObj) return;
    const reply_text = textObj.value;
    
    try {
        await fetch(`/api/reply_review/${account}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ index, reply_text })
        });
        fetchStatus(true);
    } catch(e) {
        alert('Failed to send reply.');
    }
}

async function dismissReview(account, index) {
    try {
        await fetch(`/api/reply_review/${account}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ index, reply_text: "" })
        });
        fetchStatus(true);
    } catch(e) {
        alert('Failed to dismiss review.');
    }
}

function toggleHelp() {
    const help = document.getElementById('help-content');
    help.style.display = help.style.display === 'none' ? 'block' : 'none';
}

// Initial fetch and polling
fetchStatus();
setInterval(fetchStatus, 10000); // Poll every 10s
