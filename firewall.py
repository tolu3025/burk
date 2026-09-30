"""Burk v2 firewall — two-pass: cheap regex first, then policy check.
Phase 4 upgrade path: replace ask_sentinel() with an LLM verdict call.
"""
import re

FINANCIAL_KEYWORDS = re.compile(
    r"(pay|payment|transfer|send money|buy|purchase|checkout|otp|pin|cvv|card|"
    r"account number|bank|deposit|withdraw|subscription|crypto|btc|usdt)",
    re.IGNORECASE,
)
SHORTCODE = re.compile(r"^\d{4,6}$")

# tools that pause for human approval before executing
RISKY_TOOLS = {"sms_send", "call"}


def check_sms(number: str, text: str):
    if SHORTCODE.match(number.strip()):
        return False, f"BLOCKED: '{number}' is a shortcode (bank/operator)."
    if FINANCIAL_KEYWORDS.search(text):
        return False, "BLOCKED: message contains financial content."
    return True, "ok"


def check_request(user_text: str):
    if FINANCIAL_KEYWORDS.search(user_text):
        return False, ("I can't do anything involving money or payments. "
                       "That's yours to handle, human.")
    return True, "ok"


def is_risky(tool_name: str, args: dict) -> bool:
    if tool_name in RISKY_TOOLS:
        return True
    if tool_name == "sms_send":
        ok, _ = check_sms(args.get("number", ""), args.get("text", ""))
        return not ok
    return False
