import json
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Basic HTML template for the dashboard
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Rekall Reality Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700&family=Inter:wght@300;400;500&display=swap" rel="stylesheet">
    <style>
        :root {
            --emerald: #10b981;
            --zinc-950: #09090b;
            --zinc-900: #18181b;
            --zinc-800: #27272a;
            --zinc-400: #a1a1aa;
            --glass: rgba(255, 255, 255, 0.03);
            --glass-border: rgba(255, 255, 255, 0.08);
        }
        body {
            background-color: var(--zinc-950);
            color: #fff;
            font-family: 'Inter', sans-serif;
            margin: 0;
            padding: 2rem;
        }
        h1, h2, h3 { font-family: 'Outfit', sans-serif; }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2rem;
            border-bottom: 1px solid var(--glass-border);
            padding-bottom: 1rem;
        }
        .logo { font-size: 1.5rem; font-weight: 700; color: var(--emerald); }
        .badge { font-size: 0.7rem; background: rgba(16,185,129,0.1); color: var(--emerald); padding: 0.2rem 0.5rem; border-radius: 999px; }
        
        .grid { display: grid; grid-template-cols: 1fr 350px; gap: 2rem; }
        .card { background: var(--glass); border: 1px solid var(--glass-border); border-radius: 16px; padding: 1.5rem; overflow: hidden; }
        
        .work-items { list-style: none; padding: 0; }
        .work-item { 
            padding: 1rem; border-bottom: 1px solid var(--glass-border); 
            display: flex; justify-content: space-between; align-items: flex-start;
        }
        .status { font-size: 0.75rem; text-transform: uppercase; padding: 0.2rem 0.4rem; border-radius: 4px; font-weight: 600; }
        .status-todo { background: #3f3f46; color: #d4d4d8; }
        .status-in_progress { background: #1e3a8a; color: #93c5fd; }
        .status-blocked { background: #7f1d1d; color: #fecaca; }
        .status-done { background: #064e3b; color: #6ee7b7; }
        
        .activity-feed { font-size: 0.85rem; }
        .activity-item { padding: 0.75rem 0; border-bottom: 1px solid rgba(255,255,255,0.05); }
        .activity-item .timestamp { color: var(--zinc-400); font-size: 0.7rem; }
        
        pre { background: #000; padding: 1rem; border-radius: 8px; font-size: 0.8rem; overflow-x: auto; color: #d4d4d8; }
    </style>
</head>
<body>
    <div class="header">
        <div class="logo">Rekall <span class="badge">Reality Dashboard</span></div>
        <div id="project-id" style="color: var(--zinc-400)">-</div>
    </div>
    
    <div class="grid">
        <div class="main">
            <div class="card">
                <h2>Active Work Items</h2>
                <div id="work-items-list">Loading...</div>
            </div>
            <div class="card" style="margin-top: 2rem">
                <h2>Raw State</h2>
                <pre id="raw-state">{}</pre>
            </div>
        </div>
        <div class="sidebar">
            <div class="card">
                <h3>Recent Activity</h3>
                <div id="activity-list" class="activity-feed">Loading...</div>
            </div>
        </div>
    </div>

    <script>
        async function refresh() {
            try {
                const res = await fetch('/api/state');
                const data = await res.json();
                
                document.getElementById('project-id').textContent = data.project_config.project_id || 'unnamed-project';
                document.getElementById('raw-state').textContent = JSON.stringify(data, null, 2);
                
                // Render Work Items
                const wiList = document.getElementById('work-items-list');
                wiList.innerHTML = '';
                Object.values(data.work_items).forEach(wi => {
                    const el = document.createElement('div');
                    el.className = 'work-item';
                    el.innerHTML = `
                        <div>
                            <div style="font-weight: 600">${wi.title}</div>
                            <div style="font-size: 0.8rem; color: var(--zinc-400)">${wi.work_item_id}</div>
                        </div>
                        <span class="status status-${wi.status}">${wi.status}</span>
                    `;
                    wiList.appendChild(el);
                });
                
                // Render Activity
                const actList = document.getElementById('activity-list');
                actList.innerHTML = '';
                (data.activity || []).reverse().forEach(act => {
                    const el = document.createElement('div');
                    el.className = 'activity-item';
                    el.innerHTML = `
                        <div class="timestamp">${new Date(act.timestamp).toLocaleString()}</div>
                        <div><strong>${act.actor.actor_id}</strong> ${act.action} ${act.target_type}</div>
                        <div style="color: var(--zinc-400); font-size: 0.75rem">${act.target_id}</div>
                    `;
                    actList.appendChild(el);
                });
                
            } catch (e) {
                console.error("Failed to fetch state", e);
            }
        }
        
        refresh();
        setInterval(refresh, 5000);
    </script>
</body>
</html>
"""

class DashboardHandler(BaseHTTPRequestHandler):
    store = None

    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(DASHBOARD_HTML.encode())
        elif self.path == '/api/state':
            if not self.store:
                self.send_error(500, "Store not initialized")
                return
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            snapshot = self.store.get_snapshot()
            self.wfile.write(json.dumps(snapshot).encode())
        else:
            self.send_error(404)

    def log_message(self, format, *args):
        # Suppress noise
        pass

def start_dashboard(store, port=8888):
    DashboardHandler.store = store
    server = HTTPServer(('127.0.0.1', port), DashboardHandler)
    
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port
