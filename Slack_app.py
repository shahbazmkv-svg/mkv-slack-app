"""
MKV Luxury — Slack Interactive App
Handles Delivery, Pickup and Contract Extension forms.
Deploy on Railway — set env vars:
  SLACK_BOT_TOKEN
  SLACK_SIGNING_SECRET
"""

import os, json, hashlib, hmac, time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, unquote_plus
import requests

SLACK_BOT_TOKEN     = os.environ["SLACK_BOT_TOKEN"]
SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]
PORT                = int(os.environ.get("PORT", 3000))

HEADERS = {
    "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
    "Content-Type": "application/json; charset=utf-8",
}

# ── Slack signature verification ──────────────────────────────────────────────

def verify_slack_signature(body: bytes, timestamp: str, signature: str) -> bool:
    if abs(time.time() - int(timestamp)) > 60 * 5:
        return False
    sig_basestring = f"v0:{timestamp}:{body.decode()}"
    computed = "v0=" + hmac.new(
        SLACK_SIGNING_SECRET.encode(), sig_basestring.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(computed, signature)

# ── Block Kit builders ────────────────────────────────────────────────────────

def make_delivery_modal(booking: dict, trigger_id: str, channel: str, ts: str):
    modal = {
        "type": "modal",
        "callback_id": "delivery_submit",
        "private_metadata": json.dumps({"channel": channel, "ts": ts, "booking": booking}),
        "title": {"type": "plain_text", "text": "Vehicle Delivered"},
        "submit": {"type": "plain_text", "text": "Submit"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {
                "type": "section",
                "text": {"type": "mrkdwn",
                    "text": f"*Booking ID:* {booking.get('id','—')}  |  *Car:* {booking.get('car','—')}  |  *Date:* {booking.get('date','—')}  |  *Time:* {booking.get('time','—')}"}
            },
            {"type": "divider"},
            {
                "type": "input", "block_id": "driver_name",
                "label": {"type": "plain_text", "text": "Driver Name"},
                "element": {"type": "plain_text_input", "action_id": "value",
                            "placeholder": {"type": "plain_text", "text": "e.g. Ahmed"}}
            },
            {
                "type": "input", "block_id": "out_km",
                "label": {"type": "plain_text", "text": "Out KM"},
                "element": {"type": "plain_text_input", "action_id": "value",
                            "placeholder": {"type": "plain_text", "text": "e.g. 12500"}}
            },
            {
                "type": "input", "block_id": "fuel_level",
                "label": {"type": "plain_text", "text": "Fuel Level"},
                "element": {
                    "type": "static_select", "action_id": "value",
                    "placeholder": {"type": "plain_text", "text": "Select fuel level"},
                    "options": [
                        {"text": {"type": "plain_text", "text": "Full"},   "value": "Full"},
                        {"text": {"type": "plain_text", "text": "3/4"},    "value": "3/4"},
                        {"text": {"type": "plain_text", "text": "Half"},   "value": "Half"},
                        {"text": {"type": "plain_text", "text": "1/4"},    "value": "1/4"},
                        {"text": {"type": "plain_text", "text": "Empty"},  "value": "Empty"},
                    ]
                }
            },
            {
                "type": "input", "block_id": "photos_uploaded",
                "label": {"type": "plain_text", "text": "Photos Uploaded"},
                "element": {
                    "type": "static_select", "action_id": "value",
                    "placeholder": {"type": "plain_text", "text": "Select"},
                    "options": [
                        {"text": {"type": "plain_text", "text": "Yes"}, "value": "Yes"},
                        {"text": {"type": "plain_text", "text": "No"},  "value": "No"},
                    ]
                }
            },
            {
                "type": "input", "block_id": "remarks",
                "label": {"type": "plain_text", "text": "Remarks"},
                "optional": True,
                "element": {"type": "plain_text_input", "action_id": "value", "multiline": True,
                            "placeholder": {"type": "plain_text", "text": "Optional notes..."}}
            },
        ]
    }
    requests.post("https://slack.com/api/views.open",
                  headers=HEADERS,
                  json={"trigger_id": trigger_id, "view": modal})


def make_pickup_modal(booking: dict, trigger_id: str, channel: str, ts: str):
    modal = {
        "type": "modal",
        "callback_id": "pickup_submit",
        "private_metadata": json.dumps({"channel": channel, "ts": ts, "booking": booking}),
        "title": {"type": "plain_text", "text": "Contract Closed"},
        "submit": {"type": "plain_text", "text": "Submit"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {
                "type": "section",
                "text": {"type": "mrkdwn",
                    "text": f"*Booking ID:* {booking.get('id','—')}  |  *Car:* {booking.get('car','—')}  |  *Driver:* {booking.get('driver','—')}  |  *Out KM:* {booking.get('out_km','—')}"}
            },
            {"type": "divider"},
            {
                "type": "input", "block_id": "in_km",
                "label": {"type": "plain_text", "text": "In KM"},
                "element": {"type": "plain_text_input", "action_id": "value",
                            "placeholder": {"type": "plain_text", "text": "e.g. 12850"}}
            },
            {
                "type": "input", "block_id": "extra_km",
                "label": {"type": "plain_text", "text": "Extra KM (if any)"},
                "optional": True,
                "element": {"type": "plain_text_input", "action_id": "value",
                            "placeholder": {"type": "plain_text", "text": "e.g. 350"}}
            },
            {
                "type": "input", "block_id": "salik",
                "label": {"type": "plain_text", "text": "Salik"},
                "optional": True,
                "element": {"type": "plain_text_input", "action_id": "value",
                            "placeholder": {"type": "plain_text", "text": "e.g. AED 50"}}
            },
            {
                "type": "input", "block_id": "fines",
                "label": {"type": "plain_text", "text": "Fines"},
                "optional": True,
                "element": {"type": "plain_text_input", "action_id": "value",
                            "placeholder": {"type": "plain_text", "text": "e.g. AED 0"}}
            },
            {
                "type": "input", "block_id": "fuel_charge",
                "label": {"type": "plain_text", "text": "Fuel Charge"},
                "optional": True,
                "element": {"type": "plain_text_input", "action_id": "value",
                            "placeholder": {"type": "plain_text", "text": "e.g. AED 0"}}
            },
            {
                "type": "input", "block_id": "damage_charges",
                "label": {"type": "plain_text", "text": "Damage Charges"},
                "optional": True,
                "element": {"type": "plain_text_input", "action_id": "value",
                            "placeholder": {"type": "plain_text", "text": "e.g. AED 0"}}
            },
            {
                "type": "input", "block_id": "amount_collected",
                "label": {"type": "plain_text", "text": "Amount Collected"},
                "element": {"type": "plain_text_input", "action_id": "value",
                            "placeholder": {"type": "plain_text", "text": "e.g. AED 2,143"}}
            },
            {
                "type": "input", "block_id": "payment_mode",
                "label": {"type": "plain_text", "text": "Payment Mode"},
                "element": {
                    "type": "static_select", "action_id": "value",
                    "placeholder": {"type": "plain_text", "text": "Select payment mode"},
                    "options": [
                        {"text": {"type": "plain_text", "text": "Cash"},          "value": "Cash"},
                        {"text": {"type": "plain_text", "text": "Card"},          "value": "Card"},
                        {"text": {"type": "plain_text", "text": "Bank Transfer"}, "value": "Bank Transfer"},
                    ]
                }
            },
            {
                "type": "input", "block_id": "remarks",
                "label": {"type": "plain_text", "text": "Remarks"},
                "optional": True,
                "element": {"type": "plain_text_input", "action_id": "value", "multiline": True,
                            "placeholder": {"type": "plain_text", "text": "Optional notes..."}}
            },
        ]
    }
    requests.post("https://slack.com/api/views.open",
                  headers=HEADERS,
                  json={"trigger_id": trigger_id, "view": modal})


def make_extension_modal(booking: dict, trigger_id: str, channel: str, ts: str):
    modal = {
        "type": "modal",
        "callback_id": "extension_submit",
        "private_metadata": json.dumps({"channel": channel, "ts": ts, "booking": booking}),
        "title": {"type": "plain_text", "text": "Contract Extension"},
        "submit": {"type": "plain_text", "text": "Submit"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {
                "type": "section",
                "text": {"type": "mrkdwn",
                    "text": f"*Booking ID:* {booking.get('id','—')}  |  *Car/Plate:* {booking.get('car','—')}  |  *Driver:* {booking.get('driver','—')}  |  *Date:* {booking.get('date','—')}"}
            },
            {"type": "divider"},
            {
                "type": "input", "block_id": "new_return_date",
                "label": {"type": "plain_text", "text": "New Return Date"},
                "element": {"type": "datepicker", "action_id": "value",
                            "placeholder": {"type": "plain_text", "text": "Select new return date"}}
            },
            {
                "type": "input", "block_id": "in_km",
                "label": {"type": "plain_text", "text": "In KM"},
                "element": {"type": "plain_text_input", "action_id": "value",
                            "placeholder": {"type": "plain_text", "text": "e.g. 12850"}}
            },
            {
                "type": "input", "block_id": "salik",
                "label": {"type": "plain_text", "text": "Salik"},
                "optional": True,
                "element": {"type": "plain_text_input", "action_id": "value",
                            "placeholder": {"type": "plain_text", "text": "e.g. AED 25"}}
            },
            {
                "type": "input", "block_id": "fines",
                "label": {"type": "plain_text", "text": "Fines"},
                "optional": True,
                "element": {"type": "plain_text_input", "action_id": "value",
                            "placeholder": {"type": "plain_text", "text": "e.g. AED 0"}}
            },
            {
                "type": "input", "block_id": "fuel_charge",
                "label": {"type": "plain_text", "text": "Fuel Charge"},
                "optional": True,
                "element": {"type": "plain_text_input", "action_id": "value",
                            "placeholder": {"type": "plain_text", "text": "e.g. AED 0"}}
            },
            {
                "type": "input", "block_id": "damage_charges",
                "label": {"type": "plain_text", "text": "Damage Charges"},
                "optional": True,
                "element": {"type": "plain_text_input", "action_id": "value",
                            "placeholder": {"type": "plain_text", "text": "e.g. AED 0"}}
            },
            {
                "type": "input", "block_id": "extension_days",
                "label": {"type": "plain_text", "text": "Extension Days"},
                "element": {"type": "plain_text_input", "action_id": "value",
                            "placeholder": {"type": "plain_text", "text": "e.g. 3"}}
            },
            {
                "type": "input", "block_id": "extension_amount",
                "label": {"type": "plain_text", "text": "Extension Amount (AED)"},
                "element": {"type": "plain_text_input", "action_id": "value",
                            "placeholder": {"type": "plain_text", "text": "e.g. AED 3,300"}}
            },
            {
                "type": "input", "block_id": "extension_amount_collected",
                "label": {"type": "plain_text", "text": "Extension Amount Collected"},
                "element": {"type": "plain_text_input", "action_id": "value",
                            "placeholder": {"type": "plain_text", "text": "e.g. AED 3,300"}}
            },
            {
                "type": "input", "block_id": "extension_payment_mode",
                "label": {"type": "plain_text", "text": "Extension Payment Mode"},
                "element": {
                    "type": "static_select", "action_id": "value",
                    "placeholder": {"type": "plain_text", "text": "Select payment mode"},
                    "options": [
                        {"text": {"type": "plain_text", "text": "Cash"},          "value": "Cash"},
                        {"text": {"type": "plain_text", "text": "Card"},          "value": "Card"},
                        {"text": {"type": "plain_text", "text": "Bank Transfer"}, "value": "Bank Transfer"},
                    ]
                }
            },
            {
                "type": "input", "block_id": "remarks",
                "label": {"type": "plain_text", "text": "Remarks"},
                "optional": True,
                "element": {"type": "plain_text_input", "action_id": "value", "multiline": True,
                            "placeholder": {"type": "plain_text", "text": "Optional notes..."}}
            },
        ]
    }
    requests.post("https://slack.com/api/views.open",
                  headers=HEADERS,
                  json={"trigger_id": trigger_id, "view": modal})

# ── Thread updaters ───────────────────────────────────────────────────────────

def v(state, block_id):
    try:
        val = state["values"][block_id]["value"]
        if isinstance(val, dict):
            return val.get("selected_option", {}).get("value") or val.get("selected_date", "")
        return val or "—"
    except:
        return "—"

def update_thread(channel, ts, blocks, text):
    requests.post("https://slack.com/api/chat.update",
                  headers=HEADERS,
                  json={"channel": channel, "ts": ts, "text": text, "blocks": blocks})

def post_reply(channel, ts, text):
    requests.post("https://slack.com/api/chat.postMessage",
                  headers=HEADERS,
                  json={"channel": channel, "thread_ts": ts, "text": text,
                        "username": "MKV Fleet Status", "icon_emoji": ":car:"})

def handle_delivery_submit(payload):
    meta    = json.loads(payload["view"]["private_metadata"])
    channel = meta["channel"]
    ts      = meta["ts"]
    booking = meta["booking"]
    state   = payload["view"]["state"]

    driver  = v(state, "driver_name")
    out_km  = v(state, "out_km")
    fuel    = v(state, "fuel_level")
    photos  = v(state, "photos_uploaded")
    remarks = v(state, "remarks")

    post_reply(channel, ts,
        f"*DELIVERY COMPLETED*\n"
        f"Driver: {driver} | Out KM: {out_km} | Fuel: {fuel} | Photos: {photos}\n"
        f"Remarks: {remarks}\n"
        f"*Pickup: PENDING*"
    )

def handle_pickup_submit(payload):
    meta    = json.loads(payload["view"]["private_metadata"])
    channel = meta["channel"]
    ts      = meta["ts"]
    state   = payload["view"]["state"]

    in_km   = v(state, "in_km")
    extra   = v(state, "extra_km")
    salik   = v(state, "salik")
    fines   = v(state, "fines")
    fuel_c  = v(state, "fuel_charge")
    damage  = v(state, "damage_charges")
    amount  = v(state, "amount_collected")
    payment = v(state, "payment_mode")
    remarks = v(state, "remarks")

    post_reply(channel, ts,
        f"*CONTRACT CLOSED — NO FURTHER ACTION REQUIRED*\n"
        f"In KM: {in_km} | Extra KM: {extra} | Salik: {salik} | Fines: {fines}\n"
        f"Fuel Charge: {fuel_c} | Damage: {damage}\n"
        f"Amount Collected: {amount} | Payment: {payment}\n"
        f"Remarks: {remarks}"
    )

def handle_extension_submit(payload):
    meta    = json.loads(payload["view"]["private_metadata"])
    channel = meta["channel"]
    ts      = meta["ts"]
    state   = payload["view"]["state"]

    new_date  = v(state, "new_return_date")
    in_km     = v(state, "in_km")
    salik     = v(state, "salik")
    fines     = v(state, "fines")
    fuel_c    = v(state, "fuel_charge")
    damage    = v(state, "damage_charges")
    ext_days  = v(state, "extension_days")
    ext_amt   = v(state, "extension_amount")
    ext_coll  = v(state, "extension_amount_collected")
    ext_pay   = v(state, "extension_payment_mode")
    remarks   = v(state, "remarks")

    post_reply(channel, ts,
        f"*CONTRACT ACTIVE — EXTENDED*\n"
        f"New Return Date: {new_date} | Extension Days: {ext_days}\n"
        f"In KM: {in_km} | Salik: {salik} | Fines: {fines}\n"
        f"Fuel Charge: {fuel_c} | Damage: {damage}\n"
        f"Extension Amount: {ext_amt} | Collected: {ext_coll} | Payment: {ext_pay}\n"
        f"Remarks: {remarks}\n"
        f"*Final Pickup: PENDING*"
    )

# ── HTTP Handler ──────────────────────────────────────────────────────────────

class SlackHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"[{self.address_string()}] {format % args}")

    def respond(self, code=200, body=b""):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length  = int(self.headers.get("Content-Length", 0))
        body    = self.rfile.read(length)
        ts      = self.headers.get("X-Slack-Request-Timestamp", "0")
        sig     = self.headers.get("X-Slack-Signature", "")

        if not verify_slack_signature(body, ts, sig):
            self.respond(401, b'{"error":"invalid signature"}')
            return

        content_type = self.headers.get("Content-Type", "")

        if self.path == "/slack/actions":
            raw     = parse_qs(body.decode())
            payload = json.loads(unquote_plus(raw.get("payload", ["{}"])[0]))
            p_type  = payload.get("type")

            if p_type == "block_actions":
                action_id = payload["actions"][0]["action_id"]
                trigger   = payload["trigger_id"]
                channel   = payload["container"]["channel_id"]
                msg_ts    = payload["container"]["message_ts"]

                bk = payload["actions"][0].get("value", "{}")
                try:
                    booking = json.loads(bk)
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

        elif self.path == "/health":
            self.respond(200, b'{"status":"ok"}')
        else:
            self.respond(404, b'{"error":"not found"}')

    def do_GET(self):
        if self.path == "/health":
            self.respond(200, b'{"status":"ok","service":"MKV Slack App"}')
        else:
            self.respond(404)

# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"MKV Slack App running on port {PORT}")
    HTTPServer(("0.0.0.0", PORT), SlackHandler).serve_forever()
