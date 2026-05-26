import os, json, hashlib, hmac, time, threading
from http.server import HTTPServer, BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote_plus
import requests

SLACK_BOT_TOKEN      = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET", "")
PORT                 = int(os.environ.get("PORT", 3000))

# ── Hardcoded channel IDs — do not use env vars ──────────────────────
CHANNEL_DELIVERY = "C0ABLDUAZ0B"   # #mkv-delivery
CHANNEL_PICKUP   = "C0ABW979FML"   # #mkv-car-pickup

HEADERS = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}", "Content-Type": "application/json; charset=utf-8"}

from datetime import datetime, timezone, timedelta

FUEL_OPTIONS = [
    {"text": {"type": "plain_text", "text": "4/4 — Full"},  "value": "4/4"},
    {"text": {"type": "plain_text", "text": "3/4"},          "value": "3/4"},
    {"text": {"type": "plain_text", "text": "2/4 — Half"},   "value": "2/4"},
    {"text": {"type": "plain_text", "text": "1/4"},          "value": "1/4"},
    {"text": {"type": "plain_text", "text": "0/4 — Empty"},  "value": "0/4"},
]

def slack(endpoint, payload):
    r = requests.post(f"https://slack.com/api/{endpoint}", headers=HEADERS, json=payload, timeout=15)
    res = r.json()
    if not res.get("ok"): print(f"Slack error [{endpoint}]: {res.get('error')}")
    return res

def open_modal(trigger_id, modal): slack("views.open", {"trigger_id": trigger_id, "view": modal})

def post_msg(channel, blocks, text, ts=None):
    p = {"channel": channel, "text": text, "blocks": blocks}
    if ts: p["thread_ts"] = ts
    slack("chat.postMessage", p)

def val(state, block_id):
    try:
        block = state["values"][block_id]
        for action_id, action in block.items():
            if not isinstance(action, dict):
                continue
            if action.get("value") is not None:
                return str(action["value"])
            if action.get("selected_option"):
                return action["selected_option"]["value"]
            if action.get("selected_date"):
                return action["selected_date"]
        return "—"
    except:
        return "—"

def verify(body, ts, sig):
    try:
        if abs(time.time() - int(ts)) > 300: return False
        base = f"v0:{ts}:{body.decode()}"
        comp = "v0=" + hmac.new(SLACK_SIGNING_SECRET.encode(), base.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(comp, sig)
    except: return False

def delivery_modal(b, trigger, ch, ts):
    open_modal(trigger, {"type":"modal","callback_id":"delivery_submit",
        "private_metadata": json.dumps({"channel":ch,"ts":ts,"booking":b}),
        "title":{"type":"plain_text","text":"Vehicle Delivered"},
        "submit":{"type":"plain_text","text":"Submit"},
        "close":{"type":"plain_text","text":"Cancel"},
        "blocks":[
            {"type":"section","text":{"type":"mrkdwn","text":f"*{b.get('id','—')}* | {b.get('car','—')} | {b.get('date','—')} {b.get('time','')}"}},
            {"type":"divider"},
            {"type":"input","block_id":"driver_name","label":{"type":"plain_text","text":"Driver Name"},
             "element":{"type":"plain_text_input","action_id":"value","placeholder":{"type":"plain_text","text":"e.g. Ahmed"}}},
            {"type":"input","block_id":"out_km","label":{"type":"plain_text","text":"Out KM"},
             "element":{"type":"plain_text_input","action_id":"value","placeholder":{"type":"plain_text","text":"e.g. 12500"}}},
            {"type":"input","block_id":"fuel_level","label":{"type":"plain_text","text":"Fuel Level"},
             "element":{"type":"static_select","action_id":"value","placeholder":{"type":"plain_text","text":"Select fuel level"},"options":FUEL_OPTIONS}},
            {"type":"input","block_id":"photos_uploaded","label":{"type":"plain_text","text":"Photos Uploaded"},
             "element":{"type":"static_select","action_id":"value","placeholder":{"type":"plain_text","text":"Select"},
             "options":[{"text":{"type":"plain_text","text":"Yes"},"value":"Yes"},{"text":{"type":"plain_text","text":"No"},"value":"No"}]}},
            {"type":"input","block_id":"remarks","label":{"type":"plain_text","text":"Remarks"},"optional":True,
             "element":{"type":"plain_text_input","action_id":"value","multiline":True,"placeholder":{"type":"plain_text","text":"Optional"}}},
        ]})

def pickup_modal(b, trigger, ch, ts):
    open_modal(trigger, {"type":"modal","callback_id":"pickup_submit",
        "private_metadata": json.dumps({"channel":ch,"ts":ts,"booking":b}),
        "title":{"type":"plain_text","text":"Contract Closed"},
        "submit":{"type":"plain_text","text":"Submit"},
        "close":{"type":"plain_text","text":"Cancel"},
        "blocks":[
            {"type":"section","text":{"type":"mrkdwn","text":f"*{b.get('id','—')}* | {b.get('car','—')} | Driver: {b.get('driver','—')} | Out KM: {b.get('out_km','—')}"}},
            {"type":"divider"},
            {"type":"input","block_id":"in_km","label":{"type":"plain_text","text":"In KM"},
             "element":{"type":"plain_text_input","action_id":"value","placeholder":{"type":"plain_text","text":"e.g. 12850"}}},
            {"type":"input","block_id":"extra_km","label":{"type":"plain_text","text":"Extra KM (if any)"},"optional":True,
             "element":{"type":"plain_text_input","action_id":"value","placeholder":{"type":"plain_text","text":"e.g. 350"}}},
            {"type":"input","block_id":"salik","label":{"type":"plain_text","text":"Salik"},"optional":True,
             "element":{"type":"plain_text_input","action_id":"value","placeholder":{"type":"plain_text","text":"e.g. AED 50"}}},
            {"type":"input","block_id":"fines","label":{"type":"plain_text","text":"Fines"},"optional":True,
             "element":{"type":"plain_text_input","action_id":"value","placeholder":{"type":"plain_text","text":"e.g. AED 0"}}},
            {"type":"input","block_id":"fuel_charge","label":{"type":"plain_text","text":"Fuel Charge"},"optional":True,
             "element":{"type":"plain_text_input","action_id":"value","placeholder":{"type":"plain_text","text":"e.g. AED 0"}}},
            {"type":"input","block_id":"damage_charges","label":{"type":"plain_text","text":"Damage Charges"},"optional":True,
             "element":{"type":"plain_text_input","action_id":"value","placeholder":{"type":"plain_text","text":"e.g. AED 0"}}},
            {"type":"input","block_id":"amount_collected","label":{"type":"plain_text","text":"Amount Collected"},
             "element":{"type":"plain_text_input","action_id":"value","placeholder":{"type":"plain_text","text":"e.g. AED 2,143"}}},
            {"type":"input","block_id":"payment_mode","label":{"type":"plain_text","text":"Payment Mode"},
             "element":{"type":"static_select","action_id":"value","placeholder":{"type":"plain_text","text":"Select"},
             "options":[{"text":{"type":"plain_text","text":"Cash"},"value":"Cash"},{"text":{"type":"plain_text","text":"Card"},"value":"Card"},{"text":{"type":"plain_text","text":"Bank Transfer"},"value":"Bank Transfer"},{"text":{"type":"plain_text","text":"Crypto"},"value":"Crypto"}]}},
            {"type":"input","block_id":"remarks","label":{"type":"plain_text","text":"Remarks"},"optional":True,
             "element":{"type":"plain_text_input","action_id":"value","multiline":True,"placeholder":{"type":"plain_text","text":"Optional"}}},
        ]})

def handle_delivery(payload):
    try:
        meta    = json.loads(payload["view"]["private_metadata"])
        state   = payload["view"]["state"]
        user    = payload["user"]["name"]
        booking = meta.get("booking", {})
        driver  = val(state, "driver_name")
        out_km  = val(state, "out_km")
        booking.update({"driver": driver, "out_km": out_km})
        now_str = datetime.now(timezone(timedelta(hours=4))).strftime("%d %b %Y | %I:%M %p Dubai Time")
        post_msg(CHANNEL_DELIVERY, [
            {"type": "header", "text": {"type": "plain_text", "text": "🚗 DELIVERY COMPLETED"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": (
                f"```\n"
                f"{'AGR#':<14}: {booking.get('id','—')}\n"
                f"{'Vehicle':<14}: {booking.get('car','—')}\n"
                f"{'Date':<14}: {booking.get('date','—')}  {booking.get('time','')}\n"
                f"{'Location':<14}: {booking.get('location','—')}\n"
                f"{'─' * 36}\n"
                f"{'Driver':<14}: {driver}\n"
                f"{'Out KM':<14}: {out_km}\n"
                f"{'Fuel Level':<14}: {val(state,'fuel_level')}\n"
                f"{'Photos':<14}: {val(state,'photos_uploaded')}\n"
                f"{'Remarks':<14}: {val(state,'remarks')}\n"
                f"```"
            )}},
            {"type": "actions", "elements": [
                {"type": "button", "text": {"type": "plain_text", "text": "🔑  Pickup"},
                 "style": "primary", "action_id": "open_pickup", "value": json.dumps(booking)},
            ]},
            {"type": "context", "elements": [{"type": "mrkdwn",
                "text": f"Submitted by @{user}  |  {now_str}  |  Status: PENDING PICKUP"}]},
        ], f"✅ Delivery completed — {booking.get('id','—')} | {booking.get('car','—')}")
        print(f"  handle_delivery: posted to CHANNEL_DELIVERY {CHANNEL_DELIVERY}")
    except Exception as e:
        import traceback
        print(f"  handle_delivery ERROR: {e}\n{traceback.format_exc()}")

def handle_pickup(payload):
    try:
        meta    = json.loads(payload["view"]["private_metadata"])
        state   = payload["view"]["state"]
        user    = payload["user"]["name"]
        booking = meta.get("booking", {})
        in_km   = val(state, "in_km")
        out_km  = booking.get("out_km", "—")
        now_str = datetime.now(timezone(timedelta(hours=4))).strftime("%d %b %Y | %I:%M %p Dubai Time")

        # Auto-calculate KM driven
        try:
            km_driven = str(int(float(in_km)) - int(float(out_km)))
        except:
            km_driven = "—"

        post_msg(CHANNEL_PICKUP, [
            {"type": "header", "text": {"type": "plain_text", "text": "🔑 CONTRACT CLOSED"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": (
                f"```\n"
                f"{'AGR#':<16}: {booking.get('id','—')}\n"
                f"{'Vehicle':<16}: {booking.get('car','—')}\n"
                f"{'Driver':<16}: {booking.get('driver','—')}\n"
                f"{'─' * 36}\n"
                f"{'Out KM':<16}: {out_km}\n"
                f"{'In KM':<16}: {in_km}\n"
                f"{'KM Driven':<16}: {km_driven}\n"
                f"{'Extra KM':<16}: {val(state,'extra_km')}\n"
                f"{'─' * 36}\n"
                f"{'Salik':<16}: {val(state,'salik')}\n"
                f"{'Fines':<16}: {val(state,'fines')}\n"
                f"{'Fuel Charge':<16}: {val(state,'fuel_charge')}\n"
                f"{'Damage':<16}: {val(state,'damage_charges')}\n"
                f"{'─' * 36}\n"
                f"{'Amt Collected':<16}: {val(state,'amount_collected')}\n"
                f"{'Payment Mode':<16}: {val(state,'payment_mode')}\n"
                f"{'Remarks':<16}: {val(state,'remarks')}\n"
                f"```\n"
                f"*CONTRACT CLOSED — NO FURTHER ACTION REQUIRED*"
            )}},
            {"type": "context", "elements": [{"type": "mrkdwn",
                "text": f"Submitted by @{user}  |  {now_str}"}]},
        ], f"🔑 Contract closed — {booking.get('id','—')} | {booking.get('car','—')} | KM Driven: {km_driven}")
        print(f"  handle_pickup: posted to CHANNEL_PICKUP {CHANNEL_PICKUP}")
    except Exception as e:
        import traceback
        print(f"  handle_pickup ERROR: {e}\n{traceback.format_exc()}")

# ── HTTP Handler ──────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, f, *a): print(f"[{self.address_string()}] {f%a}")

    def send_json(self, code=200, body=b""):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()

    def do_GET(self):
        print(f"GET {self.path}")
        self.send_json(200, b'{"status":"ok","service":"MKV Slack App"}')

    def do_POST(self):
        n    = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n)
        ts   = self.headers.get("X-Slack-Request-Timestamp", "0")
        sig  = self.headers.get("X-Slack-Signature", "")
        print(f"POST {self.path} [{n} bytes]")

        # URL verification challenge
        try:
            jb = json.loads(body.decode())
            if jb.get("type") == "url_verification":
                print("URL verification OK")
                self.send_json(200, json.dumps({"challenge": jb["challenge"]}).encode())
                return
        except: pass

        if not verify(body, ts, sig):
            print("Sig failed")
            self.send_json(401, b'{"error":"invalid_signature"}')
            return

        raw     = parse_qs(body.decode())
        payload = json.loads(unquote_plus(raw.get("payload", ["{}"])[0]))
        ptype   = payload.get("type")
        print(f"Type: {ptype}")

        if ptype == "block_actions":
            aid     = payload["actions"][0]["action_id"]
            trigger = payload["trigger_id"]
            ch      = payload["container"]["channel_id"]
            mts     = payload["container"]["message_ts"]
            try: bk = json.loads(payload["actions"][0].get("value", "{}"))
            except: bk = {}
            print(f"Action: {aid}")
            if aid == "open_delivery":   delivery_modal(bk, trigger, ch, mts)
            elif aid == "open_pickup":   pickup_modal(bk, trigger, ch, mts)

            self.send_json(200, b"")

        elif ptype == "view_submission":
            cb = payload["view"]["callback_id"]
            print(f"Submit: {cb}")
            self.send_json(200, b'{"response_action":"clear"}')
            if cb == "delivery_submit":
                threading.Thread(target=handle_delivery, args=(payload,), daemon=True).start()
            elif cb == "pickup_submit":
                threading.Thread(target=handle_pickup, args=(payload,), daemon=True).start()
        else:
            self.send_json(200, b"")

if __name__ == "__main__":
    print(f"MKV Slack App starting on 0.0.0.0:{PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
