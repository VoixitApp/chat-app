import sqlite3
import os
import time
from flask import Response
from flask import Flask, request, jsonify, render_template_string, redirect, url_for
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from openai import OpenAI
client = OpenAI()
active_streams = {}


# ======================
# APP SETUP
# ======================
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "fallback-secret")

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ======================
# DATABASE INIT
# ======================
def init_db():
    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    # USERS
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT
    )
    """)

    # CHATS (NEW)
    c.execute("""
    CREATE TABLE IF NOT EXISTS chats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        title TEXT
    )
    """)

    # MESSAGES (UPDATED)
    c.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER,
        role TEXT,
        content TEXT
    )
    """)

    conn.commit()
    conn.close()
# ======================
# USER CLASS
# ======================
class User(UserMixin):
    def __init__(self, id):
        self.id = id

@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    c.execute("SELECT id FROM users WHERE id=?", (user_id,))
    user = c.fetchone()
    conn.close()

    if user:
        return User(user_id)
    return None

# ======================
# HTML UI
# ======================
HTML = """
<!DOCTYPE html>
<html>
<head>
<title>OracleDrop AI</title>

<style>
body {
    margin: 0;
    font-family: Arial, sans-serif;
    background: #0f172a;
    color: white;
    display: flex;
    height: 100vh;
}

/* ===== SIDEBAR ===== */
#sidebar {
    width: 220px;
    background: #020617;
    border-right: 1px solid #1e293b;
    padding: 15px;
}

#sidebar h2 {
    font-size: 16px;
    margin-bottom: 20px;
}

#sidebar a {
    display: block;
    color: #38bdf8;
    text-decoration: none;
    margin-bottom: 10px;
}

/* ===== MAIN ===== */
#main {
    flex: 1;
    display: flex;
    flex-direction: column;
}

/* HEADER */
#header {
    padding: 15px;
    border-bottom: 1px solid #1e293b;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

/* CHAT AREA */
#chat {
    flex: 1;
    overflow-y: auto;
    padding: 20px;
}

/* MESSAGES */
.message {
    display: flex;
    margin-bottom: 15px;
}

.user { justify-content: flex-end; }
.bot { justify-content: flex-start; }

.bubble {
    padding: 12px 15px;
    border-radius: 12px;
    max-width: 65%;
    line-height: 1.4;
    font-size: 14px;
}

.user .bubble {
    background: #2563eb;
}

.bot .bubble {
    background: #1e293b;
}

/* INPUT */
#input-area {
    display: flex;
    padding: 10px;
    border-top: 1px solid #1e293b;
    background: #020617;
}

input {
    flex: 1;
    padding: 12px;
    border-radius: 8px;
    border: none;
    outline: none;
    background: #1e293b;
    color: white;
}

button {
    margin-left: 10px;
    padding: 12px;
    border: none;
    border-radius: 8px;
    background: #2563eb;
    color: white;
    cursor: pointer;
}

button:hover {
    background: #1d4ed8;
}
</style>
</head>

<body>

<!-- SIDEBAR -->
<div id="sidebar">
    <h2>🤖 OracleDrop</h2>
    <a href="/login">Login</a>
    <a href="/register">Register</a>
    <a href="/logout" style="color:red;">Logout</a>

    <h3>Your Chats</h3>

<a href="/new_chat">➕ New Chat</a>

{% for chat in chats %}
    <a href="/?chat_id={{chat[0]}}">
        💬 {{chat[1]}}
    </a>
{% endfor %}

</div>

<!-- MAIN -->
<div id="main">

<div id="header">
    <div>User: {{username}}</div>
    <div>AI Assistant</div>
</div>

<div id="chat">
{% for msg in messages %}
<div class="message {% if msg.role == 'user' %}user{% else %}bot{% endif %}">
    <div class="bubble">{{msg.content}}</div>
</div>
{% endfor %}
</div>

<div id="input-area">
    <input id="message" placeholder="Type a message..." onkeydown="handleKey(event)" />
    <button onclick="sendMessage()">Send</button>
    <button onclick="stopResponse()">⛔ Stop</button>
    <button onclick="startVoice()">🎤</button>
</div>

</div>

<script>

let currentStream = null;

function sendMessage() {
    let msg = document.getElementById("message").value;
    if (!msg) return;

    let chat = document.getElementById("chat");

    chat.innerHTML += `
        <div class="message user">
            <div class="bubble">${msg}</div>
        </div>
    `;

    document.getElementById("message").value = "";

    let botId = "bot-" + Date.now();

    chat.innerHTML += `
        <div class="message bot">
            <div class="bubble" id="${botId}">Typing...</div>
        </div>
    `;

    chat.scrollTop = chat.scrollHeight;

    // ✅ FIX: assign to currentStream
    currentStream = new EventSource(
        "/chat?message=" + encodeURIComponent(msg) + "&chat_id={{current_chat}}"
    );

    let fullText = "";

    currentStream.onmessage = function(event) {
        fullText += event.data;
        document.getElementById(botId).innerText = fullText;
        chat.scrollTop = chat.scrollHeight;
    };

    currentStream.onerror = function() {
        currentStream.close();
        speak(fullText);
    };
}

// 🔥 STOP BUTTON
function stopResponse() {
    if (currentStream) {
        currentStream.close();
        fetch("/stop");
    }
}

// 🔥 ENTER TO SEND
function handleKey(e) {
    if (e.key === "Enter") {
        sendMessage();
    }
}

function startVoice() {
    let recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
    recognition.start();

    recognition.onresult = function(e) {
        document.getElementById("message").value = e.results[0][0].transcript;
        sendMessage();
    };
}

function speak(text) {
    let speech = new SpeechSynthesisUtterance(text);
    speechSynthesis.speak(speech);
}

init_db()

window.onload = () => {
    let chat = document.getElementById("chat");
    chat.scrollTop = chat.scrollHeight;
};
</script>

</body>
</html>
"""

# ======================
# ROUTES
# ======================

@app.route("/")
@login_required
def home():

    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    c.execute("SELECT username FROM users WHERE id=?", (current_user.id,))
    result = c.fetchone()

    # 🔥 THIS IS THE REAL FIX
    if not result:
        logout_user()
        return redirect(url_for("login"))

    username = result[0]
    

    # GET CHATS
    c.execute("SELECT id, title FROM chats WHERE user_id=?", (current_user.id,))
    chats = c.fetchall()

    # 🔥 AUTO CREATE CHAT IF NONE
    if not chats:
        c.execute("INSERT INTO chats (user_id, title) VALUES (?, ?)",
                  (current_user.id, "First Chat"))
        conn.commit()

        c.execute("SELECT id, title FROM chats WHERE user_id=?", (current_user.id,))
        chats = c.fetchall()

    chat_id = request.args.get("chat_id")

    if not chat_id:
        chat_id = chats[0][0]

    # GET MESSAGES
    c.execute("""
        SELECT role, content FROM messages
        WHERE chat_id=?
        ORDER BY id ASC
    """, (chat_id,))
    messages = [{"role": r[0], "content": r[1]} for r in c.fetchall()]

    conn.close()

    return render_template_string(
        HTML,
        username=username,
        messages=messages,
        chats=chats,
        current_chat=chat_id
    )

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = generate_password_hash(request.form["password"])

        conn = sqlite3.connect("users.db")
        c = conn.cursor()

        try:
            c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
            conn.commit()

            user_id = c.lastrowid  # 🔥 get new user id
            login_user(User(user_id))  # 🔥 auto login

        except:
            return "User already exists"

        conn.close()
        return redirect(url_for("login"))

    return '''
    <h2>Register</h2>
    <form method="post">
        <input name="username" placeholder="Username"/>
        <input name="password" type="password"/>
        <button>Register</button>
    </form>

    <p>Already have account? <a href="/login">Login</a></p>
    '''


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = sqlite3.connect("users.db")
        c = conn.cursor()

        c.execute("SELECT id, password FROM users WHERE username=?", (username,))
        user = c.fetchone()
        conn.close()

        if user and check_password_hash(user[1], password):
            login_user(User(user[0]))
            return redirect(url_for("home"))
        else:
            return "Invalid login"

    return '''
    <h2>Login</h2>
    <form method="post">
        <input name="username" placeholder="Username"/>
        <input name="password" type="password"/>
        <button>Login</button>
    </form>

    <p>No account? <a href="/register">Register here</a></p>
    '''


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))



@app.route("/chat")
@login_required
def chat():
    chat_id = request.args.get("chat_id")
    user_message = request.args.get("message")
    user_id = current_user.id

    if not chat_id:
        return "No chat selected"

    active_streams[user_id] = True

    def generate():
        full_reply = ""

        try:
            # 🔥 SAVE USER MESSAGE FIRST
            conn = sqlite3.connect("users.db")
            c = conn.cursor()
            c.execute("INSERT INTO messages (chat_id, role, content) VALUES (?, ?, ?)",
                      (chat_id, "user", user_message))
            conn.commit()
            conn.close()

            response = client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": user_message}
                ],
                stream=True
            )

            for chunk in response:
                if not active_streams.get(user_id):
                    break

                delta = chunk.choices[0].delta

                if hasattr(delta, "content") and delta.content:
                    text = delta.content
                    full_reply += text
                    yield f"data: {text}\n\n"

            # 🔥 SAVE AI RESPONSE
            conn = sqlite3.connect("users.db")
            c = conn.cursor()
            c.execute("INSERT INTO messages (chat_id, role, content) VALUES (?, ?, ?)",
                      (chat_id, "assistant", full_reply))
            conn.commit()
            conn.close()

        except Exception as e:
            yield f"data: Error: {str(e)}\n\n"

        finally:
            active_streams[user_id] = False

    return Response(generate(), mimetype="text/event-stream")


@app.route("/new_chat")
@login_required
def new_chat():
    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    c.execute("INSERT INTO chats (user_id, title) VALUES (?, ?)",
              (current_user.id, "New Chat"))

    chat_id = c.lastrowid

    conn.commit()
    conn.close()

    return redirect(url_for("home", chat_id=chat_id))


@app.route("/stop")
@login_required
def stop():
    active_streams[current_user.id] = False
    return "stopped"
# ======================
# RUN
# ======================
if __name__ == "__main__":
    app.run(debug=True)