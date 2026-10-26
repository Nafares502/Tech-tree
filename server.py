#!/usr/bin/env python3
"""Local server for the production tree.
Run:  python server.py   (opens http://localhost:8000 by itself)
Serves index.html and machinery_blocks/, reads and writes the .json files in this folder.
No install needed: standard library of Python 3 only."""
import http.server, json, os, re, socketserver, threading, unicodedata, webbrowser

BASE = os.path.dirname(os.path.abspath(__file__))
ICON_DIR = "machinery_blocks"
IMG = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")
W_MIN, W_MAX, W_DEF = 160, 480, 200   # block width limits (px)
H_MIN, H_MAX, H_DEF = 64, 320, 80     # block height limits (px)

VERSION = 7
UI_DIR = "ui_models"                  # saved UI models live here
LINKS_FILE = "connections.json"       # block connections live here
LINK_LOCK = threading.Lock()
LAYOUT_FILE = "layout.json"           # block positions on the board
LAYOUT_LOCK = threading.Lock()
POS_MAX = 50000
SLOT = 36                             # item slot size (px)
TALL_W, TALL_H = 24, 104              # fluid and FE columns (px)
BTN_H, BTN_W_MIN, BTN_W_MAX, BTN_W_DEF = 24, 40, 160, 72
ARROW_W, ARROW_H = 44, 32             # progress arrow
FLAME_W, FLAME_H = 28, 32             # flame
UW_MIN, UW_MAX, UW_DEF = 120, 420, 240
UH_MIN, UH_MAX, UH_DEF = 40, 240, 120
MAX_PIECES = 32
SLOT_TYPES = ("item", "fluid", "energy")
PIECE_TYPES = SLOT_TYPES + ("button", "arrow", "flame")
MAX_ENTRIES = 6                       # inputs / outputs per side
TYPES = ("item", "fluid", "energy")   # legacy inputs/outputs lists
AMT_MAX = 99999999


def clamp(v, lo, hi, default):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return default
    return max(lo, min(hi, int(v)))


def icons():
    d = os.path.join(BASE, ICON_DIR)
    if not os.path.isdir(d):
        return []
    return sorted(f for f in os.listdir(d) if f.lower().endswith(IMG))


def clean_entries(lst):
    """Lenient: used when reading files (they may be edited by hand)."""
    out = []
    if not isinstance(lst, list):
        return out
    for e in lst[:MAX_ENTRIES]:
        if not isinstance(e, dict) or e.get("type") not in TYPES:
            continue
        name = e.get("name")
        name = name.strip()[:30] if isinstance(name, str) else ""
        if not name and e["type"] == "energy":
            name = "Energy"
        if not name:
            continue
        icon = e.get("icon")
        out.append({"type": e["type"], "name": name,
                    "amount": clamp(e.get("amount"), 1, AMT_MAX, 1),
                    "icon": icon if isinstance(icon, str) and icon else None})
    return out


def piece_size(kind, w=None):
    if kind == "item":
        return SLOT, SLOT
    if kind in ("fluid", "energy"):
        return TALL_W, TALL_H
    if kind == "button":
        return (w or BTN_W_DEF), BTN_H
    if kind == "arrow":
        return ARROW_W, ARROW_H
    return FLAME_W, FLAME_H


def side_of(x, pw, w):
    return "input" if x + pw / 2 < w / 2 else "output"


def clean_piece(s, w, h):
    """Lenient: used when reading model files (they may be edited by hand)."""
    if not isinstance(s, dict) or s.get("type") not in PIECE_TYPES:
        return None
    kind = s["type"]
    p = {"type": kind}
    if kind == "button":
        text = s.get("text")
        p["text"] = (text.strip()[:20] if isinstance(text, str) else "") or "Button"
        p["w"] = clamp(s.get("w"), BTN_W_MIN, BTN_W_MAX, BTN_W_DEF)
    elif kind == "arrow":
        p["progress"] = clamp(s.get("progress"), 0, 100, 50)
    elif kind == "flame":
        p["level"] = clamp(s.get("level"), 0, 100, 75)
    else:
        name = s.get("name")
        icon = s.get("icon")
        p["name"] = name.strip()[:30] if isinstance(name, str) else ""
        p["amount"] = clamp(s.get("amount"), 1, AMT_MAX, None)
        p["icon"] = icon if isinstance(icon, str) and icon else None
    pw, ph = piece_size(kind, p.get("w"))
    p["x"] = clamp(s.get("x"), 0, max(0, w - pw), 0)
    p["y"] = clamp(s.get("y"), 0, max(0, h - ph), 0)
    if kind in SLOT_TYPES:
        p["side"] = side_of(p["x"], pw, w)
        # active: this slot gets a connection square on the block (default: yes)
        p["active"] = s["active"] if isinstance(s.get("active"), bool) else True
    return p


def clean_model(data, stem):
    if not isinstance(data, dict) or not isinstance(data.get("name"), str):
        return None
    w = clamp(data.get("width"), UW_MIN, UW_MAX, UW_DEF)
    h = clamp(data.get("height"), UH_MIN, UH_MAX, UH_DEF)
    raw = data.get("pieces")
    if not isinstance(raw, list):
        raw = data.get("slots")          # models saved by the previous version
    pieces = [clean_piece(s, w, h) for s in (raw if isinstance(raw, list) else [])[:MAX_PIECES]]
    arrow = data.get("defaultArrow")
    return {"file": stem, "name": data["name"].strip()[:40], "width": w, "height": h,
            "defaultArrow": arrow if isinstance(arrow, bool) else True,
            "pieces": [p for p in pieces if p]}


def ui_models():
    d = os.path.join(BASE, UI_DIR)
    out = []
    if not os.path.isdir(d):
        return out
    for f in sorted(os.listdir(d)):
        if not f.lower().endswith(".json"):
            continue
        try:
            with open(os.path.join(d, f), encoding="utf-8") as fh:
                m = clean_model(json.load(fh), f[:-5])
        except Exception:
            continue
        if m:
            out.append(m)
    return out


def is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def strict_piece(s, w, h):
    """Strict: used when saving a model from the editor. Returns (piece, rect)."""
    if not isinstance(s, dict) or s.get("type") not in PIECE_TYPES:
        raise ValueError("invalid piece type")
    kind = s["type"]
    p = {"type": kind}
    if kind == "button":
        text = s.get("text")
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 20:
            raise ValueError("button text must be 1-20 characters")
        bw = s.get("w", BTN_W_DEF)
        if not (is_int(bw) and BTN_W_MIN <= bw <= BTN_W_MAX):
            raise ValueError("button width out of range (%d-%d)" % (BTN_W_MIN, BTN_W_MAX))
        p["text"], p["w"] = text.strip(), bw
    elif kind in ("arrow", "flame"):
        key = "progress" if kind == "arrow" else "level"
        v = s.get(key, 50 if kind == "arrow" else 75)
        if not (is_int(v) and 0 <= v <= 100):
            raise ValueError("%s must be 0-100" % key)
        p[key] = v
    # item / fluid / energy slots are only a frame: what goes in them is set in the block
    active = s.get("active")
    if kind in SLOT_TYPES and active is not None and not isinstance(active, bool):
        raise ValueError("active must be true or false")
    pw, ph = piece_size(kind, p.get("w"))
    x, y = s.get("x"), s.get("y")
    if not (is_int(x) and is_int(y) and 0 <= x <= w - pw and 0 <= y <= h - ph):
        raise ValueError("piece outside the canvas")
    p["x"], p["y"] = x, y
    if kind in SLOT_TYPES:
        p["side"] = side_of(x, pw, w)
        p["active"] = active if isinstance(active, bool) else True
    return p, (x, y, pw, ph)


def strict_model(data):
    name = data.get("name")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 40:
        raise ValueError("invalid name (1-40 characters)")
    w, h = data.get("width"), data.get("height")
    if not (is_int(w) and UW_MIN <= w <= UW_MAX and is_int(h) and UH_MIN <= h <= UH_MAX):
        raise ValueError("size out of range (width %d-%d, height %d-%d)" % (UW_MIN, UW_MAX, UH_MIN, UH_MAX))
    raw = data.get("pieces")
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_PIECES:
        raise ValueError("a UI needs 1 to %d pieces" % MAX_PIECES)
    arrow = data.get("defaultArrow", True)
    if not isinstance(arrow, bool):
        raise ValueError("invalid defaultArrow")
    pieces, rects = [], []
    for s in raw:
        p, (x, y, pw, ph) = strict_piece(s, w, h)
        for ox, oy, ow, oh in rects:
            if x < ox + ow and ox < x + pw and y < oy + oh and oy < y + ph:
                raise ValueError("pieces overlap")
        pieces.append(p)
        rects.append((x, y, pw, ph))
    return {"name": name.strip(), "width": w, "height": h, "defaultArrow": arrow, "pieces": pieces}


def clean_content(lst):
    """Lenient: one entry per slot, invalid values become empty ones."""
    if not isinstance(lst, list):
        return None
    out = []
    for c in lst[:MAX_PIECES]:
        c = c if isinstance(c, dict) else {}
        name, icon = c.get("name"), c.get("icon")
        out.append({"name": name.strip()[:40] if isinstance(name, str) else "",
                    "amount": clamp(c.get("amount"), 1, AMT_MAX, None),
                    "icon": icon if isinstance(icon, str) and icon else None})
    return out


def strict_content(lst, n):
    if not isinstance(lst, list) or len(lst) != n:
        raise ValueError("content needs %d entr%s, one per slot of the UI" % (n, "y" if n == 1 else "ies"))
    out = []
    for c in lst:
        if not isinstance(c, dict):
            raise ValueError("invalid content entry")
        name = c.get("name") or ""
        if not isinstance(name, str) or len(name.strip()) > 40:
            raise ValueError("content name must be at most 40 characters")
        amount = c.get("amount")
        if amount is not None and not (is_int(amount) and 1 <= amount <= AMT_MAX):
            raise ValueError("amount out of range (1-%d)" % AMT_MAX)
        icon = c.get("icon")
        if icon is not None:
            if not isinstance(icon, str) or os.path.basename(icon) not in icons():
                raise ValueError("icon not found in " + ICON_DIR)
            icon = ICON_DIR + "/" + os.path.basename(icon)
        out.append({"name": name.strip(), "amount": amount, "icon": icon})
    return out


def blocks():
    models = {m["file"]: m for m in ui_models()}
    out = []
    for f in sorted(os.listdir(BASE)):
        if not f.lower().endswith(".json"):
            continue
        try:
            with open(os.path.join(BASE, f), encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            continue
        if isinstance(data, dict) and isinstance(data.get("name"), str):
            out.append({
                "file": f, "name": data["name"], "icon": data.get("icon"),
                "width": clamp(data.get("width"), W_MIN, W_MAX, W_DEF),
                "height": clamp(data.get("height"), H_MIN, H_MAX, H_DEF),
                "inputs": clean_entries(data.get("inputs")),
                "outputs": clean_entries(data.get("outputs")),
                "content": clean_content(data.get("content")),
                "ui": data["ui"] if isinstance(data.get("ui"), str) else None,
                "uiModel": models.get(data.get("ui")) if isinstance(data.get("ui"), str) else None,
            })
    return out


# ---------- connections ----------
def clean_end(e):
    if isinstance(e, dict) and isinstance(e.get("block"), str) and is_int(e.get("slot")) and e["slot"] >= 0:
        return {"block": e["block"], "slot": e["slot"]}
    return None


def read_links():
    try:
        with open(os.path.join(BASE, LINKS_FILE), encoding="utf-8") as fh:
            raw = json.load(fh).get("links", [])
    except Exception:
        return []
    out = []
    for l in raw if isinstance(raw, list) else []:
        if not isinstance(l, dict):
            continue
        a, b = clean_end(l.get("from")), clean_end(l.get("to"))
        if a and b:
            out.append({"from": a, "to": b})
    return out


def write_links(lst):
    with open(os.path.join(BASE, LINKS_FILE), "w", encoding="utf-8") as fh:
        json.dump({"links": lst}, fh, ensure_ascii=False, indent=2)


def port_info(bl, end):
    b = next((x for x in bl if x["file"] == end["block"]), None)
    m = b["uiModel"] if b else None
    slots = [p for p in m["pieces"] if p["type"] in SLOT_TYPES] if m else []
    if not 0 <= end["slot"] < len(slots) or not slots[end["slot"]].get("active"):
        raise ValueError("port not found")
    return slots[end["slot"]]


def read_layout():
    try:
        with open(os.path.join(BASE, LAYOUT_FILE), encoding="utf-8") as fh:
            raw = json.load(fh).get("pos", {})
    except Exception:
        return {}
    out = {}
    for k, v in (raw.items() if isinstance(raw, dict) else []):
        if isinstance(k, str) and isinstance(v, dict) and is_int(v.get("x")) and is_int(v.get("y")):
            out[k] = {"x": max(0, min(POS_MAX, v["x"])), "y": max(0, min(POS_MAX, v["y"]))}
    return out


def write_layout(d):
    with open(os.path.join(BASE, LAYOUT_FILE), "w", encoding="utf-8") as fh:
        json.dump({"pos": d}, fh, ensure_ascii=False, indent=2)


def slug(s):
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_") or "blocco"


def create(folder, base, payload):
    os.makedirs(folder, exist_ok=True)
    n = 1
    while True:
        fname = base + ("" if n == 1 else "_%d" % n) + ".json"
        try:
            with open(os.path.join(folder, fname), "x", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
            return fname
        except FileExistsError:
            n += 1


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=BASE, **k)

    def log_message(self, *a):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def reply(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/blocks":
            return self.reply(blocks())
        if path == "/api/icons":
            return self.reply(icons())
        if path == "/api/uis":
            return self.reply(ui_models())
        if path == "/api/links":
            return self.reply(read_links())
        if path == "/api/layout":
            return self.reply(read_layout())
        if path == "/api/version":
            return self.reply({"version": VERSION})
        if path.lower().endswith((".py", ".bat")):
            return self.send_error(404)
        super().do_GET()

    def do_POST(self):
        if self.path not in ("/api/blocks", "/api/uis", "/api/links", "/api/links/delete", "/api/layout") \
                or "application/json" not in self.headers.get("Content-Type", ""):
            return self.reply({"error": "invalid request"}, 400)
        try:
            n = int(self.headers.get("Content-Length", "0"))
            data = json.loads(self.rfile.read(n).decode("utf-8"))
            assert isinstance(data, dict)
        except Exception:
            return self.reply({"error": "invalid data"}, 400)
        if self.path == "/api/layout":
            return self.layout_post(data)
        if self.path.startswith("/api/links"):
            return self.links_post(data)
        if self.path == "/api/uis":
            try:
                model = strict_model(data)
            except ValueError as err:
                return self.reply({"error": str(err)}, 400)
            fname = create(os.path.join(BASE, UI_DIR), slug(model["name"]), model)
            return self.reply({"file": UI_DIR + "/" + fname})
        self.create_block(data)

    def layout_post(self, data):
        block, x, y = data.get("block"), data.get("x"), data.get("y")
        if not (isinstance(block, str) and block == os.path.basename(block) and block.lower().endswith(".json")
                and is_int(x) and is_int(y) and 0 <= x <= POS_MAX and 0 <= y <= POS_MAX):
            return self.reply({"error": "invalid position"}, 400)
        with LAYOUT_LOCK:
            lay = read_layout()
            lay[block] = {"x": x, "y": y}
            write_layout(lay)
        self.reply({"ok": True})

    def links_post(self, data):
        a, b = clean_end(data.get("from")), clean_end(data.get("to"))
        if not (a and b):
            return self.reply({"error": "invalid connection"}, 400)
        with LINK_LOCK:
            links = read_links()
            if self.path == "/api/links/delete":
                write_links([l for l in links if not (l["from"] == a and l["to"] == b)])
                return self.reply({"ok": True})
            if a["block"] == b["block"]:
                return self.reply({"error": "a block cannot be connected to itself"}, 400)
            try:
                bl = blocks()
                pa, pb = port_info(bl, a), port_info(bl, b)
            except ValueError as err:
                return self.reply({"error": str(err)}, 400)
            if pa["side"] != "output" or pb["side"] != "input":
                return self.reply({"error": "connect an output to an input"}, 400)
            if pa["type"] != pb["type"]:
                return self.reply({"error": "only same types: item-item, fluid-fluid, FE-FE"}, 400)
            if any(l["from"] == a and l["to"] == b for l in links):
                return self.reply({"error": "already connected"}, 400)
            links.append({"from": a, "to": b})
            write_links(links)
        self.reply({"ok": True})

    def create_block(self, data):
        try:
            name = data["name"].strip()
            icon = data.get("icon")
            width, height = data["width"], data["height"]
        except Exception:
            return self.reply({"error": "invalid data"}, 400)
        if not name or len(name) > 40:
            return self.reply({"error": "invalid name"}, 400)
        ok = lambda v, lo, hi: isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi
        if not (ok(width, W_MIN, W_MAX) and ok(height, H_MIN, H_MAX)):
            return self.reply({"error": "size out of range (width %d-%d, height %d-%d)" % (W_MIN, W_MAX, H_MIN, H_MAX)}, 400)
        if icon is not None:
            if not isinstance(icon, str) or os.path.basename(icon) not in icons():
                return self.reply({"error": "icon not found in " + ICON_DIR}, 400)
            icon = ICON_DIR + "/" + os.path.basename(icon)
        ui = data.get("ui")
        models = {m["file"]: m for m in ui_models()}
        if ui is not None and (not isinstance(ui, str) or ui not in models):
            return self.reply({"error": "UI model not found in " + UI_DIR}, 400)
        slots = [p for p in models[ui]["pieces"] if p["type"] in SLOT_TYPES] if ui else []
        try:
            content = strict_content(data.get("content", []), len(slots))
        except ValueError as err:
            return self.reply({"error": str(err)}, 400)
        payload = {"name": name, "icon": icon, "width": width, "height": height, "ui": ui, "content": content}
        fname = create(BASE, slug(name), payload)
        self.reply({"file": fname, "width": width, "height": height, "ui": ui, "content": content})


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    for port in range(8000, 8011):
        try:
            srv = Server(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    else:
        raise SystemExit("No free port between 8000 and 8010")
    url = "http://localhost:%d" % port
    print("Production tree running at " + url)
    print("Folder: " + BASE)
    print("Press Ctrl+C to quit.")
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()