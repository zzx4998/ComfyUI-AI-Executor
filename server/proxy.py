import json
import os
import time

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PLUGIN_DIR, "config.json")

_cache = {"proxy": None, "ts": 0}


def _from_plugin_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f).get("proxy")
        except Exception:
            pass
    return None


def _find_key(obj, key, depth=0):
    if depth > 4 or not isinstance(obj, dict):
        return None
    for k, v in obj.items():
        if k == key and isinstance(v, str) and v.strip():
            return v.strip()
        found = _find_key(v, key, depth + 1)
        if found:
            return found
    return None


def _from_launcher():
    d = PLUGIN_DIR
    for _ in range(6):
        pref = os.path.join(d, ".launcher", "preference.json")
        if os.path.exists(pref):
            try:
                with open(pref, "r", encoding="utf-8") as f:
                    return _find_key(json.load(f), "proxy_address")
            except Exception:
                return None
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return None


def _from_env():
    return (os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
            or os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy"))


def get_proxy():
    if time.time() - _cache["ts"] < 60:
        return _cache["proxy"]
    proxy = _from_plugin_config() or _from_launcher() or _from_env()
    if proxy and not proxy.startswith("http"):
        proxy = "http://" + proxy
    _cache.update(proxy=proxy or None, ts=time.time())
    return _cache["proxy"]
