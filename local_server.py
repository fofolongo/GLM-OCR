"""Minimal OpenAI-compatible API server for GLM-OCR on CPU.

Loads the model using transformers and serves /v1/chat/completions.
Designed for testing — inference on CPU will be slow but functional.
"""

import base64
import json
import re
import time
import uuid
from io import BytesIO

import torch
from flask import Flask, Response, jsonify, request
from PIL import Image
from transformers import AutoModelForImageTextToText, AutoProcessor

MODEL_ID = "zai-org/GLM-OCR"

print(f"Loading processor from {MODEL_ID}...")
processor = AutoProcessor.from_pretrained(MODEL_ID)

print(f"Loading model from {MODEL_ID} (bfloat16 on CPU)...")
model = AutoModelForImageTextToText.from_pretrained(
    MODEL_ID,
    dtype=torch.bfloat16,
    device_map="cpu",
)
model.eval()
print("Model loaded successfully!")

app = Flask(__name__)

CHAT_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SmolVLM Chat</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #111; color: #eee; height: 100dvh;
    display: flex; flex-direction: column;
}
.header {
    padding: 12px 16px; background: #1a1a2e; text-align: center;
    font-size: 1.1rem; font-weight: 600;
}
.messages {
    flex: 1; overflow-y: auto; padding: 12px;
    display: flex; flex-direction: column; gap: 10px;
}
.msg { max-width: 85%; padding: 10px 14px; border-radius: 12px; line-height: 1.5; word-wrap: break-word; }
.msg.user { background: #2a2a4a; align-self: flex-end; }
.msg.assistant { background: #1a1a2e; align-self: flex-start; }
.msg img { max-width: 200px; border-radius: 8px; margin-top: 6px; display: block; }
.msg pre { background: #0d0d1a; padding: 8px; border-radius: 6px; overflow-x: auto; margin: 4px 0; }
.msg code { font-family: 'Courier New', monospace; font-size: 0.9em; }
.input-area {
    padding: 10px 12px; background: #1a1a2e;
    display: flex; gap: 8px; align-items: flex-end;
}
#imagePreview {
    display: none; padding: 8px 12px; background: #1a1a2e;
    border-bottom: 1px solid #333;
}
#imagePreview img { max-height: 80px; border-radius: 6px; }
#imagePreview .remove {
    background: #e94560; color: #fff; border: none; border-radius: 50%;
    width: 22px; height: 22px; cursor: pointer; margin-left: 8px; vertical-align: top;
}
textarea {
    flex: 1; background: #222; color: #eee; border: 1px solid #444;
    border-radius: 10px; padding: 10px 12px; font-size: 1rem;
    resize: none; min-height: 44px; max-height: 120px;
    font-family: inherit;
}
textarea:focus { outline: none; border-color: #e94560; }
button.send {
    background: #e94560; color: #fff; border: none; border-radius: 10px;
    padding: 10px 18px; font-size: 1rem; font-weight: 600; cursor: pointer;
}
button.send:disabled { opacity: 0.4; cursor: not-allowed; }
label.attach {
    background: #333; color: #eee; border-radius: 10px;
    padding: 10px 14px; cursor: pointer; font-size: 1.1rem;
}
.spinner {
    display: inline-block; width: 18px; height: 18px;
    border: 2px solid #555; border-top-color: #e94560; border-radius: 50%;
    animation: spin 0.8s linear infinite; vertical-align: middle; margin-right: 6px;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>
<div class="header">GLM-OCR Chat</div>
<div class="messages" id="messages"></div>
<div id="imagePreview"></div>
<div class="input-area">
    <label class="attach" title="Attach image">
        &#128247;
        <input type="file" id="imageInput" accept="image/*" hidden>
    </label>
    <textarea id="input" rows="1" placeholder="Type a message..." autofocus></textarea>
    <button class="send" id="sendBtn" onclick="send()">Send</button>
</div>
<script>
const messagesDiv = document.getElementById('messages');
const input = document.getElementById('input');
const sendBtn = document.getElementById('sendBtn');
const imageInput = document.getElementById('imageInput');
const imagePreviewDiv = document.getElementById('imagePreview');
let attachedImage = null;
let history = [];

imageInput.addEventListener('change', function() {
    const file = this.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = function(e) {
        attachedImage = e.target.result;
        imagePreviewDiv.innerHTML = '<img src="' + attachedImage + '"><button class="remove" onclick="removeImage()">X</button>';
        imagePreviewDiv.style.display = 'block';
    };
    reader.readAsDataURL(file);
});

function removeImage() {
    attachedImage = null;
    imageInput.value = '';
    imagePreviewDiv.style.display = 'none';
    imagePreviewDiv.innerHTML = '';
}

input.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
});

input.addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = Math.min(this.scrollHeight, 120) + 'px';
});

function addMessage(role, text, imageUrl) {
    const div = document.createElement('div');
    div.className = 'msg ' + role;
    let html = '';
    if (imageUrl) html += '<img src="' + imageUrl + '">';
    html += formatText(text);
    div.innerHTML = html;
    messagesDiv.appendChild(div);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
    return div;
}

function formatText(t) {
    let h = t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    h = h.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
    h = h.replace(/`([^`]+)`/g, '<code>$1</code>');
    h = h.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    h = h.replace(/\n/g, '<br>');
    return h;
}

async function send() {
    const text = input.value.trim();
    if (!text && !attachedImage) return;

    addMessage('user', text || '(image)', attachedImage);

    const content = [];
    if (text) content.push({type: 'text', text: text});
    if (attachedImage) content.push({type: 'image_url', image_url: {url: attachedImage}});

    history.push({role: 'user', content: content});

    const curImage = attachedImage;
    input.value = ''; input.style.height = 'auto';
    removeImage();
    sendBtn.disabled = true;

    const thinking = addMessage('assistant', '<span class="spinner"></span> Thinking...');

    try {
        const resp = await fetch('/v1/chat/completions', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({messages: history, max_tokens: 4096, temperature: 0.1})
        });
        const data = await resp.json();
        const reply = data.choices[0].message.content;
        thinking.innerHTML = formatText(reply);
        history.push({role: 'assistant', content: reply});
    } catch(e) {
        thinking.innerHTML = '<span style="color:#f66">Error: ' + e.message + '</span>';
    }
    sendBtn.disabled = false;
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}
</script>
</body>
</html>"""


@app.route("/")
def index():
    return CHAT_HTML, 200, {"Content-Type": "text/html"}


def decode_image(url: str) -> Image.Image:
    """Decode an image from a data URI, file path, or URL."""
    if url.startswith("data:"):
        # data:image/png;base64,...
        header, b64data = url.split(",", 1)
        img_bytes = base64.b64decode(b64data)
        return Image.open(BytesIO(img_bytes)).convert("RGB")
    elif url.startswith("file://"):
        path = url[7:]
        return Image.open(path).convert("RGB")
    elif url.startswith(("http://", "https://")):
        import requests as req
        resp = req.get(url, timeout=30)
        return Image.open(BytesIO(resp.content)).convert("RGB")
    else:
        return Image.open(url).convert("RGB")


@app.route("/v1/chat/completions", methods=["POST"])
def chat_completions():
    data = request.get_json()
    messages = data.get("messages", [])
    max_tokens = data.get("max_tokens", 4096)
    temperature = data.get("temperature", 0.1)

    # Extract images and text from messages
    images = []
    conversation = []

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if isinstance(content, str):
            conversation.append({"role": role, "content": content})
        elif isinstance(content, list):
            parts = []
            for item in content:
                item_type = item.get("type", "")
                if item_type == "text":
                    parts.append({"type": "text", "text": item["text"]})
                elif item_type in ("image_url", "image"):
                    # Handle both OpenAI format {"type":"image_url","image_url":{"url":...}}
                    # and simplified {"type":"image","image_url":{"url":...}}
                    img_url = None
                    if "image_url" in item and isinstance(item["image_url"], dict):
                        img_url = item["image_url"].get("url")
                    elif "url" in item:
                        img_url = item["url"]
                    if img_url:
                        try:
                            img = decode_image(img_url)
                            images.append(img)
                            parts.append({"type": "image"})
                        except Exception as e:
                            print(f"Failed to decode image: {e}", flush=True)
                    else:
                        # type=image with no URL — just mark as image placeholder
                        parts.append({"type": "image"})
            conversation.append({"role": role, "content": parts})

    # Apply chat template
    text_input = processor.apply_chat_template(
        conversation, tokenize=False, add_generation_prompt=True
    )

    # Process inputs
    if images:
        inputs = processor(
            text=[text_input],
            images=images,
            return_tensors="pt",
            padding=True,
        )
    else:
        inputs = processor(
            text=[text_input],
            return_tensors="pt",
            padding=True,
        )

    # Move to CPU (already there, but explicit)
    inputs = {k: v.to("cpu") if hasattr(v, "to") else v for k, v in inputs.items()}

    # Generate
    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=max_tokens,
            temperature=max(temperature, 0.01),
            do_sample=temperature > 0,
        )

    # Decode only new tokens
    input_len = inputs["input_ids"].shape[1]
    generated = output_ids[0][input_len:]
    text_output = processor.decode(generated, skip_special_tokens=True)

    # Format as OpenAI response
    resp = {
        "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "glm-ocr",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text_output},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": input_len,
            "completion_tokens": len(generated),
            "total_tokens": input_len + len(generated),
        },
    }
    return jsonify(resp)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
