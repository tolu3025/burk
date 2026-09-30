import json, os, subprocess, urllib.request, time
from firewall import check_sms, check_request
import db

HOME = os.path.expanduser("~")
BURK = os.path.join(HOME, "burk")
OPENAI_KEY = os.environ["OPENAI_API_KEY"]
BOT_TOKEN = open(os.path.join(BURK, "token.txt")).read().strip()
OFFSET = 0

def http(url, payload, headers):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())

# ---------- telegram ----------
def tg_send(chat_id, text):
    http(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
         {"chat_id": chat_id, "text": text[:4000]},
         {"Content-Type": "application/json"})

def tg_get_updates():
    global OFFSET
    data = http(f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
                {"offset": OFFSET, "timeout": 30},
                {"Content-Type": "application/json"})
    for u in data.get("result", []):
        OFFSET = u["update_id"] + 1
    return data.get("result", [])

# ---------- openai ----------
def oai(messages, tools=None):
    payload = {"model": "gpt-4o-mini", "messages": messages, "max_tokens": 1024}
    if tools:
        payload["tools"] = tools
    return http("https://api.openai.com/v1/chat/completions", payload,
                {"Content-Type": "application/json",
                 "Authorization": f"Bearer {OPENAI_KEY}"})

# ---------- phone tools ----------
def api(*args):
    r = subprocess.run(["termux-api", *args],
                       capture_output=True, text=True, timeout=30)
    try:
        return json.loads(r.stdout)
    except Exception:
        return r.stdout or r.stderr

def sms_list(n=5):
    return api("termux-sms-list", "-l", str(n))

def sms_send(number, text):
    ok, why = check_sms(number, text)
    if not ok:
        return "FIREWALL: " + why
    return api("termux-sms-send", "-n", number, text) or "sent."

def notify(text):
    api("termux-notification", "-t", "Burk", "-c", text)
    return "notified."

def battery():
    return api("termux-battery-status")

def clipboard():
    return api("termux-clipboard-get")

def torch(state="on"):
    api("termux-torch", state)
    return f"torch {state}."

def call(number):
    api("termux-telephony-call", number)
    return f"dialing {number}..."

def remember(text):
    db.save_memory(text)
    return "remembered."

TOOLS = {
    "sms_list": sms_list, "sms_send": sms_send, "notify": notify,
    "battery": battery, "clipboard": clipboard, "torch": torch,
    "call": call, "remember": remember,
}

SCHEMAS = [
  {"type": "function", "function": {"name": "sms_list", "description": "Read last N SMS messages", "parameters": {"type": "object", "properties": {"n": {"type": "integer"}}}}},
  {"type": "function", "function": {"name": "sms_send", "description": "Send an SMS (financial content blocked)", "parameters": {"type": "object", "properties": {"number": {"type": "string"}, "text": {"type": "string"}}, "required": ["number", "text"]}}},
  {"type": "function", "function": {"name": "notify", "description": "Post a notification on the phone", "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}},
  {"type": "function", "function": {"name": "battery", "description": "Get battery status", "parameters": {"type": "object", "properties": {}}}},
  {"type": "function", "function": {"name": "clipboard", "description": "Read clipboard", "parameters": {"type": "object", "properties": {}}}},
  {"type": "function", "function": {"name": "torch", "description": "Toggle flashlight", "parameters": {"type": "object", "properties": {"state": {"type": "string", "enum": ["on", "off"]}}}}},
  {"type": "function", "function": {"name": "call", "description": "Dial a number (user must speak)", "parameters": {"type": "object", "properties": {"number": {"type": "string"}}, "required": ["number"]}}},
  {"type": "function", "function": {"name": "remember", "description": "Save a durable fact about the owner to long-term memory", "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}},
]

SYSTEM = """You are Burk, a personal AI agent living on your owner's Android phone.
You act on their behalf on THIS device only.

ABSOLUTE RULES:
- NEVER perform financial actions: no payments, transfers, purchases, banking,
  OTP/PIN/card numbers, subscriptions, crypto. Ever.
- If asked for anything financial, say: "I can't do anything involving money. Do that yourself."
- Complete tasks fully before replying. Be concise, a little dry-witted.

Use the remember tool when the owner tells you something durable
(name, preferences, schedule, people, projects)."""

# ---------- agent loop ----------
def run_agent(chat_id, user_text):
    ok, why = check_request(user_text)
    if not ok:
        return why

    db.save_message(chat_id, "user", user_text)
    db.log("recv", user_text[:100])

    msgs = [{"role": "system", "content": SYSTEM +
             f"\n\n<memory>\n{db.load_memory()}\n</memory>"}]
    msgs += db.get_history(chat_id)
    msgs.append({"role": "user", "content": user_text})

    for _ in range(8):
        r = oai(msgs, SCHEMAS)
        msg = r["choices"][0]["message"]
        if not msg.get("tool_calls"):
            db.save_message(chat_id, "assistant", msg["content"])
            db.log("reply", msg["content"][:100])
            return msg["content"]
        msgs.append(msg)
        for tc in msg["tool_calls"]:
            args = json.loads(tc["function"]["arguments"] or "{}")
            try:
                out = TOOLS[tc["function"]["name"]](**args)
            except Exception as e:
                out = f"error: {e}"
            db.log(f"tool:{tc['function']['name']}", args)
            msgs.append({"role": "tool", "tool_call_id": tc["id"],
                         "content": str(out)[:2000]})
    return "I hit my tool limit. Try a smaller task."

# ---------- main ----------
if __name__ == "__main__":
    while True:
        try:
            for u in tg_get_updates():
                m = u.get("message")
                if not m or not m.get("text"):
                    continue
                chat_id = m["chat"]["id"]
                text = m["text"]
                if text == "/start":
                    tg_send(chat_id, "Burk online. ⚡ What do you need?")
                else:
                    tg_send(chat_id, run_agent(chat_id, text))
        except Exception as e:
            print("error:", e)
            db.log("error", e)
            time.sleep(5)
