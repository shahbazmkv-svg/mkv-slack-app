import os, json, hashlib, hmac, time, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote_plus
from datetime import datetime, timezone, timedelta
import requests

# ── CONFIG ────────────────────────────────────────────────────────────────────
def gcc_now():
    return datetime.now(timezone(timedelta(hours=4))).strftime("%H:%M")

SLACK_BOT_TOKEN      = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET", "")
PORT                 = int(os.environ.get("PORT", 3000))

CHANNEL_BOOKINGS = "C0ABPC606F7"   # #mkv-bookings  (ROOT)
CHANNEL_DELIVERY = "C0ABLDUAZ0B"   # #mkv-delivery
CHANNEL_PICKUP   = "C0ABW979FML"   # #mkv-car-pickup

HEADERS = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}", "Content-Type": "application/json; charset=utf-8"}

FUEL_OPTIONS = [
    {"text": {"type": "plain_text", "text": "4/4 — Full"},  "value": "4/4"},
    {"text": {"type": "plain_text", "text": "3/4"},          "value": "3/4"},
    {"text": {"type": "plain_text", "text": "2/4 — Half"},   "value": "2/4"},
    {"text": {"type": "plain_text", "text": "1/4"},          "value": "1/4"},
    {"text": {"type": "plain_text", "text": "0/4 — Empty"},  "value": "0/4"},
]

# ── HELPERS ───────────────────────────────────────────────────────────────────
def slack(endpoint, payload):
    r = requests.post(f"https://slack.com/api/{endpoint}", headers=HEADERS, json=payload, timeout=15)
    res = r.json()
    if not res.get("ok"): print(f"Slack error [{endpoint}]: {res.get('error')}")
    return res

def open_modal(trigger_id, modal):
    slack("views.open", {"trigger_id": trigger_id, "view": modal})

def post_msg(channel, blocks, text, ts=None):
    p = {"channel": channel, "text": text, "blocks": blocks}
    if ts: p["thread_ts"] = ts
    slack("chat.postMessage", p)

def val(state, block_id):
    try:
        block = state["values"][block_id]
        for action_id, action in block.items():
            if isinstance(action, dict):
                if action.get("value") is not None:
                    return str(action["value"])
                if action.get("selected_option"):
                    return action["selected_option"]["value"]
                if action.get("selected_date"):
                    return action["selected_date"]
        return "—"
    except: return "—"

def verify(body, ts, sig):
    try:
        if abs(time.time() - int(ts)) > 300:
            print(f"verify FAILED: timestamp too old — now={int(time.time())} ts={ts}")
            return False
        base = f"v0:{ts}:{body.decode()}"
        comp = "v0=" + hmac.new(SLACK_SIGNING_SECRET.encode(), base.encode(), hashlib.sha256).hexdigest()
        result = hmac.compare_digest(comp, sig)
        print(f"verify: {'OK' if result else 'FAILED'} | sig={sig[:20]}... | comp={comp[:20]}...")
        return result
    except Exception as e:
        print(f"verify ERROR: {e}")
        return False

# ── MODALS ────────────────────────────────────────────────────────────────────
def delivery_modal(b, trigger, ch, ts):
    open_modal(trigger, {
        "type": "modal", "callback_id": "delivery_submit",
        "private_metadata": json.dumps({"channel": ch, "ts": ts, "booking": b}),
        "title": {"type": "plain_text", "text": "Vehicle Delivered"},
        "submit": {"type": "plain_text", "text": "Submit"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {"type": "section", "text": {"type": "mrkdwn",
                "text": f"*{b.get('id','—')}* | {b.get('car','—')} | {b.get('date','—')} {b.get('time','')}"}},
            {"type": "divider"},
            {"type": "input", "block_id": "driver_name",
             "label": {"type": "plain_text", "text": "Driver Name"},
             "element": {"type": "plain_text_input", "action_id": "value",
                         "placeholder": {"type": "plain_text", "text": "e.g. Ahmed"}}},
            {"type": "input", "block_id": "delivery_time",
             "label": {"type": "plain_text", "text": "Delivery Time (GCC 24h)"},
             "element": {"type": "plain_text_input", "action_id": "value",
                         "initial_value": gcc_now(),
                         "placeholder": {"type": "plain_text", "text": "e.g. 14:30"}}},
            {"type": "input", "block_id": "out_km",
             "label": {"type": "plain_text", "text": "Out KM"},
             "element": {"type": "plain_text_input", "action_id": "value",
                         "placeholder": {"type": "plain_text", "text": "e.g. 12500"}}},
            {"type": "input", "block_id": "fuel_level",
             "label": {"type": "plain_text", "text": "Fuel Level"},
             "element": {"type": "static_select", "action_id": "value",
                         "placeholder": {"type": "plain_text", "text": "Select fuel level"},
                         "options": FUEL_OPTIONS}},
            {"type": "input", "block_id": "photos_uploaded",
             "label": {"type": "plain_text", "text": "Photos Uploaded"},
             "element": {"type": "static_select", "action_id": "value",
                         "placeholder": {"type": "plain_text", "text": "Select"},
                         "options": [{"text": {"type": "plain_text", "text": "Yes"}, "value": "Yes"},
                                     {"text": {"type": "plain_text", "text": "No"},  "value": "No"}]}},
            {"type": "input", "block_id": "remarks", "optional": True,
             "label": {"type": "plain_text", "text": "Remarks"},
             "element": {"type": "plain_text_input", "action_id": "value", "multiline": True,
                         "placeholder": {"type": "plain_text", "text": "Optional"}}},
        ]
    })

def pickup_modal(b, trigger, ch, ts):
    out_km = b.get("out_km", "—")
    open_modal(trigger, {
        "type": "modal", "callback_id": "pickup_submit",
        "private_metadata": json.dumps({"channel": ch, "ts": ts, "booking": b}),
        "title": {"type": "plain_text", "text": "Contract Closed"},
        "submit": {"type": "plain_text", "text": "Submit"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {"type": "section", "text": {"type": "mrkdwn",
                "text": f"*{b.get('id','—')}* | {b.get('car','—')} | Driver: {b.get('driver','—')} | Out KM: {out_km} | Delivered: {b.get('delivery_time','—')}"}},
            {"type": "divider"},
            {"type": "input", "block_id": "in_km",
             "label": {"type": "plain_text", "text": "In KM"},
             "dispatch_action": True,
             "element": {"type": "plain_text_input", "action_id": "in_km_entered",
                         "dispatch_action_config": {"trigger_actions_on": ["on_character_entered"]},
                         "placeholder": {"type": "plain_text", "text": "e.g. 12850"}}},
            {"type": "section", "block_id": "km_driven_display",
             "text": {"type": "mrkdwn", "text": "*KM Driven:* — _(auto-calculated)_"}},
            {"type": "input", "block_id": "in_time",
             "label": {"type": "plain_text", "text": "In Time (GCC 24h)"},
             "element": {"type": "plain_text_input", "action_id": "value",
                         "initial_value": gcc_now(),
                         "placeholder": {"type": "plain_text", "text": "e.g. 18:45"}}},
            {"type": "input", "block_id": "salik", "optional": True,
             "label": {"type": "plain_text", "text": "Salik"},
             "element": {"type": "plain_text_input", "action_id": "value",
                         "placeholder": {"type": "plain_text", "text": "e.g. AED 50"}}},
            {"type": "input", "block_id": "fines", "optional": True,
             "label": {"type": "plain_text", "text": "Fines"},
             "element": {"type": "plain_text_input", "action_id": "value",
                         "placeholder": {"type": "plain_text", "text": "e.g. AED 0"}}},
            {"type": "input", "block_id": "fuel_charge", "optional": True,
             "label": {"type": "plain_text", "text": "Fuel Charge"},
             "element": {"type": "plain_text_input", "action_id": "value",
                         "placeholder": {"type": "plain_text", "text": "e.g. AED 0"}}},
            {"type": "input", "block_id": "damage_charges", "optional": True,
             "label": {"type": "plain_text", "text": "Damage Charges"},
             "element": {"type": "plain_text_input", "action_id": "value",
                         "placeholder": {"type": "plain_text", "text": "e.g. AED 0"}}},
            {"type": "input", "block_id": "amount_collected",
             "label": {"type": "plain_text", "text": "Amount Collected"},
             "element": {"type": "plain_text_input", "action_id": "value",
                         "placeholder": {"type": "plain_text", "text": "e.g. AED 2,143"}}},
            {"type": "input", "block_id": "payment_mode",
             "label": {"type": "plain_text", "text": "Payment Mode"},
             "element": {"type": "static_select", "action_id": "value",
                         "placeholder": {"type": "plain_text", "text": "Select"},
                         "options": [{"text": {"type": "plain_text", "text": "Cash"},          "value": "Cash"},
                                     {"text": {"type": "plain_text", "text": "Card"},          "value": "Card"},
                                     {"text": {"type": "plain_text", "text": "Bank Transfer"}, "value": "Bank Transfer"},
                                     {"text": {"type": "plain_text", "text": "Crypto"},        "value": "Crypto"}]}},
            {"type": "input", "block_id": "remarks", "optional": True,
             "label": {"type": "plain_text", "text": "Remarks"},
             "element": {"type": "plain_text_input", "action_id": "value", "multiline": True,
                         "placeholder": {"type": "plain_text", "text": "Optional"}}},
        ]
    })

# ── HANDLERS ─────────────────────────────────────────────────────────────────
def handle_delivery(payload):
    try:
        meta          = json.loads(payload["view"]["private_metadata"])
        state         = payload["view"]["state"]
        user          = payload["user"]["name"]
        booking       = meta["booking"]
        driver        = val(state, "driver_name")
        delivery_time = val(state, "delivery_time")
        out_km        = val(state, "out_km")
        booking.update({"driver": driver, "out_km": out_km, "delivery_time": delivery_time})
        print(f"handle_delivery: {booking.get('id','—')} → {CHANNEL_DELIVERY}")
        post_msg(CHANNEL_DELIVERY, [
            {"type": "section", "text": {"type": "mrkdwn", "text": (
                f"✅ *DELIVERY COMPLETED*\n```\n"
                f"{'AGR#':<14}: {booking.get('id','—')}\n"
                f"{'Car':<14}: {booking.get('car','—')}\n"
                f"{'Driver':<14}: {driver}\n"
                f"{'Delivery Time':<14}: {delivery_time}\n"
                f"{'Out KM':<14}: {out_km}\n"
                f"{'Fuel Level':<14}: {val(state,'fuel_level')}\n"
                f"{'Photos':<14}: {val(state,'photos_uploaded')}\n"
                f"{'Remarks':<14}: {val(state,'remarks')}\n```"
            )}},
            {"type": "divider"},
            {"type": "actions", "elements": [
                {"type": "button", "text": {"type": "plain_text", "text": "🔑  Pickup"},
                 "style": "primary", "action_id": "open_pickup", "value": json.dumps(booking)},
            ]},
            {"type": "context", "elements": [{"type": "mrkdwn",
                "text": f"Submitted by @{user} | Pickup: PENDING"}]},
        ], f"✅ Delivery completed by {user}")
        print(f"handle_delivery: posted OK")
    except Exception as e:
        print(f"handle_delivery ERROR: {e}")
        import traceback; traceback.print_exc()

def handle_pickup(payload):
    try:
        meta    = json.loads(payload["view"]["private_metadata"])
        state   = payload["view"]["state"]
        user    = payload["user"]["name"]
        booking = meta.get("booking", {})
        in_km_str  = val(state, "in_km")
        out_km_str = booking.get("out_km", "—")
        try:
            driven_str = f"{int(in_km_str) - int(out_km_str)} KM"
        except:
            driven_str = "—"
        print(f"handle_pickup: {booking.get('id','—')} → {CHANNEL_PICKUP}")
        post_msg(CHANNEL_PICKUP, [
            {"type": "section", "text": {"type": "mrkdwn", "text": (
                f"✅ *CONTRACT CLOSED*\n```\n"
                f"{'AGR#':<16}: {booking.get('id','—')}\n"
                f"{'Car':<16}: {booking.get('car','—')}\n"
                f"{'Driver':<16}: {booking.get('driver','—')}\n"
                f"{'─'*34}\n"
                f"{'Out KM':<16}: {out_km_str}\n"
                f"{'Delivered At':<16}: {booking.get('delivery_time','—')}\n"
                f"{'In KM':<16}: {in_km_str}\n"
                f"{'In Time':<16}: {val(state,'in_time')}\n"
                f"{'KM Driven':<16}: {driven_str}\n"
                f"{'─'*34}\n"
                f"{'Salik':<16}: {val(state,'salik')}\n"
                f"{'Fines':<16}: {val(state,'fines')}\n"
                f"{'Fuel Charge':<16}: {val(state,'fuel_charge')}\n"
                f"{'Damage':<16}: {val(state,'damage_charges')}\n"
                f"{'Amt Collected':<16}: {val(state,'amount_collected')}\n"
                f"{'Payment Mode':<16}: {val(state,'payment_mode')}\n"
                f"{'Remarks':<16}: {val(state,'remarks')}\n```\n"
                f"*CONTRACT CLOSED — NO FURTHER ACTION REQUIRED*"
            )}},
            {"type": "context", "elements": [{"type": "mrkdwn",
                "text": f"Submitted by @{user}"}]},
        ], f"✅ Contract closed by {user}")
        print(f"handle_pickup: posted OK")
    except Exception as e:
        print(f"handle_pickup ERROR: {e}")
        import traceback; traceback.print_exc()

def handle_km_update(payload):
    """Live KM Driven update as driver types In KM."""
    try:
        meta    = json.loads(payload["view"]["private_metadata"])
        booking = meta.get("booking", {})
        out_km  = booking.get("out_km", "—")
        in_km   = payload["actions"][0].get("value", "")
        try:
            driven = int(in_km) - int(out_km)
            km_text = f"*KM Driven:* {driven} KM"
        except:
            km_text = "*KM Driven:* — _(auto-calculated)_"

        blocks = payload["view"]["blocks"]
        for block in blocks:
            if block.get("block_id") == "km_driven_display":
                block["text"]["text"] = km_text
                break

        slack("views.update", {
            "view_id": payload["view"]["id"],
            "hash":    payload["view"]["hash"],
            "view": {
                "type":             "modal",
                "callback_id":      "pickup_submit",
                "private_metadata": payload["view"]["private_metadata"],
                "title":            payload["view"]["title"],
                "submit":           payload["view"]["submit"],
                "close":            payload["view"]["close"],
                "blocks":           blocks,
            }
        })
        print(f"KM update: out={out_km} in={in_km} driven={km_text}")
    except Exception as e:
        print(f"handle_km_update ERROR: {e}")

# ── HTTP HANDLER ──────────────────────────────────────────────────────────────
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
            aid = payload["actions"][0]["action_id"]
            print(f"Action: {aid}")

            if aid == "in_km_entered":
                self.send_json(200, b"")
                threading.Thread(target=handle_km_update, args=(payload,), daemon=True).start()

            else:
                trigger = payload["trigger_id"]
                ch      = payload["container"]["channel_id"]
                mts     = payload["container"]["message_ts"]
                try: bk = json.loads(payload["actions"][0].get("value", "{}"))
                except: bk = {}
                if aid == "open_delivery":
                    delivery_modal(bk, trigger, ch, mts)
                elif aid == "open_pickup":
                    pickup_modal(bk, trigger, ch, mts)
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
