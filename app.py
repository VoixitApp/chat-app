import sqlite3
from flask import redirect, url_for
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask import Flask, request, jsonify, render_template_string
from openai import OpenAI
import os
import json


app = Flask(__name__)
app.secret_key = "supersecretkey"

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 🔥 LOAD MEMORY
try:
    with open("memory.json", "r") as f:
        conversation_history = json.load(f)
except:
    conversation_history = []

HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>My AI Chat</title>

    <style>
        body {
            margin: 0;
            font-family: Arial, sans-serif;
            background: #0f172a;
            color: white;
            display: flex;
            justify-content: center;
        }

        #container {
            width: 100%;
            max-width: 700px;
            height: 100vh;
            display: flex;
            flex-direction: column;
        }

        #header {
            padding: 15px;
            text-align: center;
            font-size: 18px;
            border-bottom: 1px solid #1e293b;
        }

        #chat {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
        }

        .message {
            margin-bottom: 15px;
            display: flex;
        }

        .user { justify-content: flex-end; }
        .bot { justify-content: flex-start; }

        .bubble {
            padding: 12px 15px;
            border-radius: 12px;
            max-width: 70%;
            line-height: 1.4;
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

<div>
    <a href="/login">Login</a> |
    <a href="/register">Register</a> |
    <a href="/logout">Logout</a>
</div>

<div id="container">
    <div id="header">🤖 OracleDrop</div>
    <div id="chat"></div>

    <div id="input-area">
        <input id="message" placeholder="Type or speak..." />
        <button onclick="sendMessage()">Send</button>
        <button onclick="startVoice()">🎤</button>
    </div>
</div>

<script>
async function sendMessage() {
    let msg = document.getElementById("message").value;
    if (!msg) return;

    let chat = document.getElementById("chat");

    chat.innerHTML += `
        <div class="message user">
            <div class="bubble">${msg}</div>
        </div>
    `;

    document.getElementById("message").value = "";

    let typingId = "typing-" + Date.now();

    chat.innerHTML += `
        <div class="message bot" id="${typingId}">
            <div class="bubble">Typing...</div>
        </div>
    `;

    chat.scrollTop = chat.scrollHeight;

    let res = await fetch("/chat", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({message: msg})
    });

    let data = await res.json();

    let element = document.getElementById(typingId);
    element.innerHTML = `<div class="bubble"></div>`;

    let bubble = element.querySelector(".bubble");

    let text = data.reply;
    let i = 0;

    function typeEffect() {
        if (i < text.length) {
            bubble.innerHTML += text.charAt(i);
            i++;
            setTimeout(typeEffect, 10);
        } else {
            speak(text);
        }
    }

    typeEffect();
}

function startVoice() {
    let recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
    recognition.lang = "en-US";
    recognition.start();

    recognition.onresult = function(event) {
        let transcript = event.results[0][0].transcript;
        document.getElementById("message").value = transcript;
        sendMessage();
    };
}

function speak(text) {
    let speech = new SpeechSynthesisUtterance(text);
    window.speechSynthesis.speak(speech);
}
</script>

</body>
</html>
"""

@app.route("/")
@login_required
def home():
    return render_template_string(HTML)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = sqlite3.connect("users.db")
        c = conn.cursor()

        try:
            c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
            conn.commit()
        except:
            return "User already exists"

        conn.close()
        return redirect(url_for("login"))

    return """
    <form method="post">
        <input name="username" placeholder="Username"/>
        <input name="password" type="password" placeholder="Password"/>
        <button>Register</button>
    </form>
    """

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = sqlite3.connect("users.db")
        c = conn.cursor()

        c.execute("SELECT id FROM users WHERE username=? AND password=?", (username, password))
        user = c.fetchone()
        conn.close()

        if user:
            login_user(User(user[0]))
            return redirect(url_for("home"))
        else:
            return "Invalid login"

    return """
    <form method="post">
        <input name="username"/>
        <input name="password" type="password"/>
        <button>Login</button>
    </form>
    """

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

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

class User(UserMixin):
    def __init__(self, id):
        self.id = id

@login_manager.user_loader
def load_user(user_id):
    return User(user_id)        

def is_important(message):
    keywords = ["name", "remember", "my", "i am", "i'm", "important"]
    return any(word in message.lower() for word in keywords)

@app.route("/chat", methods=["POST"])
@login_required
def chat():
    user_message = request.json["message"]

    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    # save user message
    c.execute("INSERT INTO messages (user_id, role, content) VALUES (?, ?, ?)",
              (current_user.id, "user", user_message))

    # get last 10 messages
    c.execute("SELECT role, content FROM messages WHERE user_id=? ORDER BY id DESC LIMIT 10",
              (current_user.id,))
    rows = c.fetchall()
    conn.close()

    messages = [{"role": role, "content": content} for role, content in reversed(rows)]

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "system", "content": "You are a helpful assistant."}] + messages
        )

        reply = response.choices[0].message.content

        conn = sqlite3.connect("users.db")
        c = conn.cursor()
        c.execute("INSERT INTO messages (user_id, role, content) VALUES (?, ?, ?)",
                  (current_user.id, "assistant", reply))
        conn.commit()
        conn.close()

    except Exception as e:
        reply = "Error: " + str(e)

    return jsonify({"reply": reply})

if __name__ == "__main__":
    app.run(debug=True)