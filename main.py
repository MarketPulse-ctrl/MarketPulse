"""
Market Pulse Newsletter - Daily AI-powered market digest
Run daily via cron: 0 7 * * 1-5 python main.py
"""

import os
import json
import requests
from datetime import datetime, date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from jinja2 import Template
import anthropic

# ─── CONFIG ──────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY   = os.getenv("ANTHROPIC_API_KEY")
FINNHUB_API_KEY     = os.getenv("FINNHUB_API_KEY")       # free at finnhub.io
KIT_API_KEY         = os.getenv("KIT_API_KEY")            # Kit (ConvertKit) API key
KIT_EMAIL_ADDRESS   = os.getenv("KIT_EMAIL_ADDRESS")      # Your verified sender email in Kit
NEWSLETTER_NAME     = "Market Pulse"
WATCHLIST           = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "TSLA", "BTC-USD"]

# ─── 1. FETCH MARKET DATA ─────────────────────────────────────────────────────
def get_market_snapshot():
    """Pull price data for watchlist tickers via Finnhub."""
    results = []
    for symbol in WATCHLIST:
        try:
            url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_API_KEY}"
            r = requests.get(url, timeout=10).json()
            change_pct = round(((r["c"] - r["pc"]) / r["pc"]) * 100, 2) if r.get("pc") else 0
            results.append({
                "symbol": symbol,
                "price":  round(r.get("c", 0), 2),
                "change": change_pct,
                "arrow":  "▲" if change_pct >= 0 else "▼",
                "color":  "#22c55e" if change_pct >= 0 else "#ef4444",
            })
        except Exception as e:
            print(f"[WARN] Could not fetch {symbol}: {e}")
    return results


def get_market_news():
    """Fetch today's top financial news headlines via Finnhub."""
    url = f"https://finnhub.io/api/v1/news?category=general&token={FINNHUB_API_KEY}"
    try:
        items = requests.get(url, timeout=10).json()
        # Return top 10 headlines + summaries
        return [
            {"headline": i["headline"], "summary": i.get("summary", ""), "source": i.get("source", "")}
            for i in items[:10]
        ]
    except Exception as e:
        print(f"[WARN] News fetch failed: {e}")
        return []


# ─── 2. AI SUMMARIZATION ──────────────────────────────────────────────────────
def generate_digest(market_data, news_items):
    """Ask Claude to write today's digest from raw data."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    market_text = "\n".join(
        f"{d['symbol']}: ${d['price']} ({'+' if d['change']>=0 else ''}{d['change']}%)"
        for d in market_data
    )
    news_text = "\n".join(
        f"- {n['headline']} ({n['source']}): {n['summary']}"
        for n in news_items
    )
    today = date.today().strftime("%A, %B %d, %Y")

    prompt = f"""You are a sharp, trusted financial journalist writing a daily market digest for retail investors.
Today is {today}.

MARKET DATA:
{market_text}

TODAY'S TOP NEWS:
{news_text}

Write a concise, insightful daily market digest with these EXACT sections:
1. **THE BIG PICTURE** (2–3 sentences): The single most important market story today. Be direct.
2. **WHAT'S MOVING** (3–4 bullet points): Key movers and why. Include the ticker in brackets e.g. [NVDA].
3. **UNDER THE RADAR** (1–2 sentences): One overlooked story or data point worth watching.
4. **TOMORROW'S WATCHLIST** (2–3 bullet points): What to watch for next session. Be specific.

Tone: confident, clear, no fluff. Write for someone who knows markets but is busy.
Return ONLY the newsletter body text. No preamble. Use markdown formatting."""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=900,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text


# ─── 3. EMAIL TEMPLATE ────────────────────────────────────────────────────────
EMAIL_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ newsletter_name }} — {{ date }}</title>
</head>
<body style="margin:0;padding:0;background:#0f0f0f;font-family:'Georgia',serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0f0f0f;padding:32px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">

        <!-- Header -->
        <tr><td style="background:#111;border:1px solid #222;border-radius:12px 12px 0 0;padding:32px 40px 24px;">
          <div style="font-family:'Georgia',serif;font-size:28px;font-weight:700;color:#f5f0e8;letter-spacing:-0.5px;">
            {{ newsletter_name }}
          </div>
          <div style="color:#666;font-size:13px;margin-top:4px;font-family:monospace;">
            {{ date }} &nbsp;·&nbsp; Daily Market Digest
          </div>
        </td></tr>

        <!-- Ticker bar -->
        <tr><td style="background:#161616;border-left:1px solid #222;border-right:1px solid #222;padding:16px 40px;">
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
            {% for t in tickers %}
              <td style="text-align:center;padding:0 8px;">
                <div style="font-family:monospace;font-size:11px;color:#888;">{{ t.symbol }}</div>
                <div style="font-family:monospace;font-size:13px;color:#f5f0e8;font-weight:600;">${{ t.price }}</div>
                <div style="font-family:monospace;font-size:11px;color:{{ t.color }};">{{ t.arrow }} {{ t.change }}%</div>
              </td>
            {% endfor %}
            </tr>
          </table>
        </td></tr>

        <!-- Body -->
        <tr><td style="background:#111;border:1px solid #222;border-top:0;padding:32px 40px;">
          <div style="color:#d4cfc6;font-size:15px;line-height:1.8;">
            {{ body_html | safe }}
          </div>
        </td></tr>

        <!-- Footer -->
        <tr><td style="background:#0d0d0d;border:1px solid #222;border-top:0;border-radius:0 0 12px 12px;padding:20px 40px;">
          <div style="color:#444;font-size:12px;font-family:monospace;">
            You're receiving this because you subscribed to {{ newsletter_name }}.<br>
            <a href="{{ unsubscribe_url }}" style="color:#666;text-decoration:underline;">Unsubscribe</a>
            &nbsp;·&nbsp; This is not financial advice.
          </div>
        </td></tr>

      </table>
    </td></tr>
  </table>
</body>
</html>
"""

def markdown_to_simple_html(text):
    """Minimal markdown → HTML converter (no dependencies)."""
    import re
    lines = text.split("\n")
    html_lines = []
    for line in lines:
        line = re.sub(r'\*\*(.*?)\*\*', r'<strong style="color:#f5f0e8;">\1</strong>', line)
        if line.startswith("## ") or line.startswith("**") and line.endswith("**"):
            line = f'<h3 style="color:#d4a847;font-size:13px;letter-spacing:1px;text-transform:uppercase;margin:24px 0 8px;font-family:monospace;">{line.lstrip("#").strip()}</h3>'
        elif line.startswith("- ") or line.startswith("• "):
            line = f'<div style="padding:4px 0 4px 16px;border-left:2px solid #333;margin:6px 0;">· {line[2:]}</div>'
        elif line.strip():
            line = f'<p style="margin:0 0 12px;">{line}</p>'
        html_lines.append(line)
    return "\n".join(html_lines)


def build_email(digest_text, market_data):
    tpl = Template(EMAIL_HTML)
    return tpl.render(
        newsletter_name=NEWSLETTER_NAME,
        date=date.today().strftime("%B %d, %Y"),
        tickers=market_data[:7],
        body_html=markdown_to_simple_html(digest_text),
        unsubscribe_url="https://yoursite.com/unsubscribe",
    )



# ─── 5. SEND VIA KIT BROADCAST ───────────────────────────────────────────────
def send_kit_broadcast(subject, html_content):
    """
    Creates and sends a Broadcast via Kit (ConvertKit) API v4.
    Kit skickar emailet till ALLA dina aktiva prenumeranter automatiskt.
    Du behöver inte hantera en subscribers.json längre.
    """
    headers = {
        "Authorization": f"Bearer {KIT_API_KEY}",
        "Content-Type":  "application/json",
    }

    # Steg 1: Skapa broadcast (sparas som utkast)
    create_payload = {
        "broadcast": {
            "subject":        subject,
            "content":        html_content,
            "email_address":  KIT_EMAIL_ADDRESS,
            "email_layout_template": "none",   # Använd vår egen HTML, inte Kit:s mallar
        }
    }
    r = requests.post(
        "https://api.kit.com/v4/broadcasts",
        json=create_payload,
        headers=headers,
        timeout=15,
    )
    if r.status_code not in (200, 201):
        print(f"❌ Kit: Kunde inte skapa broadcast: {r.status_code} — {r.text}")
        return False

    broadcast_id = r.json()["broadcast"]["id"]
    print(f"   ✓ Broadcast skapad (ID: {broadcast_id})")

    # Steg 2: Publicera/skicka broadcasten direkt
    send_url = f"https://api.kit.com/v4/broadcasts/{broadcast_id}/send"
    r2 = requests.post(send_url, headers=headers, timeout=15)

    if r2.status_code in (200, 201, 204):
        print(f"   ✓ Broadcast skickad till alla prenumeranter!")
        return True
    else:
        print(f"❌ Kit: Kunde inte skicka broadcast: {r2.status_code} — {r2.text}")
        return False


# ─── 6. MAIN PIPELINE ─────────────────────────────────────────────────────────
def run():
    today = date.today().strftime("%B %d, %Y")
    subject = f"{NEWSLETTER_NAME} | {today} — Daily Market Digest"

    print("📊 Hämtar marknadsdata...")
    market_data = get_market_snapshot()

    print("📰 Hämtar nyheter...")
    news = get_market_news()

    print("🤖 Genererar AI-digest...")
    digest = generate_digest(market_data, news)
    print("\n--- FÖRHANDSVISNING ---")
    print(digest[:300] + "...")

    print("\n📧 Bygger email...")
    html = build_email(digest, market_data)

    print("\n📬 Skickar via Kit...")
    success = send_kit_broadcast(subject, html)

    if success:
        print("\n✅ Klart! Emailet är på väg till alla prenumeranter.")
    else:
        print("\n❌ Något gick fel. Kontrollera dina Kit API-uppgifter.")


if __name__ == "__main__":
    run()
