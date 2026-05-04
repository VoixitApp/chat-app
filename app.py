import sqlite3
import os
from flask import Flask, request, redirect, url_for, render_template_string, Response
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from openai import OpenAI

# ======================
# APP SETUP
# ======================
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "fallback-secret")

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

active_streams = {}

# ======================
# DATABASE INIT (FORCE FIX)
# ======================
def init_db():
    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    # 🔥 DROP OLD TABLES (IMPORTANT FIX)
    c.execute("DROP TABLE IF EXISTS messages")
    c.execute("DROP TABLE IF EXISTS chats")

    # USERS
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT
    )
    """)

    # CHATS
    c.execute("""
    CREATE TABLE chats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        title TEXT
    )
    """)

    # MESSAGES
    c.execute("""
    CREATE TABLE messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER,
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
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE id=?", (user_id,))
    user = c.fetchone()
    conn.close()
    return User(user_id) if user else None

# ======================
# HTML UI
# ======================
HTML = """ 
<!DOCTYPE html>
<html>
<head>
<title>OracleDrop AI</title>
<style>
body {margin:0;font-family:Arial;background:#0f172a;color:white;display:flex;height:100vh;}
#sidebar {width:220px;background:#020617;border-right:1px solid #1e293b;padding:15px;}
#sidebar a {display:block;color:#38bdf8;margin-bottom:10px;text-decoration:none;}
#main {flex:1;display:flex;flex-direction:column;}
#header {padding:15px;border-bottom:1px solid #1e293b;display:flex;justify-content:space-between;}
#chat {flex:1;overflow-y:auto;padding:20px;}
.message {display:flex;margin-bottom:15px;}
.user {justify-content:flex-end;}
.bot {justify-content:flex-start;}
.bubble {padding:12px;border-radius:12px;max-width:65%;}
.user .bubble {background:#2563eb;}
.bot .bubble {background:#1e293b;}
#input-area {display:flex;padding:10px;border-top:1px solid #1e293b;}
input {flex:1;padding:12px;border-radius:8px;border:none;background:#1e293b;color:white;}
button {margin-left:10px;padding:12px;border:none;border-radius:8px;background:#2563eb;color:white;}
</style>
</head>

<body>

<div id="sidebar">
    <h3>🤖 OracleDrop</h3>
    <a href="/new_chat">➕ New Chat</a>
    <a href="/logout" style="color:red;">Logout</a>

    <h4>Chats</h4>
    {% for chat in chats %}
        <a href="/?chat_id={{chat[0]}}">💬 {{chat[1]}}</a>
    {% endfor %}
</div>

<div id="main">

<div id="header">
    <div>User: {{username}}</div>
</div>

<div id="chat">
{% for msg in messages %}
<div class="message {% if msg.role == 'user' %}user{% else %}bot{% endif %}">
    <div class="bubble">{{msg.content}}</div>
</div>
{% endfor %}
</div>

<div id="input-area">
    <input id="message" placeholder="Type message..." onkeydown="handleKey(event)">
    <button onclick="sendMessage()">Send</button>
    <button onclick="stopResponse()">⛔</button>
    <button onclick="startVoice()">🎤</button>
    <button onclick="toggleAssistant()">🧠 Assistant</button>
</div>

</div>

<script>

let currentStream = null;
let recognition = null;
let assistantMode = false;
let isSpeaking = false;
let silenceTimer = null;

// =======================
// SEND MESSAGE
// =======================
function sendMessage(){
    let msg = document.getElementById("message").value;
    if(!msg) return;

    let chat = document.getElementById("chat");

    chat.innerHTML += `<div class="message user"><div class="bubble">${msg}</div></div>`;
    document.getElementById("message").value = "";

    let id = "bot-"+Date.now();

    chat.innerHTML += `<div class="message bot"><div class="bubble" id="${id}">...</div></div>`;
    chat.scrollTop = chat.scrollHeight;

    try {
        currentStream = new EventSource("/chat?message="+encodeURIComponent(msg)+"&chat_id={{current_chat}}");
    } catch(e) {
        console.error("Stream error:", e);
        return;
    }

    let full = "";

    currentStream.onmessage = function(e){
        full += e.data;
        document.getElementById(id).innerText = full;
        chat.scrollTop = chat.scrollHeight;
    };

    currentStream.onerror = function(){
        currentStream.close();

        if (assistantMode && full) {
            speak(full);
        }
    };
}

// =======================
// STOP BUTTON
// =======================
function stopResponse(){
    if(currentStream){
        currentStream.close();
    }

    assistantMode = false;

    if(recognition){
        recognition.stop();
    }

    fetch("/stop");
}

// =======================
// ENTER KEY
// =======================
function handleKey(e){
    if(e.key === "Enter"){
        sendMessage();
    }
}

// =======================
// SAFE VOICE INIT
// =======================
function initRecognition(){
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

    if(!SpeechRecognition){
        alert("Voice not supported in this browser");
        return null;
    }

    let rec = new SpeechRecognition();
    rec.lang = "en-US";
    rec.continuous = true;
    rec.interimResults = true;

    rec.onresult = function(event){
        let transcript = "";

        for(let i = event.resultIndex; i < event.results.length; i++){
            transcript += event.results[i][0].transcript;
        }

        document.getElementById("message").value = transcript;

        clearTimeout(silenceTimer);

        silenceTimer = setTimeout(()=>{
            if(!isSpeaking && transcript.trim()){
                sendVoiceMessage(transcript);
            }
        }, 1200);
    };

    rec.onerror = function(e){
        console.log("Voice error:", e.error);
    };

    rec.onend = function(){
        if(assistantMode && !isSpeaking){
            rec.start();
        }
    };

    return rec;
}

// =======================
// ONE-TIME VOICE
// =======================
function startVoice(){
    recognition = initRecognition();
    if(recognition){
        recognition.start();
    }
}

// =======================
// ASSISTANT MODE
// =======================
function toggleAssistant(){
    assistantMode = !assistantMode;

    if(assistantMode){
        recognition = initRecognition();
        if(recognition){
            recognition.start();
        }
        console.log("Assistant ON");
    } else {
        if(recognition){
            recognition.stop();
        }
        console.log("Assistant OFF");
    }
}

// =======================
// SEND VOICE MESSAGE
// =======================
function sendVoiceMessage(text){
    document.getElementById("message").value = text;
    sendMessage();
}

// =======================
// SPEAK
// =======================
function speak(text){
    isSpeaking = true;

    let speech = new SpeechSynthesisUtterance(text);
    speech.lang = "en-US";

    speech.onend = ()=>{
        isSpeaking = false;

        if(assistantMode && recognition){
            recognition.start();
        }
    };

    window.speechSynthesis.speak(speech);
}

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
    user = c.fetchone()

    if not user:
        logout_user()
        return redirect(url_for("login"))

    username = user[0]

    c.execute("SELECT id, title FROM chats WHERE user_id=?", (current_user.id,))
    chats = c.fetchall()

    if not chats:
        c.execute("INSERT INTO chats (user_id, title) VALUES (?, ?)", (current_user.id, "First Chat"))
        conn.commit()
        c.execute("SELECT id, title FROM chats WHERE user_id=?", (current_user.id,))
        chats = c.fetchall()

    chat_id = request.args.get("chat_id")
    if not chat_id:
        chat_id = chats[0][0]

    c.execute("SELECT role, content FROM messages WHERE chat_id=?", (chat_id,))
    rows = c.fetchall()

    conn.close()

    messages = [{"role": r[0], "content": r[1]} for r in rows]

    return render_template_string(HTML, username=username, chats=chats, messages=messages, current_chat=chat_id)

# ======================
# AUTH
# ======================

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method=="POST":
        username=request.form["username"]
        password=generate_password_hash(request.form["password"])

        conn=sqlite3.connect("users.db")
        c=conn.cursor()

        try:
            c.execute("INSERT INTO users (username,password) VALUES (?,?)",(username,password))
            conn.commit()
        except:
            return "User exists"

        conn.close()
        return redirect(url_for("login"))

    return '<form method="post"><input name="username"><input name="password" type="password"><button>Register</button></form>'

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        username=request.form["username"]
        password=request.form["password"]

        conn=sqlite3.connect("users.db")
        c=conn.cursor()
        c.execute("SELECT id,password FROM users WHERE username=?",(username,))
        user=c.fetchone()
        conn.close()

        if user and check_password_hash(user[1],password):
            login_user(User(user[0]))
            return redirect(url_for("home"))

        return "Invalid login"

    return '<form method="post"><input name="username"><input name="password" type="password"><button>Login</button></form>'

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

# ======================
# CHAT STREAM
# ======================

@app.route("/chat")
@login_required
def chat():
    msg=request.args.get("message")
    chat_id=request.args.get("chat_id")
    user_id=current_user.id

    active_streams[user_id]=True

    def generate():
        full=""

        try:
            conn=sqlite3.connect("users.db")
            c=conn.cursor()

            c.execute("INSERT INTO messages (chat_id,role,content) VALUES (?,?,?)",(chat_id,"user",msg))
            conn.commit()
            conn.close()

            response=client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[{"role":"user","content":msg}],
                stream=True
            )

            for chunk in response:
                if not active_streams.get(user_id):
                    break

                delta=chunk.choices[0].delta
                if hasattr(delta,"content") and delta.content:
                    full+=delta.content
                    yield f"data: {delta.content}\n\n"

            conn=sqlite3.connect("users.db")
            c=conn.cursor()
            c.execute("INSERT INTO messages (chat_id,role,content) VALUES (?,?,?)",(chat_id,"assistant",full))
            conn.commit()
            conn.close()

        except Exception as e:
            yield f"data: Error: {str(e)}\n\n"

        active_streams[user_id]=False

    return Response(generate(), mimetype="text/event-stream")

@app.route("/new_chat")
@login_required
def new_chat():
    conn=sqlite3.connect("users.db")
    c=conn.cursor()
    c.execute("INSERT INTO chats (user_id,title) VALUES (?,?)",(current_user.id,"New Chat"))
    chat_id=c.lastrowid
    conn.commit()
    conn.close()
    return redirect(url_for("home",chat_id=chat_id))

@app.route("/stop")
@login_required
def stop():
    active_streams[current_user.id]=False
    return "stopped"

# ======================
# RUN
# ======================
if __name__=="__main__":
    app.run(debug=True)