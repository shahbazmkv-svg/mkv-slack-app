"""
MKV Luxury — Slack Interactive App (Flask)
"""
import os, json, hashlib, hmac, time
from flask import Flask, request, jsonify
from urllib.parse import parse_qs, unquote_plus
import requests as req_lib

app = Flask(__name__)

SLACK_BOT_TOKEN      = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET", "")

# Railway injects PORT automatically — must use it exactly
PORT = int(os.environ.get("PORT", 8080))

HEADERS = {
    "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
    "Content-Type":  "application/json; charset=utf-8",
}

FUEL_OPTIONS = [
    {"text": {"type": "plain_text", "text": "4/4 — Full"},  "value": "4/4"},
    {"text": {"type": "plain_text", "text": "3/4"},          "value": "3/4"},
    {"text": {"type": "plain_text", "text": "2/4 — Half"},   "value": "2/4"},
    {"text": {"type": "plain_text", "text": "1/4"},          "value": "1/4"},
    {"text": {"type": "plain_text", "text": "0/4 — Empty"},  "value": "0/4"},
]

def verify_signature(body, timestamp, signature):
    if not SLACK_SIGNING_SECRET:
        return True
    try:
        if abs(time.time() - int(timestamp)) > 300:
            return False
        base = f"v0:{timestamp}:{body.decode('utf-8')}"
        computed = "v0=" + hmac.new(
            SLACK_SIGNING_SECRET.encode(),
            base.encode(),
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(computed, signature)
    except Exception as e:
        print(f"Sig error: {e}")
        return False

def slack_call(endpoint, payload):
    r = req_lib.post(
        f"https://slack.com/api/{endpoint}",
        headers=HEADERS, json=payload, timeout=15
    )
    res = r.json()
    if not res.get("ok"):
        print(f"Slack error [{endpoint}]: {res.get('error')}")
    return res

def open_modal(trigger_id, modal):
    slack_call("views.open", {"trigger_id": trigger_id, "view": modal})

def post_thread(channel, blocks, text, ts):
    slack_call("chat.postMessage", {
        "channel": channel, "text": text,
        "blocks": blocks, "thread_ts": ts
    })

def val(state, block_id):
    try:
        v = state["values"][block_id]["value"]
        if isinstance(v, dict):
            return (v.get("selected_option") or {}).get("value") or v.get("selected_date","") or "—"
        return v or "—"
    except:
        return "—"

def delivery_modal(booking, trigger_id, channel, ts):
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
                         "placeholder": {"type": "plain_text", "text": "Optional"}}},
        ]
    })

def pickup_modal(booking, trigger_id, channel, ts):
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
                         "placeholder": {"type": "plain_text", "text": "Select"},
                         "options": [
                             {"text": {"type": "plain_text", "text": "Cash"},          "value": "Cash"},
                             {"text": {"type": "plain_text", "text": "Card"},          "value": "Card"},
                             {"text": {"type": "plain_text", "text": "Bank Transfer"}, "value": "Bank Transfer"},
                         ]}},
            {"type": "input", "block_id": "remarks", "optional": True,
             "label": {"type": "plain_text", "text": "Remarks"},
             "element": {"type": "plain_text_input", "action_id": "value",
                         "multiline": True,
                         "placeholder": {"type": "plain_text", "text": "Optional"}}},
        ]
    })

def extension_modal(booking, trigger_id, channel, ts):
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
                         "placeholder": {"type": "plain_text", "text": "Select date"}}},
            {"type": "input", "block_id": "extension_days",
             "label": {"type": "plain_text", "text": "Extension Days"},
             "element": {"type": "plain_text_input", "action_id": "value",
                         "placeholder": {"type": "plain_text", "text": "e.g. 3"}}},
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
                         "placeholder": {"type": "plain_text", "text": "Select"},
                         "options": [
                             {"text": {"type": "plain_text", "text": "Cash"},          "value": "Cash"},
                             {"text": {"type": "plain_text", "text": "Card"},          "value": "Card"},
                             {"text": {"type": "plain_text", "text": "Bank Transfer"}, "value": "Bank Transfer"},
                         ]}},
            {"type": "input", "block_id": "remarks", "optional": True,
             "label": {"type": "plain_text", "text": "Remarks"},
             "element": {"type": "plain_text_input", "action_id": "value",
                         "multiline": True,
                         "placeholder": {"type": "plain_text", "text": "Optional"}}},
        ]
    })

def handle_delivery(payload):
    meta    = json.loads(payload["view"]["private_metadata"])
    state   = payload["view"]["state"]
    user    = payload["user"]["name"]
    booking = meta["booking"]
    driver  = val(state, "driver_name")
    out_km  = val(state, "out_km")
    booking.update({"driver": driver, "out_km": out_km})

    post_thread(meta["channel"], [
        {"type": "section", "text": {"type": "mrkdwn", "text": (
            f"✅ *DELIVERY COMPLETED*\n```\n"
            f"{'Driver':<14}: {driver}\n"
            f"{'Out KM':<14}: {out_km}\n"
            f"{'Fuel Level':<14}: {val(state,'fuel_level')}\n"
            f"{'Photos':<14}: {val(state,'photos_uploaded')}\n"
            f"{'Remarks':<14}: {val(state,'remarks')}\n```"
        )}},
        {"type": "divider"},
        {"type": "actions", "elements": [
            {"type": "button", "text": {"type": "plain_text", "text": "🔑  Pickup"},
             "style": "primary", "action_id": "open_pickup", "value": json.dumps(booking)},
            {"type": "button", "text": {"type": "plain_text", "text": "📋  Extension"},
             "action_id": "open_extension", "value": json.dumps(booking)},
        ]},
        {"type": "context", "elements": [{"type": "mrkdwn",
            "text": f"Submitted by @{user} | Pickup: PENDING"}]},
    ], f"✅ Delivery completed by {user}", meta["ts"])

def handle_pickup(payload):
    meta  = json.loads(payload["view"]["private_metadata"])
    state = payload["view"]["state"]
    user  = payload["user"]["name"]
    post_thread(meta["channel"], [
        {"type": "section", "text": {"type": "mrkdwn", "text": (
            f"✅ *CONTRACT CLOSED*\n```\n"
            f"{'In KM':<16}: {val(state,'in_km')}\n"
            f"{'Extra KM':<16}: {val(state,'extra_km')}\n"
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
    ], f"✅ Contract closed by {user}", meta["ts"])

def handle_extension(payload):
    meta    = json.loads(payload["view"]["private_metadata"])
    state   = payload["view"]["state"]
    user    = payload["user"]["name"]
    booking = meta["booking"]
    post_thread(meta["channel"], [
        {"type": "section", "text": {"type": "mrkdwn", "text": (
            f"📋 *CONTRACT EXTENDED*\n```\n"
            f"{'New Return Date':<20}: {val(state,'new_return_date')}\n"
            f"{'Extension Days':<20}: {val(state,'extension_days')}\n"
            f"{'In KM':<20}: {val(state,'in_km')}\n"
            f"{'Salik':<20}: {val(state,'salik')}\n"
            f"{'Fines':<20}: {val(state,'fines')}\n"
            f"{'Fuel Charge':<20}: {val(state,'fuel_charge')}\n"
            f"{'Damage':<20}: {val(state,'damage_charges')}\n"
            f"{'Ext Amount':<20}: {val(state,'extension_amount')}\n"
            f"{'Ext Collected':<20}: {val(state,'extension_amount_collected')}\n"
            f"{'Payment Mode':<20}: {val(state,'extension_payment_mode')}\n"
            f"{'Remarks':<20}: {val(state,'remarks')}\n```\n"
            f"*CONTRACT ACTIVE — EXTENDED | Final Pickup: PENDING*"
        )}},
        {"type": "divider"},
        {"type": "actions", "elements": [
            {"type": "button", "text": {"type": "plain_text", "text": "🔑  Pickup"},
             "style": "primary", "action_id": "open_pickup", "value": json.dumps(booking)},
        ]},
        {"type": "context", "elements": [{"type": "mrkdwn",
            "text": f"Submitted by @{user}"}]},
    ], f"📋 Contract extended by {user}", meta["ts"])

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
@app.route("/health", methods=["GET"])
def health():
    print("Health check OK")
    return jsonify({"status": "ok", "service": "MKV Slack App"})

@app.route("/slack/actions", methods=["POST"])
def slack_actions():
    body      = request.get_data()
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "0")
    signature = request.headers.get("X-Slack-Signature", "")

    print(f"Incoming POST /slack/actions — {len(body)} bytes")

    # Handle URL verification challenge
    try:
        jb = json.loads(body.decode())
        if jb.get("type") == "url_verification":
            print("URL verification — responding with challenge")
            return jsonify({"challenge": jb.get("challenge", "")})
    except:
        pass

    if not verify_signature(body, timestamp, signature):
        print("Signature FAILED")
        return jsonify({"error": "invalid_signature"}), 401

    raw     = parse_qs(body.decode())
    payload = json.loads(unquote_plus(raw.get("payload", ["{}"])[0]))
    p_type  = payload.get("type")
    print(f"Type: {p_type}")

    if p_type == "block_actions":
        action_id = payload["actions"][0]["action_id"]
        trigger   = payload["trigger_id"]
        channel   = payload["container"]["channel_id"]
        msg_ts    = payload["container"]["message_ts"]
        try:
            booking = json.loads(payload["actions"][0].get("value", "{}"))
        except:
            booking = {}
        print(f"Action: {action_id}")
        if action_id == "open_delivery":
            delivery_modal(booking, trigger, channel, msg_ts)
        elif action_id == "open_pickup":
            pickup_modal(booking, trigger, channel, msg_ts)
        elif action_id == "open_extension":
            extension_modal(booking, trigger, channel, msg_ts)
        return "", 200

    elif p_type == "view_submission":
        cb = payload["view"]["callback_id"]
        print(f"Submission: {cb}")
        if cb == "delivery_submit":
            handle_delivery(payload)
        elif cb == "pickup_submit":
            handle_pickup(payload)
        elif cb == "extension_submit":
            handle_extension(payload)
        return jsonify({"response_action": "clear"})

    return "", 200

if __name__ == "__main__":
    print(f"Starting MKV Slack App on port {PORT}")
    app.run(host="0.0.0.0", port=PORT)
