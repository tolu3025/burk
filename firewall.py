import re

FINANCIAL_KEYWORDS = re.compile(
    r"(pay|payment|transfer|send money|buy|purchase|checkout|otp|pin|cvv|card|"
    r"account number|bank|deposit|withdraw|subscription|crypto|btc|usdt)",
    re.IGNORECASE,
)
SHORTCODE = re.compile(r"^\d{4,6}$")  # bank/operator shortcodes

def check_sms(number: str, text: str):
    """Returns (ok, reason). Blocks anything financial."""
    if SHORTCODE.match(number.strip()):
        return False, f"BLOCKED: '{number}' is a shortcode (bank/operator)."
    if FINANCIAL_KEYWORDS.search(text):
        return False, "BLOCKED: message contains financial content."
    return True, "ok"

def check_request(user_text: str):
    """Blocks chat requests with financial intent."""
    if FINANCIAL_KEYWORDS.search(user_text):
        return False, ("I can't do anything involving money or payments. "
                       "That's yours to handle, human.")
    return True, "ok"
