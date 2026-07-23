"""
WhatsApp API test script.
Usage: python test_whatsapp.py
Make sure your local WhatsApp API server is running on localhost:3000.
"""
import requests
import sys

API_URL = "http://localhost:3000/send-message"

# ── Change these before running ───────────────────────────────────────────────
PHONE   = "923441357416"   # full international format, no + or spaces
MESSAGE = (
    "🚀 Hello! This is a test message from PIE Real Estate CRM.\n\n"
    "If you received this, the WhatsApp API is working correctly. ✅"
)
# ─────────────────────────────────────────────────────────────────────────────

def test_send():
    print(f"Sending to: {PHONE}")
    print(f"API URL:    {API_URL}")
    print(f"Message:\n{MESSAGE}\n")
    print("-" * 50)

    try:
        response = requests.post(
            API_URL,
            json={"phone": PHONE, "message": MESSAGE},
            timeout=15,
        )
        print(f"Status Code : {response.status_code}")
        print(f"Response    : {response.text}")

        if response.ok:
            print("\n✅ Message sent successfully!")
        else:
            print("\n❌ API returned an error. Check the response above.")

    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to the API server.")
        print("   Make sure it is running:  node server.js  (or equivalent)")
        sys.exit(1)
    except requests.exceptions.Timeout:
        print("❌ Request timed out after 15 seconds.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    test_send()
