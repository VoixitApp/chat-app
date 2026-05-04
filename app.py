import sqlite3
import os
from flask import Response, Flask, request, render_template_string, redirect, url_for
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
# DATABASE INIT
# ======================
def init_db():
    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS chats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        title TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER,
        role TEXT,
        content TEXT
    )""")

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
# HTML
# ======================
HTML = """<!DOCTYPE html>
<html>
<head>
<title>OracleDrop AI</title>
<style>
body { margin:0; font-family:Arial; background:#0f172a; color:white; display:flex; height:100vh;}
#sidebar { width:220px; background:#020617; padding:15px;}
#main { flex:1; display:flex; flex-direction:column;}
#chat { flex:1; overflow-y:auto; padding:20px;}
.message { display:flex; margin-bottom:10px;}
.user { justify-content:flex-end;}
.bot { justify-content:flex-start;}
.bubble { padding:10px; border-radius:10px; max-width:65%;}
.user .bubble { background:#2563eb;}
.bot .bubble { background:#1e293b;}
#input-area { display:flex; padding:10px;}
input { flex:1; padding:10px; background:#1e293b; color:white; border:none;}
button { margin-left:5px; padding:10px;}
</style>
</head>
<body>

<div id="sidebar">
<h3>Chats</h3>
<a href="/new_chat">➕ New</a>
{% for chat in chats %}
<a href="/?chat_id={{chat[0]}}">💬 {{chat[1]}}</a>
{% endfor %}
<hr>
<a href="/logout">Logout</a>
</div>

<div id="main">
<div id="chat">
{% for msg in messages %}
<div class="message {{msg.role}}">
<div class="bubble">{{msg.content}}</div>
</div>
{% endfor %}
</div>

<div id="input-area">
<input id="msg" placeholder="Type..." onkeydown="if(event.key==='Enter')send()">
<button onclick="send()">Send</button>
<button onclick="stop()">⛔</button>
<button onclick="voice()">🎤</button>
</div>
</div>

<script>
let stream=null;

function send(){
let text=document.getElementById("msg").value;
if(!text)return;

let chat=document.getElementById("chat");

chat.innerHTML+=`<div class="message user"><div class="bubble">${text}</div></div>`;

document.getElementById("msg").value="";

let id="bot"+Date.now();
chat.innerHTML+=`<div class="message bot"><div id="${id}" class="bubble">...</div></div>`;

chat.scrollTop=chat.scrollHeight;

stream=new EventSource("/chat?message="+encodeURIComponent(text)+"&chat_id={{current_chat}}");

let full="";

stream.onmessage=e=>{
full+=e.data;
document.getElementById(id).innerText=full;
chat.scrollTop=chat.scrollHeight;
};

stream.onerror=()=>{
stream.close();
speak(full);
};
}

function stop(){
if(stream){
stream.close();
fetch("/stop");
}
}

function voice(){
let r=new(window.SpeechRecognition||window.webkitSpeechRecognition)();
r.start();
r.onresult=e=>{
document.getElementById("msg").value=e.results[0][0].transcript;
send();
};
}

function speak(t){
speechSynthesis.speak(new SpeechSynthesisUtterance(t));
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

    c.execute("SELECT id,title FROM chats WHERE user_id=?", (current_user.id,))
    chats = c.fetchall()

    if not chats:
        c.execute("INSERT INTO chats (user_id,title) VALUES (?,?)",(current_user.id,"First Chat"))
        conn.commit()
        c.execute("SELECT id,title FROM chats WHERE user_id=?", (current_user.id,))
        chats = c.fetchall()

    chat_id = request.args.get("chat_id") or chats[0][0]

    c.execute("SELECT role,content FROM messages WHERE chat_id=?",(chat_id,))
    messages = [{"role":r[0],"content":r[1]} for r in c.fetchall()]

    conn.close()

    return render_template_string(HTML, chats=chats, messages=messages, current_chat=chat_id)

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method=="POST":
        u=request.form["username"]
        p=generate_password_hash(request.form["password"])
        conn=sqlite3.connect("users.db")
        c=conn.cursor()
        try:
            c.execute("INSERT INTO users(username,password) VALUES (?,?)",(u,p))
            conn.commit()
        except:
            return "User exists"
        conn.close()
        return redirect(url_for("login"))
    return '<form method=post><input name=username><input name=password type=password><button>Register</button></form>'

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        u=request.form["username"]
        p=request.form["password"]
        conn=sqlite3.connect("users.db")
        c=conn.cursor()
        c.execute("SELECT id,password FROM users WHERE username=?",(u,))
        user=c.fetchone()
        conn.close()
        if user and check_password_hash(user[1],p):
            login_user(User(user[0]))
            return redirect("/")
        return "Invalid"
    return '<form method=post><input name=username><input name=password type=password><button>Login</button></form>'

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/login")

@app.route("/chat")
@login_required
def chat():
    msg=request.args.get("message")
    chat_id=request.args.get("chat_id")
    uid=current_user.id

    active_streams[uid]=True

    def generate():
        full=""

        conn=sqlite3.connect("users.db")
        c=conn.cursor()

        c.execute("INSERT INTO messages(chat_id,role,content) VALUES (?,?,?)",(chat_id,"user",msg))
        conn.commit()

        c.execute("SELECT role,content FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT 10",(chat_id,))
        history=[{"role":r[0],"content":r[1]} for r in reversed(c.fetchall())]

        try:
            stream=client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[{"role":"system","content":"You are a helpful assistant."}]+history,
                stream=True
            )

            for chunk in stream:
                if not active_streams.get(uid):
                    break

                delta=chunk.choices[0].delta
                if hasattr(delta,"content") and delta.content:
                    full+=delta.content
                    yield f"data: {delta.content}\n\n"

            c.execute("INSERT INTO messages(chat_id,role,content) VALUES (?,?,?)",(chat_id,"assistant",full))
            conn.commit()

        except Exception as e:
            yield f"data: Error: {str(e)}\n\n"

        finally:
            conn.close()
            active_streams[uid]=False

    return Response(generate(), mimetype="text/event-stream", headers={
        "Cache-Control":"no-cache",
        "Connection":"keep-alive"
    })

@app.route("/new_chat")
@login_required
def new_chat():
    conn=sqlite3.connect("users.db")
    c=conn.cursor()
    c.execute("INSERT INTO chats(user_id,title) VALUES (?,?)",(current_user.id,"New Chat"))
    cid=c.lastrowid
    conn.commit()
    conn.close()
    return redirect("/?chat_id="+str(cid))

@app.route("/stop")
@login_required
def stop():
    active_streams[current_user.id]=False
    return "ok"

# ======================
# RUN
# ======================
if __name__ == "__main__":
    app.run(debug=True)