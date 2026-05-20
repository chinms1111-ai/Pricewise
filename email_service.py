import os
import urllib.request
import urllib.parse
import json
from dotenv import load_dotenv

load_dotenv()

SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")
SENDER_EMAIL = os.environ.get("GMAIL_USER", "noreply@pricewise.com")


def send_deal_confirmation(seller_email, seller_name, buyer_session_id, deal_details, seller_id=None):
    if not seller_email:
        print("[EMAIL] No seller email — skipping")
        return False

    if not SENDGRID_API_KEY:
        print("[EMAIL] No SendGrid API key set")
        return False

    try:
        buyer_id = buyer_session_id[:12] + "..." if buyer_session_id else "Unknown"
        base_url = os.environ.get("APP_URL", "https://pricewise-2qrj.onrender.com")
        profile_url = f"{base_url}/seller/profile/{seller_id}" if seller_id else base_url
        commodity = deal_details.get("commodity", "Not specified")
        price = deal_details.get("price", "Not specified")
        quantity = deal_details.get("quantity", "Not specified")
        summary = deal_details.get("summary", "Your clone closed a deal on your behalf.")

        html = f"""
        <html><body style="font-family:Arial,sans-serif;background:#f5f5f5;padding:20px;">
        <div style="max-width:600px;margin:0 auto;background:white;border-radius:12px;overflow:hidden;">
            <div style="background:#0a0800;padding:24px;text-align:center;">
                <h1 style="color:#f0a500;font-size:28px;margin:0;letter-spacing:4px;">PRICEWISE</h1>
                <p style="color:#7a8499;font-size:12px;margin:6px 0 0;">MARKET INTELLIGENCE TERMINAL</p>
            </div>
            <div style="background:#f0a500;padding:16px;text-align:center;">
                <h2 style="color:#0a0800;margin:0;">🤝 DEAL CLOSED BY YOUR CLONE</h2>
            </div>
            <div style="padding:28px;">
                <p>Hi <strong>{seller_name}</strong>,<br><br>Your clone just closed a deal on your behalf:</p>
                <div style="background:#f9f9f9;border-left:4px solid #f0a500;padding:20px;margin:20px 0;">
                    <p><strong>Commodity:</strong> {commodity}</p>
                    <p><strong>Price:</strong> <span style="color:#f0a500;font-size:16px;">{price}</span></p>
                    <p><strong>Quantity:</strong> {quantity}</p>
                    <p><strong>Buyer:</strong> Anonymous ({buyer_id})</p>
                </div>
                <div style="background:#fff8e6;border:1px solid #f0a500;border-radius:6px;padding:16px;">
                    <p style="margin:0;"><strong>Clone Summary:</strong> {summary}</p>
                </div>
                <div style="text-align:center;margin:24px 0;">
                    <a href="{profile_url}" style="background:#f0a500;color:#0a0800;padding:12px 28px;
                    border-radius:6px;text-decoration:none;font-weight:bold;">VIEW CONVERSATION →</a>
                </div>
            </div>
            <div style="background:#f5f5f5;padding:16px;text-align:center;">
                <p style="color:#aaa;font-size:12px;margin:0;">PriceWise · Nigeria Commodity Intelligence Terminal</p>
            </div>
        </div>
        </body></html>
        """

        payload = json.dumps({
            "personalizations": [{"to": [{"email": seller_email}]}],
            "from": {"email": SENDER_EMAIL, "name": "PriceWise"},
            "subject": f"🤝 Deal Closed — {commodity} | PriceWise",
            "content": [{"type": "text/html", "value": html}]
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.sendgrid.com/v3/mail/send",
            data=payload,
            headers={
                "Authorization": f"Bearer {SENDGRID_API_KEY}",
                "Content-Type": "application/json"
            },
            method="POST"
        )

        with urllib.request.urlopen(req) as resp:
            print(f"[EMAIL] Sent via SendGrid — status {resp.status}")
            return True

    except Exception as e:
        print(f"[EMAIL] Failed to send: {e}")
        return False