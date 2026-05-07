let currentEditAccount = null;
let currentEditType = null; // 'role' or 'posts'

async function fetchStatus() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();
        renderDashboard(data);
    } catch (error) {
        console.error("Failed to fetch status:", error);
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

const accountNames = {
    "account1": "Solvikz (Main)",
    "account2": "Prettiva & Co.",
    "account3": "STRAYED"
};

function renderDashboard(data) {
    const grid = document.getElementById('dashboard-grid');
    grid.innerHTML = '';

    for (const [acc, info] of Object.entries(data)) {
        const isWarning = info.upcoming_posts && info.upcoming_posts.length === 0;
        const statusClass = info.is_active ? 'active' : (isWarning ? 'warning' : '');
        
        const card = document.createElement('div');
        card.className = 'card';
        card.innerHTML = `
            <div class="card-header">
                <h2>
                    <div class="status-indicator ${statusClass}"></div>
                    ${accountNames[acc] || acc}
                </h2>
                <span style="font-size: 12px; color: var(--text-muted);">
                    <i class="ph ph-clock"></i> Checked ${timeSince(info.last_reply_check)}
                </span>
            </div>
            
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
                <button class="btn-primary" onclick="triggerRun('${acc}')">
                    <i class="ph ph-play"></i> Force Run
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
    try {
        await fetch(`/api/trigger/${account}`, { method: 'POST' });
        alert(`Triggered run for ${accountNames[account] || account}. Check terminal for logs.`);
        setTimeout(fetchStatus, 3000); // Refresh after 3s
    } catch (e) {
        alert('Failed to trigger run.');
    }
}

async function editRole(account) {
    currentEditAccount = account;
    currentEditType = 'role';
    document.getElementById('modal-title').innerText = `Edit Persona: ${accountNames[account] || account}`;
    
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
    document.getElementById('modal-title').innerText = `Edit Queue: ${accountNames[account] || account}`;
    
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

function closeModal() {
    document.getElementById('edit-modal').classList.remove('active');
    currentEditAccount = null;
    currentEditType = null;
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
        closeModal();
        fetchStatus();
    } catch(e) {
        alert('Failed to save data.');
    }
}

// Initial fetch and polling
fetchStatus();
setInterval(fetchStatus, 10000); // Poll every 10s
