"""Wi-Fi controller for the ESP32 traffic-light prototype.

Fixes applied:
- Dynamic BASE_URL: changes to ESP32_IP take effect immediately via get_base_url().
- Sanitized IP setter: strips whitespace, protocol prefixes, and trailing slashes.
- Shorter default timeout (2.5 s) to prevent GUI thread freezes.
- check_connection() for fast reachability tests (timeout=2 s).
- set_esp32_ip() / get_esp32_ip() so the GUI can update the IP at runtime.
"""
import json
import time
import urllib.parse
import urllib.request

# Default IP — override at runtime with set_esp32_ip() or via the GUI toolbar.
_ESP32_IP: str = "192.168.137.3"


def set_esp32_ip(ip: str) -> None:
    """Update the ESP32 IP address at runtime (strips protocol / slashes)."""
    global _ESP32_IP
    ip = ip.strip()
    for prefix in ("http://", "https://"):
        if ip.lower().startswith(prefix):
            ip = ip[len(prefix):]
    _ESP32_IP = ip.rstrip("/")


def get_esp32_ip() -> str:
    return _ESP32_IP


def get_base_url() -> str:
    """Always builds the URL from the current IP so runtime changes take effect."""
    return f"http://{_ESP32_IP}"


def _get(path: str, params: dict | None = None, timeout: float = 2.5) -> str:
    url = get_base_url() + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read().decode("utf-8")


# ── Public API ────────────────────────────────────────────────────────────────

def check_connection(timeout: float = 2.0) -> bool:
    """Return True if the ESP32 root page responds within *timeout* seconds."""
    try:
        _get("/", timeout=timeout)
        return True
    except Exception:
        return False


def send_yellow(direction: str) -> bool:
    """Tell the ESP32 to light the YELLOW LED for the given direction.

    The Python app (app.py) manages the 3-second yellow duration via QTimer;
    the ESP32 simply holds the yellow LED on until /set or /stop arrives.
    Failure is non-blocking — GUI yellow phase continues regardless.
    """
    direction = str(direction).upper()
    try:
        data = _get("/yellow", {"direction": direction})
        print("ESP32 yellow ->", data)
        return True
    except Exception as e:
        print("ESP32 yellow error:", e)
        return False


def send_signal(direction: str, seconds: int) -> bool:
    direction = str(direction).upper()
    seconds = int(seconds)
    try:
        data = _get("/set", {"direction": direction, "seconds": seconds})
        print("ESP32 ->", data)
        return True
    except Exception as e:
        print("ESP32 connection error:", e)
        return False


def stop_signal() -> bool:
    try:
        print("ESP32 ->", _get("/stop"))
        return True
    except Exception as e:
        print("ESP32 connection error:", e)
        return False


def get_status() -> dict | None:
    try:
        return json.loads(_get("/status"))
    except Exception as e:
        print("ESP32 status error:", e)
        return None


def run_sequence(sequence: list) -> bool:
    for direction, seconds in sequence:
        if not send_signal(direction, seconds):
            return False
        time.sleep(int(seconds))
    stop_signal()
    return True
