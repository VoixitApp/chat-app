import sqlite3
import os
import time
from flask import Response
from flask import Flask, request, jsonify, render_template_string, redirect, url_for
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from openai import OpenAI
client = OpenAI()

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

    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        role TEXT,
        content TEXT
    )
    """)

    conn.commit()
    conn.close()

init_db()

# ======================
# USER CLASS
# ======================
class User(UserMixin):
    def __init__(self, id):
        self.id = id

@login_manager.user_loader
def load_user(user_id):
    return User(user_id)

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
    font-family: Arial;
    background: #0f172a;
    color: white;
}

#topbar {
    padding: 10px;
    text-align: center;
    background: #020617;
    border-bottom: 1px solid #1e293b;
}

#topbar a {
    color: #38bdf8;
    margin: 0 10px;
    text-decoration: none;
}

#container {
    max-width: 700px;
    margin: auto;
    height: calc(100vh - 50px);
    display: flex;
    flex-direction: column;
}

#header {
    padding: 15px;
    text-align: center;
    border-bottom: 1px solid #1e293b;
}

#chat {
    flex: 1;
    overflow-y: auto;
    padding: 20px;
}

.message {
    display: flex;
    margin-bottom: 15px;
}

.user { justify-content: flex-end; }
.bot { justify-content: flex-start; }

.bubble {
    padding: 12px;
    border-radius: 12px;
    max-width: 70%;
}

.user .bubble { background: #2563eb; }
.bot .bubble { background: #1e293b; }

#input-area {
    display: flex;
    padding: 10px;
    border-top: 1px solid #1e293b;
}

input {
    flex: 1;
    padding: 12px;
    border-radius: 8px;
    border: none;
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
</style>
</head>

<body>

<div id="topbar">
    <a href="/login">Login</a>
    <a href="/register">Register</a>
</div>

<div id="container">

<div id="header">
🤖 OracleDrop | {{username}}
<a href="/logout" style="color:red;">Logout</a>
</div>

<div id="chat">
{% for msg in messages %}
<div class="message {% if msg.role == 'user' %}user{% else %}bot{% endif %}">
<div class="bubble">{{msg.content}}</div>
</div>
{% endfor %}
</div>

<div id="input-area">
<input id="message" placeholder="Type or speak..." />
<button onclick="sendMessage()">Send</button>
<button onclick="startVoice()">🎤</button>
</div>

</div>

<script>

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

    // ✅ STREAMING (GET)
    const evtSource = new EventSource("/chat?message=" + encodeURIComponent(msg));

    let fullText = "";

    evtSource.onmessage = function(event) {
        fullText += event.data;

        document.getElementById(botId).innerText = fullText;
        chat.scrollTop = chat.scrollHeight;
    };

    evtSource.onerror = function() {
        evtSource.close();
        speak(fullText);
    };
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
    username = result[0] if result else "Unknown"

    c.execute("SELECT role, content FROM messages WHERE user_id=? ORDER BY id ASC LIMIT 20",
              (current_user.id,))
    rows = c.fetchall()
    conn.close()

    messages = [{"role": r[0], "content": r[1]} for r in rows]

    return render_template_string(HTML, messages=messages, username=username)


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
        except:
            return "User already exists"

        conn.close()
        return redirect(url_for("login"))

    return '''
    <form method="post">
        <input name="username" placeholder="Username"/>
        <input name="password" type="password"/>
        <button>Register</button>
    </form>
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
    <form method="post">
        <input name="username"/>
        <input name="password" type="password"/>
        <button>Login</button>
    </form>
    '''


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))



@app.route("/chat")
@login_required
def chat():
    user_message = request.args.get("message")

    def generate():
        full_reply = ""

        try:
            response = client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": user_message}
                ],
                stream=True
            )

            for chunk in response:
                delta = chunk.choices[0].delta

                # ✅ FIXED (NO MORE .get ERROR)
                if hasattr(delta, "content") and delta.content:
                    text = delta.content
                    full_reply += text
                    yield f"data: {text}\n\n"

            # ✅ SAVE FULL RESPONSE AFTER STREAM
            conn = sqlite3.connect("users.db")
            c = conn.cursor()

            c.execute("INSERT INTO messages (user_id, role, content) VALUES (?, ?, ?)",
                      (current_user.id, "user", user_message))

            c.execute("INSERT INTO messages (user_id, role, content) VALUES (?, ?, ?)",
                      (current_user.id, "assistant", full_reply))

            conn.commit()
            conn.close()

        except Exception as e:
            yield f"data: Error: {str(e)}\n\n"

    return Response(generate(), mimetype="text/event-stream")
# ======================
# RUN
# ======================
if __name__ == "__main__":
    app.run(debug=True)