from flask import Flask, request, jsonify, render_template_string
from openai import OpenAI
import os
import json


app = Flask(__name__)

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
def home():
    return render_template_string(HTML)

def is_important(message):
    keywords = ["name", "remember", "my", "i am", "i'm", "important"]
    return any(word in message.lower() for word in keywords)

@app.route("/chat", methods=["POST"])
def chat():
    user_message = request.json["message"]

    conversation_history.append({"role": "user", "content": user_message})

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "You are a wise, intelligent and calm assistant. You give clear, helpful and natural responses."}
            ] + conversation_history[-10:]
        )

        reply = response.choices[0].message.content

        conversation_history.append({"role": "assistant", "content": reply})

        # limit memory
        conversation_history[:] = conversation_history[-50:]

        # save memory
        with open("memory.json", "w") as f:
            json.dump(conversation_history, f)

    except Exception as e:
        print("ERROR:", e)   # 👈 ADD THIS
        reply = str(e)

    return jsonify({"reply": reply})

if __name__ == "__main__":
    app.run(debug=True)