"""
MKV Luxury — Slack Interactive App
Original working version + 3 changes:
  1. Fuel options: 1/4, 2/4, 3/4, 4/4
  2. After delivery: posts Pickup + Extension buttons
  3. URL verification challenge handler added
"""

import os, json, hashlib, hmac, time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, unquote_plus
import requests

SLACK_BOT_TOKEN      = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET", "")
PORT                 = int(os.environ.get("PORT", 8080))

HEADERS = {
    "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
    "Content-Type":  "application/json; charset=utf-8",
}

# Change 1: Fuel options updated to 1/4, 2/4, 3/4, 4/4
FUEL_OPTIONS = [
    {"text": {"type": "plain_text", "text": "4/4 — Full"},  "value": "4/4"},
    {"text": {"type": "plain_text", "text": "3/4"},          "value": "3/4"},
    {"text": {"type": "plain_text", "text": "2/4 — Half"},   "value": "2/4"},
    {"text": {"type": "plain_text", "text": "1/4"},          "value": "1/4"},
    {"text": {"type": "plain_text", "text": "0/4 — Empty"},  "value": "0/4"},
]

# ── Slack signature verification ──────────────────────────────────────────────

def verify_slack_signature(body: bytes, timestamp: str, signature: str) -> bool:
    if abs(time.time() - int(timestamp)) > 60 * 5:
        return False
    sig_basestring = f"v0:{timestamp}:{body.decode()}"
    computed = "v0=" + hmac.new(
        SLACK_SIGNING_SECRET.encode(), sig_basestring.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(computed, signature)

# ── Slack helpers ─────────────────────────────────────────────────────────────

def slack_post(endpoint, payload):
    r = requests.post(
        f"https://slack.com/api/{endpoint}",
        headers=HEADERS,
        json=payload,
        timeout=15,
    )
    result = r.json()
    if not result.get("ok"):
        print(f"Slack {endpoint} error: {result.get('error')}")
    return result

def open_modal(trigger_id, modal):
    slack_post("views.open", {"trigger_id": trigger_id, "view": modal})

def post_message(channel, blocks, text, thread_ts=None):
    payload = {"channel": channel, "text": text, "blocks": blocks}
    if thread_ts:
        payload["thread_ts"] = thread_ts
    return slack_post("chat.postMessage", payload)

# ── Value extractor ───────────────────────────────────────────────────────────

def v(state, block_id):
    try:
        val = state["values"][block_id]["value"]
        if isinstance(val, dict):
            return (val.get("selected_option") or {}).get("value") \
                or val.get("selected_date", "") or "—"
        return val or "—"
    except:
        return "—"

# ── Modals ────────────────────────────────────────────────────────────────────

def make_delivery_modal(booking, trigger_id, channel, ts):
    open_modal(trigger_id, {
        "type": "modal",
        "callback_id": "delivery_submit",
        "private_metadata": json.dumps({"channel": channel, "ts": ts, "booking": booking}),
        "title":  {"type": "plain_text", "text": "Vehicle Delivered"},
        "submit": {"type": "plain_text", "text": "Submit"},
        "close":  {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {"type": "section", "text": {"type": "mrkdwn",
                "text": f"*{booking.get('id','—')}* | {booking.get('car','—')} | {booking.get('date','—')} {booking.get('time','')}"}},
            {"type": "divider"},
            {"type": "input", "block_id": "driver_name",
             "label": {"type": "plain_text", "text": "Driver Name"},
             "element": {"type": "plain_text_input", "action_id": "value",
                         "placeholder": {"type": "plain_text", "text": "e.g. Ahmed"}}},
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
                         "options": [
                             {"text": {"type": "plain_text", "text": "Yes"}, "value": "Yes"},
                             {"text": {"type": "plain_text", "text": "No"},  "value": "No"},
                         ]}},
            {"type": "input", "block_id": "remarks",
             "label": {"type": "plain_text", "text": "Remarks"},
             "optional": True,
             "element": {"type": "plain_text_input", "action_id": "value",
                         "multiline": True,
                         "placeholder": {"type": "plain_text", "text": "Optional notes..."}}},
        ]
    })


def make_pickup_modal(booking, trigger_id, channel, ts):
    open_modal(trigger_id, {
        "type": "modal",
        "callback_id": "pickup_submit",
        "private_metadata": json.dumps({"channel": channel, "ts": ts, "booking": booking}),
        "title":  {"type": "plain_text", "text": "Contract Closed"},
        "submit": {"type": "plain_text", "text": "Submit"},
        "close":  {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {"type": "section", "text": {"type": "mrkdwn",
                "text": f"*{booking.get('id','—')}* | {booking.get('car','—')} | Driver: {booking.get('driver','—')} | Out KM: {booking.get('out_km','—')}"}},
            {"type": "divider"},
            {"type": "input", "block_id": "in_km",
             "label": {"type": "plain_text", "text": "In KM"},
             "element": {"type": "plain_text_input", "action_id": "value",
                         "placeholder": {"type": "plain_text", "text": "e.g. 12850"}}},
            {"type": "input", "block_id": "extra_km", "optional": True,
             "label": {"type": "plain_text", "text": "Extra KM (if any)"},
             "element": {"type": "plain_text_input", "action_id": "value",
                         "placeholder": {"type": "plain_text", "text": "e.g. 350"}}},
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
                         "placeholder": {"type": "plain_text", "text": "Select payment mode"},
                         "options": [
                             {"text": {"type": "plain_text", "text": "Cash"},          "value": "Cash"},
                             {"text": {"type": "plain_text", "text": "Card"},          "value": "Card"},
                             {"text": {"type": "plain_text", "text": "Bank Transfer"}, "value": "Bank Transfer"},
                         ]}},
            {"type": "input", "block_id": "remarks", "optional": True,
             "label": {"type": "plain_text", "text": "Remarks"},
             "element": {"type": "plain_text_input", "action_id": "value",
                         "multiline": True,
                         "placeholder": {"type": "plain_text", "text": "Optional notes..."}}},
        ]
    })


def make_extension_modal(booking, trigger_id, channel, ts):
    open_modal(trigger_id, {
        "type": "modal",
        "callback_id": "extension_submit",
        "private_metadata": json.dumps({"channel": channel, "ts": ts, "booking": booking}),
        "title":  {"type": "plain_text", "text": "Contract Extension"},
        "submit": {"type": "plain_text", "text": "Submit"},
        "close":  {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {"type": "section", "text": {"type": "mrkdwn",
                "text": f"*{booking.get('id','—')}* | {booking.get('car','—')} | {booking.get('date','—')}"}},
            {"type": "divider"},
            {"type": "input", "block_id": "new_return_date",
             "label": {"type": "plain_text", "text": "New Return Date"},
             "element": {"type": "datepicker", "action_id": "value",
                         "placeholder": {"type": "plain_text", "text": "Select new return date"}}},
            {"type": "input", "block_id": "in_km",
             "label": {"type": "plain_text", "text": "In KM"},
             "element": {"type": "plain_text_input", "action_id": "value",
                         "placeholder": {"type": "plain_text", "text": "e.g. 12850"}}},
            {"type": "input", "block_id": "salik", "optional": True,
             "label": {"type": "plain_text", "text": "Salik"},
             "element": {"type": "plain_text_input", "action_id": "value",
                         "placeholder": {"type": "plain_text", "text": "e.g. AED 25"}}},
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
            {"type": "input", "block_id": "extension_days",
             "label": {"type": "plain_text", "text": "Extension Days"},
             "element": {"type": "plain_text_input", "action_id": "value",
                         "placeholder": {"type": "plain_text", "text": "e.g. 3"}}},
            {"type": "input", "block_id": "extension_amount",
             "label": {"type": "plain_text", "text": "Extension Amount (AED)"},
             "element": {"type": "plain_text_input", "action_id": "value",
                         "placeholder": {"type": "plain_text", "text": "e.g. AED 3,300"}}},
            {"type": "input", "block_id": "extension_amount_collected",
             "label": {"type": "plain_text", "text": "Extension Amount Collected"},
             "element": {"type": "plain_text_input", "action_id": "value",
                         "placeholder": {"type": "plain_text", "text": "e.g. AED 3,300"}}},
            {"type": "input", "block_id": "extension_payment_mode",
             "label": {"type": "plain_text", "text": "Extension Payment Mode"},
             "element": {"type": "static_select", "action_id": "value",
                         "placeholder": {"type": "plain_text", "text": "Select payment mode"},
                         "options": [
                             {"text": {"type": "plain_text", "text": "Cash"},          "value": "Cash"},
                             {"text": {"type": "plain_text", "text": "Card"},          "value": "Card"},
                             {"text": {"type": "plain_text", "text": "Bank Transfer"}, "value": "Bank Transfer"},
                         ]}},
            {"type": "input", "block_id": "remarks", "optional": True,
             "label": {"type": "plain_text", "text": "Remarks"},
             "element": {"type": "plain_text_input", "action_id": "value",
                         "multiline": True,
                         "placeholder": {"type": "plain_text", "text": "Optional notes..."}}},
        ]
    })

# ── Submission handlers ───────────────────────────────────────────────────────

def handle_delivery_submit(payload):
    meta    = json.loads(payload["view"]["private_metadata"])
    channel = meta["channel"]
    ts      = meta["ts"]
    booking = meta["booking"]
    state   = payload["view"]["state"]
    user    = payload["user"]["name"]

    driver  = v(state, "driver_name")
    out_km  = v(state, "out_km")
    fuel    = v(state, "fuel_level")
    photos  = v(state, "photos_uploaded")
    remarks = v(state, "remarks")

    # Pass driver and out_km forward to pickup/extension buttons
    booking["driver"] = driver
    booking["out_km"] = out_km
    booking_json = json.dumps(booking)

    # Change 2: Post delivery completed + Pickup/Extension buttons
    post_message(channel, [
        {"type": "section", "text": {"type": "mrkdwn",
            "text": (
                f"✅ *DELIVERY COMPLETED*\n"
                f"```\n"
                f"{'Driver':<14}: {driver}\n"
                f"{'Out KM':<14}: {out_km}\n"
                f"{'Fuel Level':<14}: {fuel}\n"
                f"{'Photos':<14}: {photos}\n"
                f"{'Remarks':<14}: {remarks}\n"
                f"```"
            )}},
        {"type": "divider"},
        {"type": "actions", "elements": [
            {"type": "button",
             "text": {"type": "plain_text", "text": "🔑  Pickup"},
             "style": "primary",
             "action_id": "open_pickup",
             "value": booking_json},
            {"type": "button",
             "text": {"type": "plain_text", "text": "📋  Extension"},
             "action_id": "open_extension",
             "value": booking_json},
        ]},
        {"type": "context", "elements": [{"type": "mrkdwn",
            "text": f"Submitted by @{user} | Pickup: PENDING"}]},
    ], f"✅ Delivery completed by {user}", thread_ts=ts)


def handle_pickup_submit(payload):
    meta    = json.loads(payload["view"]["private_metadata"])
    channel = meta["channel"]
    ts      = meta["ts"]
    state   = payload["view"]["state"]
    user    = payload["user"]["name"]

    post_message(channel, [
        {"type": "section", "text": {"type": "mrkdwn",
            "text": (
                f"✅ *CONTRACT CLOSED*\n"
                f"```\n"
                f"{'In KM':<16}: {v(state,'in_km')}\n"
                f"{'Extra KM':<16}: {v(state,'extra_km')}\n"
                f"{'Salik':<16}: {v(state,'salik')}\n"
                f"{'Fines':<16}: {v(state,'fines')}\n"
                f"{'Fuel Charge':<16}: {v(state,'fuel_charge')}\n"
                f"{'Damage':<16}: {v(state,'damage_charges')}\n"
                f"{'Amt Collected':<16}: {v(state,'amount_collected')}\n"
                f"{'Payment Mode':<16}: {v(state,'payment_mode')}\n"
                f"{'Remarks':<16}: {v(state,'remarks')}\n"
                f"```\n"
                f"*CONTRACT CLOSED — NO FURTHER ACTION REQUIRED*"
            )}},
        {"type": "context", "elements": [{"type": "mrkdwn",
            "text": f"Submitted by @{user}"}]},
    ], f"✅ Contract closed by {user}", thread_ts=ts)


def handle_extension_submit(payload):
    meta    = json.loads(payload["view"]["private_metadata"])
    channel = meta["channel"]
    ts      = meta["ts"]
    state   = payload["view"]["state"]
    user    = payload["user"]["name"]
    booking = meta["booking"]

    post_message(channel, [
        {"type": "section", "text": {"type": "mrkdwn",
            "text": (
                f"📋 *CONTRACT EXTENDED*\n"
                f"```\n"
                f"{'New Return Date':<20}: {v(state,'new_return_date')}\n"
                f"{'Extension Days':<20}: {v(state,'extension_days')}\n"
                f"{'In KM':<20}: {v(state,'in_km')}\n"
                f"{'Salik':<20}: {v(state,'salik')}\n"
                f"{'Fines':<20}: {v(state,'fines')}\n"
                f"{'Fuel Charge':<20}: {v(state,'fuel_charge')}\n"
                f"{'Damage':<20}: {v(state,'damage_charges')}\n"
                f"{'Ext Amount':<20}: {v(state,'extension_amount')}\n"
                f"{'Ext Collected':<20}: {v(state,'extension_amount_collected')}\n"
                f"{'Payment Mode':<20}: {v(state,'extension_payment_mode')}\n"
                f"{'Remarks':<20}: {v(state,'remarks')}\n"
                f"```\n"
                f"*CONTRACT ACTIVE — EXTENDED | Final Pickup: PENDING*"
            )}},
        {"type": "divider"},
        {"type": "actions", "elements": [
            {"type": "button",
             "text": {"type": "plain_text", "text": "🔑  Pickup"},
             "style": "primary",
             "action_id": "open_pickup",
             "value": json.dumps(booking)},
        ]},
        {"type": "context", "elements": [{"type": "mrkdwn",
            "text": f"Submitted by @{user}"}]},
    ], f"📋 Contract extended by {user}", thread_ts=ts)

# ── HTTP Handler — original working version ───────────────────────────────────

class SlackHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"[{self.address_string()}] {format % args}")

    def respond(self, code=200, body=b""):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        # Health check
        self.respond(200, b'{"status":"ok","service":"MKV Slack App"}')

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length)
        ts     = self.headers.get("X-Slack-Request-Timestamp", "0")
        sig    = self.headers.get("X-Slack-Signature", "")

        if self.path == "/slack/actions":

            # Change 3: Handle Slack URL verification challenge
            try:
                json_body = json.loads(body.decode())
                if json_body.get("type") == "url_verification":
                    challenge = json_body.get("challenge", "")
                    print(f"URL verification challenge received")
                    self.respond(200, json.dumps({"challenge": challenge}).encode())
                    return
            except:
                pass

            # Verify signature
            if not verify_slack_signature(body, ts, sig):
                print("Signature verification failed")
                self.respond(401, b'{"error":"invalid signature"}')
                return

            raw     = parse_qs(body.decode())
            payload = json.loads(unquote_plus(raw.get("payload", ["{}"])[0]))
            p_type  = payload.get("type")

            if p_type == "block_actions":
                action_id = payload["actions"][0]["action_id"]
                trigger   = payload["trigger_id"]
                channel   = payload["container"]["channel_id"]
                msg_ts    = payload["container"]["message_ts"]
                try:
                    booking = json.loads(payload["actions"][0].get("value", "{}"))
                except:
                    booking = {}

                if action_id == "open_delivery":
                    make_delivery_modal(booking, trigger, channel, msg_ts)
                elif action_id == "open_pickup":
                    make_pickup_modal(booking, trigger, channel, msg_ts)
                elif action_id == "open_extension":
                    make_extension_modal(booking, trigger, channel, msg_ts)

                self.respond(200, b"")

            elif p_type == "view_submission":
                cb = payload["view"]["callback_id"]
                if cb == "delivery_submit":
                    handle_delivery_submit(payload)
                elif cb == "pickup_submit":
                    handle_pickup_submit(payload)
                elif cb == "extension_submit":
                    handle_extension_submit(payload)
                self.respond(200, b'{"response_action":"clear"}')
            else:
                self.respond(200, b"")

        else:
            self.respond(200, b'{"status":"ok"}')

# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"MKV Slack App running on 0.0.0.0:{PORT}")
    server = HTTPServer(("0.0.0.0", PORT), SlackHandler)
    print(f"Server ready — listening on port {PORT}")
    server.serve_forever()
