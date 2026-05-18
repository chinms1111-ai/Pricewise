"""
email_service.py — PriceWise Email Service
==========================================
Sends deal confirmation emails via Gmail SMTP.
"""

import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")


def send_deal_confirmation(seller_email, seller_name, buyer_session_id, deal_details):
    """
    Send deal confirmation email to seller after clone closes a deal.
    
    deal_details: dict with commodity, price, quantity, buyer_message
    """
    if not seller_email:
        print("[EMAIL] No seller email — skipping")
        return False

    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("[EMAIL] Gmail credentials not set")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🤝 Deal Closed — {deal_details.get('commodity', 'Commodity')} | PriceWise"
        msg["From"] = GMAIL_USER
        msg["To"] = seller_email

        buyer_id = buyer_session_id[:12] + "..." if buyer_session_id else "Unknown"
        commodity = deal_details.get("commodity", "Not specified")
        price = deal_details.get("price", "Not specified")
        quantity = deal_details.get("quantity", "Not specified")
        summary = deal_details.get("summary", "Your clone closed a deal on your behalf.")

        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; background:#f5f5f5; padding:20px;">
            <div style="max-width:600px; margin:0 auto; background:white; 
                border-radius:12px; overflow:hidden; box-shadow:0 2px 10px rgba(0,0,0,0.1);">
                
                <!-- Header -->
                <div style="background:#0a0800; padding:24px; text-align:center;">
                    <h1 style="color:#f0a500; font-size:28px; margin:0; letter-spacing:4px;">
                        PRICEWISE
                    </h1>
                    <p style="color:#7a8499; font-size:12px; margin:6px 0 0; letter-spacing:2px;">
                        MARKET INTELLIGENCE TERMINAL
                    </p>
                </div>

                <!-- Deal Badge -->
                <div style="background:#f0a500; padding:16px; text-align:center;">
                    <h2 style="color:#0a0800; margin:0; font-size:18px; letter-spacing:2px;">
                        🤝 DEAL CLOSED BY YOUR CLONE
                    </h2>
                </div>

                <!-- Body -->
                <div style="padding:28px;">
                    <p style="color:#333; font-size:15px; line-height:1.7;">
                        Hi <strong>{seller_name}</strong>,<br><br>
                        Your PriceWise clone just closed a deal on your behalf while you were away.
                        Here are the details:
                    </p>

                    <!-- Deal Details -->
                    <div style="background:#f9f9f9; border:1px solid #eee; 
                        border-left:4px solid #f0a500; border-radius:6px; 
                        padding:20px; margin:20px 0;">
                        <table style="width:100%; border-collapse:collapse;">
                            <tr>
                                <td style="padding:8px 0; color:#666; font-size:13px; 
                                    width:40%; font-weight:bold;">COMMODITY</td>
                                <td style="padding:8px 0; color:#333; font-size:14px;">
                                    {commodity}
                                </td>
                            </tr>
                            <tr style="border-top:1px solid #eee;">
                                <td style="padding:8px 0; color:#666; font-size:13px; 
                                    font-weight:bold;">AGREED PRICE</td>
                                <td style="padding:8px 0; color:#f0a500; font-size:16px; 
                                    font-weight:bold;">
                                    {price}
                                </td>
                            </tr>
                            <tr style="border-top:1px solid #eee;">
                                <td style="padding:8px 0; color:#666; font-size:13px; 
                                    font-weight:bold;">QUANTITY</td>
                                <td style="padding:8px 0; color:#333; font-size:14px;">
                                    {quantity}
                                </td>
                            </tr>
                            <tr style="border-top:1px solid #eee;">
                                <td style="padding:8px 0; color:#666; font-size:13px; 
                                    font-weight:bold;">BUYER</td>
                                <td style="padding:8px 0; color:#333; font-size:14px;">
                                    Anonymous Buyer ({buyer_id})
                                </td>
                            </tr>
                        </table>
                    </div>

                    <!-- Clone Summary -->
                    <div style="background:#fff8e6; border:1px solid #f0a500; 
                        border-radius:6px; padding:16px; margin:16px 0;">
                        <p style="color:#666; font-size:12px; margin:0 0 6px; 
                            letter-spacing:1px; font-weight:bold;">
                            🧬 CLONE SUMMARY
                        </p>
                        <p style="color:#333; font-size:14px; margin:0; line-height:1.6;">
                            {summary}
                        </p>
                    </div>

                    <p style="color:#666; font-size:13px; line-height:1.7;">
                        Please follow up with the buyer to confirm delivery details 
                        and payment. Log in to PriceWise to view the full conversation.
                    </p>

                    <div style="text-align:center; margin:24px 0;">
                        <a href="https://pricewise-2qrj.onrender.com/seller/profile/1" 
                            style="background:#f0a500; color:#0a0800; padding:12px 28px; 
                            border-radius:6px; text-decoration:none; font-weight:bold; 
                            font-size:14px; letter-spacing:1px;">
                            VIEW CONVERSATION →
                        </a>
                    </div>
                </div>

                <!-- Footer -->
                <div style="background:#f5f5f5; padding:16px; text-align:center; 
                    border-top:1px solid #eee;">
                    <p style="color:#aaa; font-size:12px; margin:0;">
                        PriceWise · Nigeria Commodity Intelligence Terminal<br>
                        This email was sent because your clone closed a deal on your behalf.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, seller_email, msg.as_string())

        print(f"[EMAIL] Deal confirmation sent to {seller_email}")
        return True

    except Exception as e:
        print(f"[EMAIL] Failed to send: {e}")
        return False