#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
 rice.py — OUTLAWSYL theme orchestrator (Ubuntu/WSL2 ⇄ Win11)

   🖼 WALLPAPER → rice_wall.exe overlay crossfade (top-level layered popup,
       HWND_BOTTOM). No COM, no flicker.
   🎵 MUSIC    → WSL mpv A/B crossfade + TCP relay + SMTC bridge
       (frozen stack; bridge auto-restarts on code updates and has
        a force-repair action in settings).
   🎨 YASB     → role-mapped hex swap (frozen).
   🖥 TERMINAL → surgical settings.json patch (frozen).
   ✦ UI        → gallery menus with real image previews (Unicode
       half-blocks + ffmpeg thumbnails), ANSI logo, main menu is
       just themes / wallpaper / music / settings.

 gallery needs ≥84 cols (maximize WT) + ffmpeg for previews.
 Falls back gracefully without either.

 FISH ALIAS
   alias rice 'python3 /mnt/c/Users/lenov/rice/rice.py'; funcsave rice
"""

import argparse, glob, hashlib, json, ntpath, os, re, shutil, socket, \
       subprocess, sys, threading, time, traceback
from datetime import datetime

IS_WIN = (os.name == "nt")
IS_WSL = False
if not IS_WIN:
    try:
        with open("/proc/version", encoding="utf-8", errors="ignore") as f:
            IS_WSL = "microsoft" in f.read().lower()
    except OSError:
        pass
    IS_WSL = IS_WSL or bool(os.environ.get("WSL_DISTRO_NAME"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE        = os.path.dirname(os.path.abspath(__file__))
STATE_PATH  = os.path.join(HERE, "rice_state.json")
LOG_PATH    = os.path.join(HERE, "rice_debug.log")
AUDIO_LOG   = os.path.join(HERE, "rice_audio.log")
YASB_DATA   = os.path.join(HERE, "yasb")
NP_JSON     = os.path.join(HERE, "np.json")
THUMB_DIR   = os.path.join(HERE, "thumbs")
FW_DIRS     = ["/mnt/c/Windows/Microsoft.NET/Framework64/v4.0.30319",
               "/mnt/c/Windows/Microsoft.NET/Framework/v4.0.30319"]
DN          = subprocess.DEVNULL
INTERACTIVE = sys.stdin.isatty() and sys.stdout.isatty()

CFG = {
    "win_user": "hi", "volume": 70, "crossfade": 2.8,
    "win_fade_wait": 800,
    "shuffle": False, "wt_profile": "Ubuntu",
    "wallpaper_dir": r"D:\pics_dump\wallpaper",
    "music_dir":     r"C:\Users\lenov\Music",
    "yasb_dir": r"C:\Program Files\YASB",
    "yasb_styles": [r"C:\Users\lenov\.config\yasb\styles.css"],
    "yasb_configs": [r"C:\Users\lenov\.config\yasb\config.yaml",
                     r"C:\Program Files\YASB\config.yaml"],
    "wt_settings": [
        r"C:\Users\lenov\AppData\Local\Packages\Microsoft.WindowsTerminal_8wekyb3d8bbwe\LocalState\settings.json",
        r"C:\Users\lenov\AppData\Local\Packages\Microsoft.WindowsTerminalPreview_8wekyb3d8bbwe\LocalState\settings.json",
        r"C:\Users\lenov\AppData\Local\Microsoft\Windows Terminal\settings.json",
    ],
}

THEME_PALETTES = {
    "amber": {"accent":"#AC8E2B","accent_dim":"#8B6508","accent_shift":"#c17a3a",
              "text":"#d3a16d","text_dim":"#a89a78","bg":"#14110a",
              "surface":"#27221a","border":"#3a3226","overlay":"#5c5140"},
    "pink":  {"accent":"#f4b8e4","accent_dim":"#9F7894","accent_shift":"#c4a8e8",
              "text":"#ceb8e4","text_dim":"#a890a0","bg":"#141014",
              "surface":"#272028","border":"#3a2e36","overlay":"#5f4858"},
    "blue":  {"accent":"#89b4fa","accent_dim":"#5B6E9A","accent_shift":"#b4befe",
              "text":"#c0caf9","text_dim":"#a0a8c0","bg":"#12151b",
              "surface":"#282936","border":"#313244","overlay":"#6c7086"},
}

ROLE_MAP = {
    "#89b4fa":"accent","#b4befe":"accent_shift","#f9e2af":"accent",
    "#cdd6f4":"text","#ffffff":"text","#fff":"text","#12151b":"bg",
    "#313244":"border","#282936":"surface","#6c7086":"overlay","#4f5868":"overlay",
}

PRESETS = {
    "1": dict(name="Amber Cyberpunk", emoji="⚡", hex="#AC8E2B",
              wp=r"D:\pics_dump\wallpaper\overspec2.png",
              music=r"C:\Users\lenov\Music\Break My Soul (DELTARUNE) (feat. Hypotoria & Kathy-Chan).mp3",
              wt_scheme="YourRiceTheme", wt_opacity=75, yasb="amber"),
    "2": dict(name="Cozy Pink Catppuccin", emoji="🌸", hex="#f4b8e4",
              wp=r"D:\pics_dump\wallpaper\logan-apple-komorebi-by-thoughtweaver-d9lw3n8.jpg",
              music=r"C:\Users\lenov\Music\songs from Funamusea's games to relax - a playlist.mp3",
              wt_scheme="Catppuccin-Frappe", wt_opacity=75, yasb="pink"),
    "3": dict(name="Baby Blue · No Blur",  emoji="🌊", hex="#8caaee",
              wp=r"D:\pics_dump\wallpaper\wallhaven-wqex9q.jpg",
              music=r"C:\Users\lenov\Music\Kung Fu Fighting (From Kung Fu Panda).mp3",
              wt_scheme="Catppuccin-Frappe", wt_opacity=100, yasb="blue"),
}

CAND = {"yasb_exe": [r"C:\Program Files\YASB\YASB.exe"]}
SOCKS = {"a": "/tmp/mpv-rice-a.sock", "b": "/tmp/mpv-rice-b.sock"}
RELAY_PORTS = {6600: SOCKS["a"], 6601: SOCKS["b"]}
IMG_EXT = {".png",".jpg",".jpeg",".webp",".bmp",".gif",".avif"}
AUD_EXT = {".mp3",".flac",".ogg",".oga",".opus",".wav",".m4a",".aac",".wma",".aiff"}
HEX_RE = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?![0-9a-fA-F])")
VAR_RE = re.compile(r"--([A-Za-z0-9_-]+)\s*:\s*(#[0-9a-fA-F]{3,8})\b")

# ── path bridge + io helpers ─────────────────────────────────────────────
_wpc = {}
def to_host(p):
    if not IS_WSL: return p
    if p.startswith("/"): return p
    if p in _wpc: return _wpc[p]
    q = ""
    try:
        r = subprocess.run(["wslpath", p], capture_output=True, text=True,
                           timeout=5, errors="replace")
        q = r.stdout.strip()
    except Exception: q = ""
    if not q:
        m = re.match(r"^([A-Za-z]):[\\/](.*)$", p)
        if m: q = "/mnt/" + m.group(1).lower() + "/" + m.group(2).replace("\\","/")
    _wpc[p] = q
    return q

def to_win(p):
    if not IS_WSL: return p
    try:
        r = subprocess.run(["wslpath","-w",p], capture_output=True, text=True,
                           timeout=5, errors="replace")
        if r.stdout.strip(): return r.stdout.strip()
    except Exception: pass
    return p

def wbase(p): return ntpath.basename(p)
def rb(p):
    with open(p,"rb") as f: return f.read()
def rt(p): return rb(p).decode("utf-8","surrogateescape")

def atomic_write(p, data):
    tmp = p + ".rice-tmp"
    try:
        with open(tmp,"wb") as f: f.write(data)
        os.replace(tmp,p)
    except OSError:
        with open(p,"wb") as f: f.write(data)

def write_asset(name, content):
    p = os.path.join(HERE, name)
    want = content.strip().encode("utf-8") + b"\n"
    if os.path.isfile(p) and rb(p) == want: return False
    atomic_write(p, want); return True

def dbg(msg):
    try:
        with open(LOG_PATH,"a",encoding="utf-8") as f:
            f.write("[%s] %s\n" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg))
    except OSError: pass

def sh(cmd, timeout=15):
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout, errors="replace")
    except Exception as e:
        dbg("sh failed: %r -> %s" % (cmd, e)); return None

def spawn_win(exe, args=(), cwd=None):
    kw = dict(stdin=DN, stdout=DN, stderr=DN)
    if cwd: kw["cwd"] = cwd
    if IS_WIN: kw["creationflags"] = 0x00000008 | 0x00000200
    else: kw["start_new_session"] = True
    subprocess.Popen([exe, *args], **kw)

def powershell():
    w = shutil.which("powershell.exe")
    if w: return w
    c = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
    return to_host(c) if os.path.exists(to_host(c)) else None

def proc_running(name):
    r = sh(["tasklist.exe","/FI","IMAGENAME eq %s" % name,"/NH"], timeout=12)
    return bool(r and r.stdout and name.lower() in r.stdout.lower())

def find_tool(key, names, cands=()):
    p = STATE.get(key)
    if p and os.path.exists(to_host(p)): return p
    for n in names:
        w = shutil.which(n)
        if w:
            win = to_win(w) if IS_WSL else w
            STATE[key] = win; return win
    for c in cands:
        if os.path.exists(to_host(c)):
            STATE[key] = c; return c
    return None

def _fsafe(s): return re.sub(r"[^A-Za-z0-9._-]+","_",s)
def _tag(p): return _fsafe(wbase(p)) + "-" + hashlib.md5(p.encode()).hexdigest()[:4]

# ── state ────────────────────────────────────────────────────────────────
def load_state():
    try:
        with open(STATE_PATH, encoding="utf-8") as f: return json.load(f)
    except Exception: return {}

SAVE_LOCK = threading.Lock()
def save_state(st):
    with SAVE_LOCK:
        try: atomic_write(STATE_PATH, json.dumps(st, indent=2).encode("utf-8"))
        except OSError as e: dbg("save_state failed: %s" % e)

STATE = load_state()
STATE.setdefault("accent_hexes", ["#8B6508","#AC8E2B"])
STATE.setdefault("yasb_reload", "live")

# ── UI ───────────────────────────────────────────────────────────────────
RST, BOLD, DIM = "\x1b[0m","\x1b[1m","\x1b[2m"
BOXW = 58; PALHEX = "#b4befe"
QUIET = False

LOGO = [
"██████╗  ██╗  ██████╗ ███████╗",
"██╔══██╗ ██║ ██╔════╝ ██╔════╝",
"██████╔╝ ██║ ██║      █████╗  ",
"██╔══██╗ ██║ ██║      ██╔══╝  ",
"██║  ██║ ██║ ███████╗ ███████╗",
"╚═╝  ╚═╝ ╚═╝ ╚══════╝ ╚══════╝",
]

def set_palette(h):
    global PALHEX; PALHEX = h
def hexrgb(h):
    h = h.lstrip("#"); return (int(h[0:2],16),int(h[2:4],16),int(h[4:6],16))
def fg(h):
    r,g,b = hexrgb(h); return "\x1b[38;2;%d;%d;%dm" % (r,g,b)
def clear(): sys.stdout.write("\x1b[2J\x1b[H"); sys.stdout.flush()
def shorten(s,n): return s if len(s)<=n else s[:n-1]+"…"

def np_now():
    try:
        if os.path.isfile(NP_JSON):
            j = rt(NP_JSON)
            m = re.search(r'"title"\s*:\s*"([^"]*)"', j)
            p = re.search(r'"playing"\s*:\s*"?([A-Za-z]+)"?', j)
            return ((m.group(1) if m else ""),
                    (p.group(1) if p else "false") == "true")
    except Exception: pass
    return ("", False)

def status_line():
    tk = STATE.get("theme_key")
    tn = PRESETS[tk]["name"] if tk in PRESETS else "no theme"
    t, playing = np_now()
    np_ = STATE.get("now_playing")
    mus = ("♪ " + shorten(t, 30)) if t else \
          (("np: " + shorten(wbase(np_), 26)) if np_ else "silence")
    if t and not playing: mus += " ·paused"
    return ("theme: %s  ·  %s" % (shorten(tn, 22), mus))[:BOXW]

def logo_header():
    acc = hexrgb(PALHEX)
    dark = tuple(int(c*0.40) for c in acc)
    pad = " " * max((BOXW - 30)//2, 0)
    out = ["\n"]
    for r, row in enumerate(LOGO):
        t = r / max(len(LOGO)-1, 1)
        c = [round(dark[k] + (acc[k]-dark[k]) * t) for k in range(3)]
        out.append(pad + "\x1b[38;2;%d;%d;%dm%s" % (c[0], c[1], c[2], row) + RST)
    out += ["", "  " + DIM + status_line() + RST, ""]
    return "\n".join(out)

def draw_screen(title, items, sel, footer="", header=None):
    clear(); acc = hexrgb(PALHEX)
    if header is not None:
        print(header)
    elif title:
        print("  " + BOLD + fg(PALHEX) + title + RST)
        print("  " + DIM + "─" * 46 + RST + "\n")
    for i,it in enumerate(items):
        if it.get("skip"):
            print()
            continue
        mark = "❯" if i==sel else " "
        body = " %s %s)  %s" % (mark, it["key"], it["label"])
        if i==sel:
            print("\x1b[30m\x1b[48;2;%d;%d;%dm%s%s" % (acc[0],acc[1],acc[2],body,RST))
        elif it.get("cur"):
            print(fg(PALHEX)+body+RST)
        else:
            print(body)
    print()
    if footer: print("  " + DIM + footer + RST)

def read_key():
    if IS_WIN:
        import msvcrt
        ch = msvcrt.getwch()
        if ch == "\x03": raise KeyboardInterrupt
        if ch in ("\x00","\xe0"):
            m = msvcrt.getwch()
            return {"H":"up","P":"down","K":"left","M":"right"}.get(m,"esc")
        return "enter" if ch in ("\r","\n") else ch
    import termios, tty, fcntl
    fd = sys.stdin.fileno(); old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd); b = os.read(fd,1)
        if not b: return "esc"
        ch = b.decode("utf-8","ignore")
        if ch == "\x03": raise KeyboardInterrupt
        if ch == "\x1b":
            fl = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)
            try:
                time.sleep(0.02)
                try: rest = os.read(fd,8)
                except BlockingIOError: rest = b""
            finally:
                fcntl.fcntl(fd, fcntl.F_SETFL, fl)
            if rest.startswith(b"[") and len(rest)>=2:
                c3 = chr(rest[1])
                return {"A":"up","B":"down","C":"right","D":"left"}.get(c3,"esc")
            return "esc"
        return "enter" if ch in ("\r","\n") else ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

def pause(msg="any key to continue"):
    print("\n  "+DIM+"(%s)" % msg+RST, end="", flush=True)
    try: read_key()
    except Exception:
        try: input()
        except EOFError: pass
    print()

def ask_menu(title, items, footer="", header=None):
    sel = 0
    while True:
        draw_screen(title, items, sel, footer, header)
        k = read_key()
        if k == "up": sel = (sel-1)%len(items)
        elif k == "down": sel = (sel+1)%len(items)
        elif k == "enter": return items[sel]
        elif k in ("q","Q","esc"): return None
        else:
            for it in items:
                if k == it["key"]: return it
            if k == "p": music_toggle()

def _p(sym,color,msg): print(" %s %s" % (color+sym+RST,msg))
def step(m):
    if not QUIET: _p("▸",fg(PALHEX),m)
def ok(m):
    if not QUIET: _p("✓","\x1b[32m",m)
def warn(m):
    if not QUIET: _p("⚠","\x1b[33m",m)
def bad(m):
    _p("✗","\x1b[31m",m)

# ── thumbnails (image previews in terminal) ──────────────────────────────
def find_ffmpeg():
    """
    Prefer the native Linux ffmpeg. Windows ffmpeg + WSL 9p has a habit
    of not flushing the output file to where the WSL side can see it
    immediately, which silently breaks the gallery previews.
    """
    w = shutil.which("ffmpeg")
    if w: return w
    w = shutil.which("ffmpeg.exe")
    if w: return w
    c = r"C:\Users\lenov\scoop\shims\ffmpeg.exe"
    if os.path.isfile(to_host(c)): return to_host(c)
    return None

def _thumb_cache_path(path_win, pxw, pxh):
    return os.path.join(THUMB_DIR, "%s_%dx%d.raw" % (_tag(path_win), pxw, pxh))

def render_thumb(path_win, cw, ch):
    pxw, pxh = cw, ch*2
    want = pxw * pxh * 3
    try:
        os.makedirs(THUMB_DIR, exist_ok=True)
        cache = _thumb_cache_path(path_win, pxw, pxh)
        if not (os.path.isfile(cache) and os.path.getsize(cache) == want):
            ff = find_ffmpeg()
            if not ff: return None
            winmode = ff.lower().endswith(".exe")
            inp = to_win(path_win) if winmode else to_host(path_win)
            outp = to_win(cache) if winmode else cache
            vf = ("scale=%d:%d:force_original_aspect_ratio=increase,"
                  "crop=%d:%d" % (pxw, pxh, pxw, pxh))
            r = sh([ff, "-y", "-loglevel", "error", "-i", inp,
                    "-vf", vf, "-frames:v", "1",
                    "-f", "rawvideo", "-pix_fmt", "rgb24", outp], timeout=30)
            # 9p flush race: wait (briefly) for the file to become visible
            # and reach the expected size on the WSL side.
            for _ in range(20):
                if os.path.isfile(cache) and os.path.getsize(cache) == want:
                    break
                time.sleep(0.05)
            if not (os.path.isfile(cache) and os.path.getsize(cache) == want):
                sz = os.path.getsize(cache) if os.path.isfile(cache) else -1
                dbg("thumb fail %s: rc=%s size=%d want=%d stderr=%r"
                    % (path_win, r and r.returncode, sz, want,
                       r and (r.stderr or "")[-200:]))
                return None
        data = rb(cache)
        rows = []
        for y in range(pxh):
            base = y*pxw*3
            rows.append([(data[base+x*3], data[base+x*3+1], data[base+x*3+2])
                         for x in range(pxw)])
        return rows
    except Exception as e:
        dbg("thumb err: %s" % e); return None

def test_ffmpeg_thumb():
    """Actually run the thumbnail pipeline once, return (ok, message)."""
    ff = find_ffmpeg()
    if not ff: return (False, "no ffmpeg")
    samples = list_dir(CFG["wallpaper_dir"], IMG_EXT)
    if not samples: return (False, "no sample image")
    path = samples[0]
    pxw, pxh = 22, 16
    want = pxw * pxh * 3
    try:
        os.makedirs(THUMB_DIR, exist_ok=True)
        tmp = os.path.join(THUMB_DIR, "_diag.raw")
        if os.path.isfile(tmp):
            try: os.remove(tmp)
            except OSError: pass
        winmode = ff.lower().endswith(".exe")
        inp = to_win(path) if winmode else to_host(path)
        outp = to_win(tmp) if winmode else tmp
        vf = ("scale=%d:%d:force_original_aspect_ratio=increase,"
              "crop=%d:%d" % (pxw, pxh, pxw, pxh))
        r = sh([ff, "-y", "-loglevel", "error", "-i", inp,
                "-vf", vf, "-frames:v", "1",
                "-f", "rawvideo", "-pix_fmt", "rgb24", outp], timeout=30)
        for _ in range(20):
            if os.path.isfile(tmp) and os.path.getsize(tmp) == want:
                break
            time.sleep(0.05)
        sz = os.path.getsize(tmp) if os.path.isfile(tmp) else -1
        try: os.remove(tmp)
        except OSError: pass
        if sz == want:
            kind = "win" if winmode else "linux"
            return (True, "%s (%s)" % (wbase(ff), kind))
        err = ""
        if r is not None and r.stderr:
            err = r.stderr.strip().splitlines()[-1][:50] if r.stderr.strip() else ""
        return (False, "size %d≠%d %s" % (sz, want, err))
    except Exception as e:
        return (False, "exception: %s" % e)

def thumb_lines(matrix, dim=1.0):
    out = []
    half = len(matrix)//2
    for y in range(half):
        up, dn = matrix[2*y], matrix[2*y+1]
        parts = []
        for x in range(len(up)):
            ur,ug,ub = up[x]; dr,dg,db = dn[x]
            if dim != 1.0:
                ur=int(ur*dim); ug=int(ug*dim); ub=int(ub*dim)
                dr=int(dr*dim); dg=int(dg*dim); db=int(db*dim)
            parts.append("\x1b[38;2;%d;%d;%dm\x1b[48;2;%d;%d;%dm▀"
                         % (ur,ug,ub,dr,dg,db))
        out.append("".join(parts)+RST)
    return out

def _grad_matrix(w, h, c1, c2):
    a, b = hexrgb(c1), hexrgb(c2)
    rows = []
    for y in range(h):
        t = y/max(h-1,1)
        c = (int(a[0]+(b[0]-a[0])*t), int(a[1]+(b[1]-a[1])*t),
             int(a[2]+(b[2]-a[2])*t))
        rows.append([c]*w)
    return rows

def _tile(mat, name, color, selected, current, dim_if_unsel=True):
    img = thumb_lines(mat, 1.0 if selected else (0.55 if dim_if_unsel else 1.0))
    w = len(mat[0])
    bc = color if selected else "\x1b[90m"
    lines = [bc + "╭" + "─"*w + "╮" + RST]
    for l in img:
        lines.append(bc + "│" + l + bc + "│" + RST)
    lines.append(bc + "╰" + "─"*w + "╯" + RST)
    mark = "● " if current else "  "
    nm = shorten(name, w-2)
    if selected:
        lines.append("  " + BOLD + fg(color) + mark + nm + RST)
    elif current:
        lines.append("  " + fg(color) + mark + nm + RST)
    else:
        lines.append("  " + DIM + mark + nm + RST)
    return lines

def _join_rows(tile_lists, gap="  "):
    height = max(len(t) for t in tile_lists)
    out = []
    for r in range(height):
        parts = []
        for t in tile_lists:
            parts.append(t[r] if r < len(t) else "")
        out.append(" " + gap.join(parts))
    return out

def _wide_enough(need=84):
    try: return shutil.get_terminal_size((120,30)).columns >= need
    except Exception: return True

# ── gallery: themes ──────────────────────────────────────────────────────
def themes_menu():
    if not _wide_enough():
        items = [{"key":k, "label":"%s  (full theme)" % p["name"],
                  "fn": (lambda kk=k: apply_preset(kk))}
                 for k,p in PRESETS.items()]
        items.append({"key":"b","label":"← back","back":True,"fn":None})
        submenu("themes", items)
        return
    keys = sorted(PRESETS.keys())
    sel = 0
    while True:
        clear()
        print("  " + BOLD + fg(PALHEX) + "themes" + RST +
              DIM + "  ·  pick a world" + RST)
        print("  " + DIM + "─"*46 + RST + "\n")
        tiles = []
        for i, k in enumerate(keys):
            p = PRESETS[k]
            pal = THEME_PALETTES[p["yasb"]]
            mat = render_thumb(p["wp"], 22, 9)
            if mat is None:
                mat = _grad_matrix(22, 18, pal["bg"], pal["accent"])
            tiles.append(_tile(mat, p["name"].lower(), pal["accent"],
                               i == sel, STATE.get("theme_key") == k))
        for line in _join_rows(tiles):
            print(line)
        print("\n  " + DIM +
              "←/→ select · enter apply · 1-3 jump · p pause · q back" + RST)
        k = read_key()
        if k in ("q","Q","esc"): return
        elif k == "left": sel = (sel-1) % len(keys)
        elif k == "right": sel = (sel+1) % len(keys)
        elif k == "enter": apply_preset(keys[sel])
        elif k in keys: apply_preset(k)
        elif k == "p": music_toggle()

# ── gallery: wallpapers ──────────────────────────────────────────────────
def wallpaper_gallery():
    files = list_dir(CFG["wallpaper_dir"], IMG_EXT)
    if not files: bad("no images in %s" % CFG["wallpaper_dir"]); return
    page, GW, GH = 0, 3, 2
    per = GW*GH
    sel = 0
    while True:
        pages = max(1, (len(files)+per-1)//per)
        chunk = files[page*per : page*per+per]
        if sel >= len(chunk): sel = max(len(chunk)-1, 0)
        clear()
        print("  " + BOLD + fg(PALHEX) + "wallpaper" + RST + DIM +
              "  ·  %d images · page %d/%d" % (len(files), page+1, pages) + RST)
        print("  " + DIM + "─"*46 + RST + "\n")
        grid = []
        for i, f in enumerate(chunk):
            mat = render_thumb(f, 22, 8)
            if mat is None:
                mat = _grad_matrix(22, 16, "#1c1d26", "#3a3d4d")
            grid.append(_tile(mat, wbase(f), PALHEX, i == sel,
                              ntpath.normcase(f) ==
                              ntpath.normcase(STATE.get("wallpaper") or "")))
        while len(grid) % GW: grid.append([""]*13)
        for r in range(GH):
            row_tiles = grid[r*GW:(r+1)*GW]
            if any(row_tiles):
                for line in _join_rows(row_tiles):
                    print(line)
                print()
        print("  " + DIM +
              "arrows move · enter set · 1-6 jump · n/v pages · "
              "p pause · q back" + RST)
        k = read_key()
        if k in ("q","Q","esc"): return
        elif k == "left": sel = (sel-1) % max(len(chunk),1)
        elif k == "right": sel = (sel+1) % max(len(chunk),1)
        elif k == "up": sel = max(sel-GW, 0)
        elif k == "down": sel = min(sel+GW, len(chunk)-1)
        elif k == "n": page = (page+1)%pages; sel = 0
        elif k == "v": page = (page-1)%pages; sel = 0
        elif k == "p": music_toggle()
        elif k == "enter":
            if chunk: set_wallpaper(chunk[sel])
        elif k.isdigit() and 1 <= int(k) <= len(chunk):
            set_wallpaper(chunk[int(k)-1])

# ── compiler helpers ─────────────────────────────────────────────────────
def find_csc():
    for d in FW_DIRS:
        p = os.path.join(d,"csc.exe")
        if os.path.isfile(p): return to_win(p)
    return None

def net_ref(name):
    for d in FW_DIRS:
        p = os.path.join(d, name+".dll")
        if os.path.isfile(p): return to_win(p)
    for g in sorted(glob.glob("/mnt/c/Windows/Microsoft.NET/assembly/GAC_MSIL/%s/*/%s.dll" % (name,name))):
        return to_win(g)
    return None

def find_winmds():
    md = "/mnt/c/Windows/System32/WinMetadata"; out=[]
    for n in ("Windows.Foundation.winmd","Windows.Media.winmd","Windows.Storage.winmd"):
        p = os.path.join(md,n)
        if os.path.isfile(p): out.append(to_win(p))
    return out

def compile_exe(cs_name, exe_name, refs):
    cs = os.path.join(HERE, cs_name); exe = os.path.join(HERE, exe_name)
    csc = find_csc()
    if not csc: bad("csc.exe not found — cannot compile %s" % exe_name); return False
    args = ["/nologo","/target:exe","/platform:anycpu","/out:"+to_win(exe)]
    for r in refs: args.append("/r:"+r)
    args.append(to_win(cs))
    r = sh(["cmd.exe","/c","cd","/d",r"C:\Users\lenov\rice","&&",csc]+args, timeout=240)
    if r is None:
        bad("%s compile: csc never ran" % exe_name); return False
    if r.returncode == 0 and os.path.isfile(exe): return True
    bad("%s compile FAILED (rc=%d) — csc said:" % (exe_name, r.returncode))
    out = (r.stderr or "") + (r.stdout or "")
    for l in out.splitlines()[:16]:
        if l.strip(): print("      "+l.strip())
    dbg("csc %s: rc=%r err=%s" % (exe_name, r.returncode, out[-2000:]))
    return False

# ── WALLPAPER: top-level HWND_BOTTOM overlay (frozen) ────────────────────
WALL_CS = r"""
using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;

internal static class RiceWall
{
    [StructLayout(LayoutKind.Sequential)]
    private struct POINT { public int X, Y; }
    [StructLayout(LayoutKind.Sequential)]
    private struct SIZE { public int CX, CY; }
    [StructLayout(LayoutKind.Sequential)]
    private struct BF { public byte BlendOp, BlendFlags,
                                 SourceConstantAlpha, AlphaFormat; }

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern bool SystemParametersInfoW(uint a, uint b, string c, uint d);
    [DllImport("user32.dll", SetLastError = true)]
    private static extern IntPtr CreateWindowEx(int ex, string cls, string name,
        int style, int x, int y, int w, int h, IntPtr parent, IntPtr menu,
        IntPtr inst, IntPtr param);
    [DllImport("user32.dll")]
    private static extern bool DestroyWindow(IntPtr h);
    [DllImport("user32.dll")]
    private static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y,
        int w, int hh, uint flags);
    [DllImport("user32.dll")]
    private static extern IntPtr GetDC(IntPtr h);
    [DllImport("user32.dll")]
    private static extern int ReleaseDC(IntPtr h, IntPtr dc);
    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool UpdateLayeredWindow(IntPtr hwnd, IntPtr dst,
        ref POINT pd, ref SIZE ps, IntPtr src, ref POINT psc,
        int key, ref BF blend, int flags);
    [DllImport("user32.dll")]
    private static extern int GetSystemMetrics(int nIndex);
    [DllImport("gdi32.dll")]
    private static extern IntPtr CreateCompatibleDC(IntPtr h);
    [DllImport("gdi32.dll")]
    private static extern IntPtr SelectObject(IntPtr dc, IntPtr o);
    [DllImport("gdi32.dll")]
    private static extern bool DeleteObject(IntPtr o);
    [DllImport("gdi32.dll")]
    private static extern bool DeleteDC(IntPtr dc);
    [DllImport("user32.dll")]
    private static extern bool SetProcessDPIAware();

    public static string SetPlain(string p)
    {
        if (SystemParametersInfoW(0x0014, 0, p, 0x01 | 0x02)) return "OK set";
        return "ERR spi";
    }

    private static Bitmap LoadCover(string path, int W, int H)
    {
        Bitmap bmp = new Bitmap(W, H, PixelFormat.Format32bppArgb);
        using (Graphics g = Graphics.FromImage(bmp))
        {
            g.Clear(Color.Black);
            using (Image srcImg = Image.FromFile(path))
            {
                float ra = (float)W / srcImg.Width;
                float rb = (float)H / srcImg.Height;
                float r = Math.Max(ra, rb);
                int nw = (int)(srcImg.Width * r);
                int nh = (int)(srcImg.Height * r);
                g.DrawImage(srcImg, (W - nw) / 2, (H - nh) / 2, nw, nh);
            }
        }
        return bmp;
    }

    public static string SetWithOverlay(string oldPath, string newPath, int durMs)
    {
        if (oldPath == null || oldPath.Length == 0 ||
            !File.Exists(oldPath) || oldPath == newPath)
            return SetPlain(newPath);

        int W = GetSystemMetrics(0);
        int H = GetSystemMetrics(1);
        if (W <= 0 || H <= 0) return "ERR:size";

        Bitmap bmp = null;
        try { bmp = LoadCover(oldPath, W, H); }
        catch (Exception ex) { return "ERR:load " + ex.Message; }

        const int WS_POPUP = unchecked((int)0x80000000);
        const int WS_VISIBLE = 0x10000000;
        const int WS_EX_LAYERED = 0x00080000;
        const int WS_EX_TOOLWINDOW = 0x00000080;
        const int WS_EX_NOACTIVATE = 0x08000000;
        const int WS_EX_TRANSPARENT = 0x00000020;
        const int ULW_ALPHA = 0x02;
        const int AC_SRC_OVER = 0x00;
        const int HWND_BOTTOM = 1;
        const uint SWP_NOSIZE = 0x0001;
        const uint SWP_NOMOVE = 0x0002;
        const uint SWP_NOACTIVATE = 0x0010;
        const uint SWP_SHOWWINDOW = 0x0040;

        IntPtr hwnd = IntPtr.Zero;
        IntPtr screenDc = IntPtr.Zero;
        IntPtr memDc = IntPtr.Zero;
        IntPtr hBmp = IntPtr.Zero;
        IntPtr oldBmp = IntPtr.Zero;
        try
        {
            hwnd = CreateWindowEx(
                WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE |
                WS_EX_TRANSPARENT,
                "Static", "RiceFade",
                WS_POPUP | WS_VISIBLE,
                0, 0, W, H,
                IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero);
            if (hwnd == IntPtr.Zero)
                return "ERR:CreateWindow " + Marshal.GetLastWin32Error();

            SetWindowPos(hwnd, (IntPtr)HWND_BOTTOM, 0, 0, 0, 0,
                         SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE |
                         SWP_SHOWWINDOW);

            screenDc = GetDC(IntPtr.Zero);
            memDc = CreateCompatibleDC(screenDc);
            hBmp = bmp.GetHbitmap();
            oldBmp = SelectObject(memDc, hBmp);

            POINT dst = new POINT(); dst.X = 0; dst.Y = 0;
            POINT src = new POINT(); src.X = 0; src.Y = 0;
            SIZE sz = new SIZE(); sz.CX = W; sz.CY = H;
            BF bf = new BF();
            bf.BlendOp = AC_SRC_OVER;
            bf.BlendFlags = 0;
            bf.AlphaFormat = 0;
            bf.SourceConstantAlpha = 255;

            if (!UpdateLayeredWindow(hwnd, screenDc, ref dst, ref sz,
                                     memDc, ref src, 0, ref bf, ULW_ALPHA))
                return "ERR:ULW " + Marshal.GetLastWin32Error();

            SystemParametersInfoW(0x0014, 0, newPath, 0x01 | 0x02);

            if (durMs < 200) durMs = 200;
            int steps = 40;
            int delay = Math.Max(10, durMs / steps);
            for (int i = 1; i <= steps; i++)
            {
                bf.SourceConstantAlpha = (byte)(255 - 255 * i / steps);
                UpdateLayeredWindow(hwnd, screenDc, ref dst, ref sz,
                                    memDc, ref src, 0, ref bf, ULW_ALPHA);
                Thread.Sleep(delay);
            }
            return "OK fade";
        }
        catch (Exception ex)
        {
            try { SystemParametersInfoW(0x0014, 0, newPath, 0x01 | 0x02); }
            catch { }
            return "ERR:" + ex.Message;
        }
        finally
        {
            try
            {
                if (oldBmp != IntPtr.Zero) SelectObject(memDc, oldBmp);
                if (hBmp != IntPtr.Zero) DeleteObject(hBmp);
                if (memDc != IntPtr.Zero) DeleteDC(memDc);
                if (screenDc != IntPtr.Zero) ReleaseDC(IntPtr.Zero, screenDc);
                if (hwnd != IntPtr.Zero) DestroyWindow(hwnd);
                if (bmp != null) bmp.Dispose();
            }
            catch { }
        }
    }

    public static int Main(string[] args)
    {
        try { SetProcessDPIAware(); } catch { }
        try
        {
            string old = "", nw = "";
            int dur = 800;
            for (int i = 0; i + 1 < args.Length; i += 2)
            {
                if (args[i] == "-old") old = args[i + 1];
                else if (args[i] == "-new") nw = args[i + 1];
                else if (args[i] == "-plain")
                { Console.WriteLine(SetPlain(args[i + 1])); return 0; }
                else if (args[i] == "-wait" || args[i] == "-dur")
                { try { dur = int.Parse(args[i + 1]); } catch { } }
            }
            if (nw == "") { Console.WriteLine("ERR no -new"); return 1; }
            Console.WriteLine(SetWithOverlay(old, nw, dur));
            return 0;
        }
        catch (Exception ex)
        {
            Console.WriteLine("ERR " + ex.Message);
            return 1;
        }
    }
}
"""

def ensure_wall_assets():
    changed = write_asset("rice_wall.cs", WALL_CS)
    exe = os.path.join(HERE, "rice_wall.exe")
    if changed and os.path.isfile(exe):
        try: os.remove(exe)
        except OSError: pass
    for stale in ("rice_wall.dll", "wallpaper.ps1", "rice_wall_compile.ps1"):
        p = os.path.join(HERE, stale)
        if os.path.isfile(p):
            try: os.remove(p)
            except OSError: pass
    if not os.path.isfile(exe):
        refs = []
        for n in ("System", "System.Drawing"):
            r = net_ref(n)
            if r: refs.append(r)
            else: warn("%s.dll not found — compile may fail" % n)
        step("compiling rice_wall.exe (overlay fade engine)…")
        if compile_exe("rice_wall.cs", "rice_wall.exe", refs):
            ok("rice_wall.exe compiled")

def wp_call(mode, new="", old=""):
    ensure_wall_assets()
    exe = to_host(os.path.join(HERE, "rice_wall.exe"))
    if not os.path.isfile(exe): return None
    if mode == "plain":
        return sh([exe, "-plain", new], timeout=20)
    return sh([exe, "-old", old, "-new", new,
               "-wait", str(int(CFG["win_fade_wait"]))], timeout=30)

def _last(r):
    if r is None or not r.stdout: return ""
    ls = [l.strip() for l in r.stdout.splitlines() if l.strip()]
    return ls[-1] if ls else ""

def query_wallpaper():
    ps = powershell()
    if not ps: return ""
    r = sh([ps, "-NoProfile", "-Command",
            "(Get-ItemProperty 'HKCU:\\Control Panel\\Desktop').Wallpaper"],
           timeout=15)
    if r and r.stdout:
        p = r.stdout.strip().strip('"')
        if p: return p
    return ""

def set_wallpaper(wp, use_fade=True):
    step("wallpaper → %s" % shorten(wbase(wp), 46))
    if not os.path.isfile(to_host(wp)): bad("not found: %s" % wp); return False
    cur = STATE.get("wallpaper") or query_wallpaper()
    if cur and ntpath.normcase(cur) == ntpath.normcase(wp):
        ok("already current."); STATE["wallpaper"] = wp; save_state(STATE)
        return True
    if use_fade and cur and os.path.isfile(to_host(cur)):
        r = wp_call("fade", new=wp, old=cur)
        line = _last(r)
        if line.startswith("OK fade"):
            STATE["wallpaper"] = wp; save_state(STATE)
            ok("dissolved ✓")
            return True
        if r is not None and line:
            dbg("wall fade: %s" % line)
            warn("overlay fade hiccup (%s)" % line[:60])
    r = wp_call("plain", new=wp)
    if _last(r).startswith("OK"):
        STATE["wallpaper"] = wp; save_state(STATE); ok("wallpaper set.")
        return True
    if spi_set_wallpaper(wp):
        STATE["wallpaper"] = wp; save_state(STATE); ok("wallpaper set (Win32).")
        return True
    bad("could not set the wallpaper."); return False

def spi_set_wallpaper(wp):
    if IS_WIN:
        import ctypes; return bool(ctypes.windll.user32.SystemParametersInfoW(20,0,wp,3))
    ps = powershell()
    if not ps: return False
    s = ("Add-Type -TypeDefinition 'using System.Runtime.InteropServices;"
         "public class W{[DllImport(\"user32.dll\",CharSet=CharSet.Unicode)]"
         "public static extern bool SystemParametersInfoW(uint a,uint b,string c,uint d);}';"
         " [W]::SystemParametersInfoW(20,0,'%s',3)" % wp.replace("'","''"))
    r = sh([ps,"-NoProfile","-Command",s], timeout=20)
    return bool(r and r.returncode == 0)

# ── MUSIC (frozen engine) ────────────────────────────────────────────────
NP_LUA = r"""
local NP = '%NP%'
local function js(s)
    if not s then s = '' end
    s = tostring(s)
    s = s:gsub('\\','\\\\'):gsub('"','\\"'):gsub('[%c]',' ')
    return '"'..s..'"'
end
local function dump()
    local m = mp.get_property_native('metadata') or {}
    local p = mp.get_property_native('pause')
    local t = m.title or mp.get_property_native('filename') or ''
    local a = m.artist or ''
    local pl = (p and 'false') or 'true'
    local f = io.open(NP,'w')
    if f then
        f:write('{"title":'..js(t)..',"artist":'..js(a)..',"playing":"'..pl..'"}')
        f:close()
    end
end
mp.register_event('file-loaded', dump)
mp.observe_property('pause','bool',function() dump() end)
mp.register_event('shutdown',function()
    local f = io.open(NP,'w')
    if f then f:write('{"title":"","artist":"","playing":"false"}'); f:close() end
end)
"""

def ensure_np_watcher():
    write_asset("np_watcher.lua", NP_LUA.replace("%NP%", NP_JSON))
    if not os.path.isfile(NP_JSON):
        atomic_write(NP_JSON, b'{"title":"","artist":"","playing":"false"}')
    return os.path.join(HERE,"np_watcher.lua")

def mpv_send(sock_path, cmd, want_reply=True, timeout=3.0):
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(timeout); s.connect(sock_path)
        s.sendall((json.dumps({"command":cmd})+"\n").encode())
        if not want_reply: s.close(); return None
        buf = b""
        while b"\n" not in buf:
            c = s.recv(4096)
            if not c: break
            buf += c
        s.close()
        return json.loads(buf.decode("utf-8","replace")) if buf.strip() else None
    except (OSError, ValueError):
        return None

def mpv_live(k):
    r = mpv_send(SOCKS[k], ["get_property","volume"], timeout=0.5)
    return bool(r and r.get("error") == "success")

def mpv_spawn(args):
    logf = open(AUDIO_LOG,"ab")
    subprocess.Popen(args, stdin=DN, stdout=DN, stderr=logf, start_new_session=True)
    logf.close()

def music_set(path_win):
    host = to_host(path_win)
    if not (os.path.isfile(host) or os.path.isdir(host)):
        bad("not found: %s" % path_win); return False
    if IS_WIN:
        mpv = find_tool("mpv",["mpv.exe"],[r"C:\Users\lenov\scoop\shims\mpv.exe"])
        if not mpv: bad("mpv.exe not found"); return False
        sh(["taskkill.exe","/F","/IM","mpv.exe"], timeout=10)
        spawn_win(to_host(mpv), ["--no-video","--really-quiet","--loop-playlist=inf",
                                 "--gapless-audio=yes",
                                 "--volume=%d" % CFG["volume"],
                                 "--af=afade=t=in:st=0:d=%s" % CFG["crossfade"], path_win])
        STATE["now_playing"] = path_win; return True
    mpv = shutil.which("mpv")
    if not mpv: bad("mpv missing in WSL"); return False

    watcher = ensure_np_watcher()
    ensure_smtc()
    ensure_relay()

    folder = os.path.isdir(host)
    step("%s → %s" % ("folder" if folder else "track", shorten(wbase(path_win),40)))
    old = next((k for k in ("a","b") if mpv_live(k)), None)
    new = "b" if old == "a" else "a"
    args = [mpv,"--no-video","--really-quiet","--loop-playlist=inf",
            "--gapless-audio=yes",
            "--ao=pulse",
            "--input-ipc-server=%s" % SOCKS[new],
            "--volume=0","--script=%s" % watcher, host]
    if folder and STATE.get("shuffle", CFG["shuffle"]): args.insert(1,"--shuffle")
    mpv_spawn(args)
    up = False
    for _ in range(40):
        if mpv_live(new): up = True; break
        time.sleep(0.05)
    if not up:
        subprocess.run(["pkill","-f",SOCKS[new]], timeout=5)
        bad("mpv didn't start — see rice_audio.log"); return False
    V,F,steps = CFG["volume"], CFG["crossfade"], 12
    v0 = V
    if old:
        r = mpv_send(SOCKS[old], ["get_property","volume"])
        if r and "data" in r: v0 = max(float(r["data"]),1.0)
    try:
        for i in range(1, steps+1):
            mpv_send(SOCKS[new], ["set_property","volume", round(V*i/steps,1)])
            if old:
                mpv_send(SOCKS[old], ["set_property","volume",
                                      round(max(0.0, v0*(1-i/steps)),1)])
            time.sleep(F/steps)
    finally:
        mpv_send(SOCKS[new], ["set_property","volume",V])
    if old:
        mpv_send(SOCKS[old], ["quit"], want_reply=False)
        ok("crossfaded over %.1fs ♪" % F)
    else:
        ok("faded in over %.1fs" % F)
    STATE["now_playing"] = path_win
    STATE["active_sock"] = new
    STATE["paused"] = False
    save_state(STATE); return True

def music_toggle():
    k = STATE.get("active_sock") or next((k for k in ("a","b") if mpv_live(k)), None)
    if not k or not mpv_live(k): warn("nothing playing."); return
    r = mpv_send(SOCKS[k], ["get_property","pause"])
    cur = bool(r.get("data")) if r else False
    mpv_send(SOCKS[k], ["set_property","pause", not cur])
    STATE["paused"] = not cur; save_state(STATE)
    ok("music %s." % ("paused" if STATE["paused"] else "resumed"))

def music_stop():
    if IS_WIN: sh(["taskkill.exe","/F","/IM","mpv.exe"], timeout=10)
    else:
        for k in ("a","b"):
            if mpv_live(k): mpv_send(SOCKS[k], ["quit"], want_reply=False)
    STATE["now_playing"] = None; STATE["active_sock"] = None
    STATE["paused"] = False; save_state(STATE); ok("music stopped.")

# ── mpv TCP RELAY ────────────────────────────────────────────────────────
def relay_main():
    import threading
    def handle(conn, sock_path):
        try:
            us = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            us.settimeout(2.0); us.connect(sock_path)
        except OSError:
            try: conn.close()
            except OSError: pass
            return
        pair = (conn, us)
        def pump(a,b):
            try:
                while True:
                    d = a.recv(4096)
                    if not d: break
                    b.sendall(d)
            except OSError: pass
            finally:
                for c in pair:
                    try: c.close()
                    except OSError: pass
        threading.Thread(target=pump, args=(conn,us), daemon=True).start()
        pump(us, conn)
    def serve(port, sock_path):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            srv.bind(("0.0.0.0", port)); srv.listen(4)
        except OSError as e:
            dbg("relay bind %d failed: %s" % (port,e)); return
        while True:
            try: conn, _ = srv.accept()
            except OSError: return
            threading.Thread(target=handle, args=(conn, sock_path), daemon=True).start()
    threads = []
    for port, sp in RELAY_PORTS.items():
        t = threading.Thread(target=serve, args=(port, sp), daemon=True)
        t.start(); threads.append(t)
    for t in threads: t.join()

def ensure_relay():
    try:
        s = socket.create_connection(("127.0.0.1", 6600), timeout=0.3)
        s.close(); return True
    except OSError: pass
    try:
        subprocess.Popen([sys.executable, os.path.abspath(__file__), "--relay"],
                         stdin=DN, stdout=DN, stderr=DN, start_new_session=True)
    except OSError as e:
        warn("relay spawn failed: %s" % e); return False
    time.sleep(0.4); return True

# ── SMTC BRIDGE (frozen — the working, stress-tested one) ────────────────
# Session lifecycle:
#  * mpv has a track playing        → session shown, Playing
#  * mpv track is paused            → session shown, Paused
#  * mpv track paused > 15s         → session Closed, YT/Spotify take over
#  * mpv stopped / np.json empty    → session Closed
#  * track change / resume          → session reopened
# CommandManager stays ON the whole time so buttons never get dropped.
# Playlist is built ONCE; we only update its DisplayProperties in place.
#
# Desync guard (fixes "theme swap breaks pause"):
#   Right after Activate() the WinRT MediaPlayer's PlaybackState lags
#   behind the Play()/Pause() call for a moment. During that window,
#   comparing st to _expected would look exactly like a user button
#   click and the bridge would send a spurious pause to mpv. We now
#   ignore state mismatches for ACTIVATE_GRACE_SECONDS after Activate.
#   We also revert SMTC if SendToMpv fails, and force a resync when a
#   pending action times out — so SMTC never drifts from np.json.
SMTC_CS = r"""
using System;
using System.IO;
using System.Net.Sockets;
using System.Text;
using System.Windows.Forms;
using Windows.Media;
using Windows.Media.Core;
using Windows.Media.Playback;

internal static class RiceSmtc
{
    private static string _np, _log, _last = "";
    private static MediaPlayer _player;
    private static SystemMediaTransportControls _smtc;
    private static MediaPlaybackList _list;
    private static string _lastTitle = null;
    private static int _lastIndex = 0;
    private static MediaPlaybackState _expected = MediaPlaybackState.Paused;
    private static string _pending = null;
    private static DateTime _pendingSince = DateTime.MinValue;
    private static bool _pendingTarget = false;
    private static DateTime _emptySince = DateTime.MinValue;
    private static DateTime _pausedSince = DateTime.MinValue;
    private static bool _idle = true;
    private static int _req = 0;
    private static DateTime _lastActivate = DateTime.MinValue;

    private const double PAUSE_YIELD_SECONDS      = 15.0;
    private const double EMPTY_IDLE_SECONDS       =  1.5;
    private const double ACTIVATE_GRACE_SECONDS   =  1.5;

    private static void Log(string m)
    {
        try
        {
            Console.WriteLine("smtc: " + m);
            File.AppendAllText(_log,
                DateTime.Now.ToString("HH:mm:ss") + " " + m + Environment.NewLine);
        }
        catch { }
    }

    [STAThread]
    private static int Main(string[] args)
    {
        _np = args.Length > 0 ? args[0] : @"C:\Users\lenov\rice\np.json";
        _log = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "smtc_bridge.log");
        Log("starting; np=" + _np);
        try
        {
            _player = new MediaPlayer();
            _player.Volume = 0.0;
            _player.AutoPlay = false;
            _player.CommandManager.IsEnabled = true;
            _smtc = _player.SystemMediaTransportControls;
            _smtc.IsEnabled = true;
            _smtc.IsPlayEnabled = true;
            _smtc.IsPauseEnabled = true;
            _smtc.IsNextEnabled = true;
            _smtc.IsPreviousEnabled = true;
            _smtc.DisplayUpdater.Type = MediaPlaybackType.Music;

            // Build the silent playlist ONCE — never reassign Source.
            string wav = MakeSilentWav();
            _list = new MediaPlaybackList();
            _list.AutoRepeatEnabled = true;
            for (int i = 0; i < 16; i++)
            {
                MediaPlaybackItem it = new MediaPlaybackItem(
                    MediaSource.CreateFromUri(new Uri(wav)));
                MediaItemDisplayProperties props = it.GetDisplayProperties();
                props.Type = MediaPlaybackType.Music;
                props.MusicProperties.Title = "";
                props.MusicProperties.Artist = "";
                it.ApplyDisplayProperties(props);
                _list.Items.Add(it);
            }
            _player.Source = _list;
            // Let the media engine settle, THEN read the real index.
            System.Threading.Thread.Sleep(200);
            _lastIndex = (int)_list.CurrentItemIndex;

            _smtc.PlaybackStatus = MediaPlaybackStatus.Closed;
            _idle = true;
            Log("player ready (idle, session closed)");

            Timer t = new Timer();
            t.Interval = 250;
            t.Tick += delegate { Poll(); };
            t.Start();
            Application.Run();
        }
        catch (Exception ex)
        {
            Log("FATAL " + ex.ToString());
            return 1;
        }
        return 0;
    }

    private static void UpdateDisplay(string title, string artist)
    {
        try
        {
            for (int i = 0; i < _list.Items.Count; i++)
            {
                MediaPlaybackItem it = _list.Items[i];
                MediaItemDisplayProperties props = it.GetDisplayProperties();
                props.Type = MediaPlaybackType.Music;
                props.MusicProperties.Title = title;
                props.MusicProperties.Artist = artist;
                it.ApplyDisplayProperties(props);
            }
            _smtc.DisplayUpdater.Type = MediaPlaybackType.Music;
            _smtc.DisplayUpdater.MusicProperties.Title = title;
            _smtc.DisplayUpdater.MusicProperties.Artist = artist;
            _smtc.DisplayUpdater.Update();
        }
        catch (Exception ex) { Log("display ERR " + ex.Message); }
    }

    private static void GoIdle(string why)
    {
        try { _player.Pause(); } catch { }
        try { _smtc.PlaybackStatus = MediaPlaybackStatus.Closed; } catch { }
        _idle = true;
        _lastTitle = null;
        _pending = null;
        _emptySince = DateTime.MinValue;
        _pausedSince = DateTime.MinValue;
        _expected = MediaPlaybackState.Paused;
        Log("idle - session closed (" + why + ")");
    }

    private static void Activate(string title, string artist, bool playing)
    {
        UpdateDisplay(title, artist);
        try
        {
            MediaPlaybackState st = _player.PlaybackSession.PlaybackState;
            if (playing && st != MediaPlaybackState.Playing) _player.Play();
            else if (!playing && st == MediaPlaybackState.Playing) _player.Pause();
        }
        catch { }
        _smtc.PlaybackStatus = playing
            ? MediaPlaybackStatus.Playing
            : MediaPlaybackStatus.Paused;
        _expected = playing ? MediaPlaybackState.Playing : MediaPlaybackState.Paused;
        _idle = false;
        _lastTitle = title;
        _pausedSince = playing ? DateTime.MinValue : DateTime.UtcNow;
        _lastActivate = DateTime.UtcNow;
        Log("active - session shown: " + title + " - " + artist);
    }

    private static void Poll()
    {
        try
        {
            string json = "";
            if (File.Exists(_np)) json = File.ReadAllText(_np);
            bool changed = (json != _last);
            if (changed) _last = json;
            string title = JGet(json, "title");
            string artist = JGet(json, "artist");
            bool npPlaying = JGet(json, "playing") == "true";
            if (changed)
                Log("np: " + title + " - " + artist +
                    " [" + (npPlaying ? "playing" : "paused") + "]");

            if (title == "")
            {
                if (_idle) return;
                if (_emptySince == DateTime.MinValue)
                {
                    _emptySince = DateTime.UtcNow;
                    return;
                }
                if ((DateTime.UtcNow - _emptySince).TotalSeconds
                    < EMPTY_IDLE_SECONDS) return;
                GoIdle("empty title");
                return;
            }
            _emptySince = DateTime.MinValue;

            if (_idle || title != _lastTitle)
            {
                Activate(title, artist, npPlaying);
                return;
            }

            if (!npPlaying)
            {
                if (_pausedSince == DateTime.MinValue)
                    _pausedSince = DateTime.UtcNow;
                if ((DateTime.UtcNow - _pausedSince).TotalSeconds
                    > PAUSE_YIELD_SECONDS)
                {
                    GoIdle("paused > " + PAUSE_YIELD_SECONDS + "s");
                    return;
                }
            }
            else
            {
                _pausedSince = DateTime.MinValue;
            }

            if (_pending != null)
            {
                if (npPlaying == _pendingTarget)
                {
                    Log("pending " + _pending + " applied");
                    _pending = null;
                }
                else if ((DateTime.UtcNow - _pendingSince).TotalSeconds > 3.0)
                {
                    Log("pending " + _pending + " timed out");
                    _pending = null;
                    // mpv never acked — snap SMTC to match reality.
                    MediaPlaybackStatus fix = npPlaying
                        ? MediaPlaybackStatus.Playing
                        : MediaPlaybackStatus.Paused;
                    try { _smtc.PlaybackStatus = fix; } catch { }
                    _expected = npPlaying ? MediaPlaybackState.Playing
                                          : MediaPlaybackState.Paused;
                    return;
                }
                else return;
            }

            MediaPlaybackState st = _player.PlaybackSession.PlaybackState;
            if (st != MediaPlaybackState.Playing && st != MediaPlaybackState.Paused)
                return;

            // Grace window after Activate: the MediaPlayer's own state
            // lags behind the Play()/Pause() call. During this window
            // st != _expected would look EXACTLY like a user click.
            // Don't fall for it — adopt whatever state the engine
            // reports and skip button detection.
            if ((DateTime.UtcNow - _lastActivate).TotalSeconds
                < ACTIVATE_GRACE_SECONDS)
            {
                _expected = st;
                return;
            }

            if (st != _expected)
            {
                if (st == MediaPlaybackState.Playing && !npPlaying)
                {
                    Log("clicked PLAY");
                    if (SendToMpv("play"))
                    {
                        _pending = "play"; _pendingTarget = true;
                        _pendingSince = DateTime.UtcNow;
                        _pausedSince = DateTime.MinValue;
                        _expected = st;
                    }
                    else
                    {
                        Log("play forward failed — reverting SMTC");
                        try { _smtc.PlaybackStatus = MediaPlaybackStatus.Paused; } catch { }
                        _expected = MediaPlaybackState.Paused;
                    }
                    return;
                }
                if (st == MediaPlaybackState.Paused && npPlaying)
                {
                    Log("clicked PAUSE");
                    if (SendToMpv("pause"))
                    {
                        _pending = "pause"; _pendingTarget = false;
                        _pendingSince = DateTime.UtcNow;
                        _pausedSince = DateTime.UtcNow;
                        _expected = st;
                    }
                    else
                    {
                        Log("pause forward failed — reverting SMTC");
                        try { _smtc.PlaybackStatus = MediaPlaybackStatus.Playing; } catch { }
                        _expected = MediaPlaybackState.Playing;
                    }
                    return;
                }
                _expected = st;
            }

            int idx = (int)_list.CurrentItemIndex;
            if (idx != _lastIndex)
            {
                int n = _list.Items.Count;
                int d = (idx - _lastIndex + n) % n;
                if (d == 1) { Log("clicked NEXT"); SendToMpv("next"); }
                else if (d == n - 1) { Log("clicked PREV"); SendToMpv("prev"); }
                _lastIndex = idx; return;
            }
        }
        catch (Exception ex) { Log("poll ERR " + ex.Message); }
    }

    private static bool SendToMpv(string action)
    {
        _req++;
        string cmdPart;
        switch (action)
        {
            case "play":  cmdPart = "\"set_property\",\"pause\",false"; break;
            case "pause": cmdPart = "\"set_property\",\"pause\",true";  break;
            case "next":  cmdPart = "\"playlist-next\"";                break;
            case "prev":  cmdPart = "\"playlist-prev\"";                break;
            default: return false;
        }
        string line = "{\"command\":[" + cmdPart + "],\"request_id\":" + _req + "}\n";
        byte[] bytes = Encoding.UTF8.GetBytes(line);
        if (TryPort(6600, bytes) || TryPort(6601, bytes))
        {
            Log("forwarded " + action);
            return true;
        }
        Log("no-mpv " + action);
        return false;
    }

    private static bool TryPort(int port, byte[] bytes)
    {
        try
        {
            using (TcpClient c = new TcpClient())
            {
                c.Connect("127.0.0.1", port);
                c.ReceiveTimeout = 600;
                c.SendTimeout = 600;
                NetworkStream s = c.GetStream();
                s.Write(bytes, 0, bytes.Length); s.Flush();
                byte[] buf = new byte[2048];
                StringBuilder sb = new StringBuilder();
                DateTime start = DateTime.UtcNow;
                while ((DateTime.UtcNow - start).TotalMilliseconds < 700)
                {
                    try
                    {
                        int n = s.Read(buf, 0, buf.Length);
                        if (n <= 0) break;
                        sb.Append(Encoding.UTF8.GetString(buf, 0, n));
                        if (sb.ToString().Contains("\n")) break;
                    }
                    catch (IOException) { break; }
                }
                return sb.ToString().Contains("\"error\":\"success\"");
            }
        }
        catch { return false; }
    }

    private static string MakeSilentWav()
    {
        string p = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "silence.wav");
        if (File.Exists(p)) return p;
        int rate = 8000, secs = 600, data = rate * secs * 2;
        using (FileStream fs = new FileStream(p, FileMode.Create))
        using (BinaryWriter w = new BinaryWriter(fs))
        {
            w.Write("RIFF".ToCharArray()); w.Write(36 + data);
            w.Write("WAVE".ToCharArray()); w.Write("fmt ".ToCharArray());
            w.Write(16); w.Write((short)1); w.Write((short)1);
            w.Write(rate); w.Write(rate * 2); w.Write((short)2); w.Write((short)16);
            w.Write("data".ToCharArray()); w.Write(data); w.Write(new byte[data]);
        }
        return p;
    }

    private static string JGet(string json, string key)
    {
        try
        {
            int i = json.IndexOf("\"" + key + "\":");
            if (i < 0) return "";
            i = json.IndexOf('"', i + key.Length + 3);
            if (i < 0) return "";
            int j = json.IndexOf('"', i + 1);
            if (j < 0) return "";
            return json.Substring(i + 1, j - i - 1);
        }
        catch { return ""; }
    }
}
"""

def ensure_smtc(start=True):
    """
    Idempotent SMTC bridge manager.

    Fixes the previous behaviour where a code change would kill the running
    bridge even when the caller asked NOT to start it (e.g. --doctor), leaving
    the YASB music link dead. Now:
      * We only kill the live bridge if we're actually going to restart it.
      * We always (re)compile if the .cs changed and we need the exe.
      * If start=True and it's not running, we launch it and then verify it
        survived startup (a real check, not a hopeful 'running.' line).
    """
    ensure_np_watcher()
    changed = write_asset("smtc_bridge.cs", SMTC_CS)
    exe = os.path.join(HERE, "smtc_bridge.exe")
    running = proc_running("smtc_bridge.exe")

    if changed:
        if running and start:
            step("restarting SMTC bridge (code updated)…")
            sh(["taskkill.exe", "/F", "/IM", "smtc_bridge.exe"], timeout=10)
            time.sleep(0.5)
            running = False
        if os.path.isfile(exe) and (start or not running):
            try: os.remove(exe)
            except OSError: pass

    if not os.path.isfile(exe):
        refs = []
        for n in ("System", "System.Core", "System.Windows.Forms", "System.Runtime",
                  "System.Runtime.WindowsRuntime",
                  "System.Runtime.InteropServices.WindowsRuntime"):
            p = net_ref(n)
            if p: refs.append(p)
            else: warn("%s.dll not found" % n)
        for n in ("System.Threading.Tasks", "System.ObjectModel"):
            p = net_ref(n)
            if p: refs.append(p)
        refs += find_winmds()
        step("compiling smtc_bridge.exe…")
        if not compile_exe("smtc_bridge.cs", "smtc_bridge.exe", refs):
            warn("SMTC bridge unavailable.")
            return
        ok("smtc_bridge.exe compiled")

    if start and not running:
        try:
            spawn_win(to_host(exe), [to_win(NP_JSON)])
            time.sleep(1.2)
            if proc_running("smtc_bridge.exe"):
                ok("SMTC bridge running.")
            else:
                warn("SMTC bridge spawned but exited — see smtc_bridge.log")
        except Exception as e:
            warn("bridge launch failed: %s" % e)

def fix_music_link():
    step("restarting the YASB music link…")
    sh(["taskkill.exe","/F","/IM","smtc_bridge.exe"], timeout=10)
    time.sleep(0.5)
    exe = os.path.join(HERE, "smtc_bridge.exe")
    if os.path.isfile(exe):
        try: os.remove(exe)
        except OSError: pass
    ensure_smtc()
    ensure_relay()
    ok("bridge exe: %s" % ("✓" if os.path.isfile(exe) else "✗"))
    ok("bridge running: %s" % ("✓" if proc_running("smtc_bridge.exe") else "✗"))
    try:
        s = socket.create_connection(("127.0.0.1",6600), timeout=0.3)
        s.close(); ok("relay: ✓")
    except OSError:
        bad("relay: ✗")
    ok("play a track — the bar should pick it up within a second.")

def smtc_test():
    ensure_smtc(start=False)
    exe = os.path.join(HERE,"smtc_bridge.exe")
    if not os.path.isfile(exe): bad("bridge not compiled"); return
    if proc_running("smtc_bridge.exe"):
        sh(["taskkill.exe","/F","/IM","smtc_bridge.exe"], timeout=10); time.sleep(0.5)
    logf = os.path.join(HERE,"smtc_bridge.log")
    if os.path.isfile(logf):
        try: os.remove(logf)
        except OSError: pass
    backup = rb(NP_JSON) if os.path.isfile(NP_JSON) else None
    atomic_write(NP_JSON, b'{"title":"SMTC TEST","artist":"rice","playing":"true"}')
    print("  bridge running ~8s")
    try: spawn_win(to_host(exe), [to_win(NP_JSON)])
    except Exception as e:
        bad("could not launch: %s" % e)
        if backup: atomic_write(NP_JSON, backup)
        return
    time.sleep(8)
    sh(["taskkill.exe","/F","/IM","smtc_bridge.exe"], timeout=10); time.sleep(0.5)
    if backup: atomic_write(NP_JSON, backup)
    if os.path.isfile(logf):
        print("  smtc_bridge.log:")
        for l in rt(logf).splitlines(): print("    "+l)

# ── YASB (frozen) ────────────────────────────────────────────────────────
def yasb_scope():
    out=[]
    for c in CFG["yasb_styles"]:
        h = to_host(c)
        if os.path.isfile(h): out.append((_tag(c),c,h))
    return out

def accent_set(): return {norm_hex(a) for a in STATE.get("accent_hexes",[])}

def accent_count(text):
    n=0; accs=accent_set()
    for m in HEX_RE.finditer(text):
        tok=m.group(0)[1:]
        base=(tok[0]*2+tok[1]*2+tok[2]*2) if len(tok)==3 else tok[:6]
        if base.lower() in accs: n+=1
    return n

def yasb_writable():
    try:
        t=os.path.join(to_host(CFG["yasb_dir"]),".rice-write-test")
        open(t,"w").close(); os.remove(t); return True
    except OSError: return False

def fix_yasb_perms():
    ps = powershell()
    if not ps: bad("powershell not found"); return False
    step("requesting write access…")
    cmd = ("Start-Process icacls -ArgumentList '%s','/grant','%s:(OI)(CI)M' -Verb RunAs -Wait"
           % (CFG["yasb_dir"], CFG["win_user"]))
    sh([ps,"-NoProfile","-Command",cmd], timeout=180)
    if yasb_writable(): ok("YASB folder writable."); return True
    bad('still not writable — run icacls manually'); return False

def yasb_baseline(tag): return os.path.join(YASB_DATA,"baseline",tag+".orig")
def yasb_variant(theme,tag): return os.path.join(YASB_DATA,"themes",theme,tag)

def capture_baseline(force=False):
    scope = yasb_scope()
    if not scope: bad("no styles.css found"); return False
    os.makedirs(os.path.join(YASB_DATA,"baseline"), exist_ok=True)
    n=0
    for tag,win,host in scope:
        dst = yasb_baseline(tag)
        if force or not os.path.isfile(dst):
            shutil.copyfile(host,dst); n+=1
    if n: ok("baseline captured (%d)" % n)
    return True

def norm_hex(h):
    h = h.strip().lstrip("#").lower()
    if len(h)==3: h = h[0]*2+h[1]*2+h[2]*2
    return h[:6]

def theme_map(theme):
    pal = THEME_PALETTES[theme]
    return {src.lstrip("#").lower(): pal[role].lstrip("#").lower()
            for src,role in ROLE_MAP.items()}

def replace_hex(text, pairs):
    def sub(m):
        tok = m.group(0)[1:]
        if len(tok)==3: base,alpha = tok[0]*2+tok[1]*2+tok[2]*2,""
        elif len(tok)==8: base,alpha = tok[:6],tok[6:]
        else: base,alpha = tok,""
        t = pairs.get(base.lower())
        return "#"+t+alpha if t else "#"+tok
    return HEX_RE.sub(sub, text)

def generate_variants():
    scope = yasb_scope()
    if not scope: return False
    for theme in THEME_PALETTES:
        pairs = theme_map(theme)
        d = os.path.join(YASB_DATA,"themes",theme); os.makedirs(d, exist_ok=True)
        for tag,win,host in scope:
            src = yasb_baseline(tag)
            if not os.path.isfile(src): src = host
            atomic_write(yasb_variant(theme,tag),
                         replace_hex(rt(src),pairs).encode("utf-8","surrogateescape"))
    return True

def apply_yasb(theme_key):
    tgt = THEME_PALETTES[theme_key]; set_palette(tgt["accent"])
    step("YASB → %s theme" % theme_key)
    scope = yasb_scope()
    if not scope: bad("no styles.css"); return False
    if not STATE.get("accent_hexes"): warn("accent not calibrated"); return False
    capture_baseline(); generate_variants()
    hits = 0
    for tag,win,host in scope:
        v = yasb_variant(theme_key,tag)
        if not os.path.isfile(v): warn("no variant for %s" % win); continue
        base = yasb_baseline(tag)
        n = accent_count(rt(base if os.path.isfile(base) else host))
        try:
            with open(host,"wb") as f: f.write(rb(v))
        except PermissionError:
            warn("cannot write %s" % win); continue
        hits += n
        if not QUIET: print("    %s → %d hex tokens" % (shorten(win,58), n))
    if hits == 0: warn("no accent hexes matched")
    else: ok("styles recolored (%d tokens)." % hits)
    reload_yasb()
    STATE["yasb_theme"] = theme_key; save_state(STATE); return True

def reload_yasb():
    mode = STATE.get("yasb_reload","live")
    if mode == "live":
        time.sleep(1.2); ok("bar hot-reloaded."); return True
    exe = find_tool("yasb_exe",["YASB.exe","yasb.exe"],CAND["yasb_exe"])
    if not exe: warn("YASB.exe not found"); return False
    if mode == "flag":
        r = sh([to_host(exe),"--restart"], timeout=12)
        if r and r.returncode == 0: ok("restarted."); return True
    sh(["taskkill.exe","/F","/IM",wbase(exe)], timeout=12)
    time.sleep(0.8)
    spawn_win(to_host(exe), cwd=os.path.dirname(to_host(exe)))
    ok("YASB relaunched."); return True

def yasb_scan():
    print("\n  YASB recon")
    for c in CFG["yasb_styles"]:
        h = to_host(c)
        if os.path.isfile(h):
            print("    [+] %-58s" % shorten(c,58))
            print("        accent matches: %d" % accent_count(rt(h)))
        else: print("    [ ] %-58s (missing)" % shorten(c,58))

def yasb_calibrate():
    scope = yasb_scope()
    if not scope: bad("no styles.css found"); return False
    capture_baseline(); agg = {}
    for tag,win,host in scope:
        src = yasb_baseline(tag)
        for t in HEX_RE.findall(rt(src if os.path.isfile(src) else host)):
            agg[t.lower()] = agg.get(t.lower(),0)+1
    if not agg: bad("no hex colors"); return False
    ordered = [h for h,_ in sorted(agg.items(), key=lambda kv:-kv[1])]
    print("\n  hex colors:\n")
    for i,h in enumerate(ordered[:20],1):
        star = "  ★" if h in accent_set() else ""
        print("    %2d) %s ×%d%s" % (i,h,agg[h],star))
    sel = input("\n  which hex(es) are the accent? ").strip()
    picks = []
    for p in sel.replace(","," ").split():
        if re.fullmatch(r"#?[0-9a-fA-F]{3,8}", p): picks.append(norm_hex(p))
        elif p.isdigit() and 0 < int(p) <= len(ordered): picks.append(norm_hex(ordered[int(p)-1]))
    picks = [p for i,p in enumerate(picks) if p and p not in picks[:i]]
    if not picks: warn("cancelled."); return False
    STATE["accent_hexes"] = ["#"+p for p in picks]
    save_state(STATE)
    if generate_variants(): ok("variants regenerated.")
    return True

# ── WINDOWS TERMINAL (frozen) ────────────────────────────────────────────
def wt_settings():
    for c in CFG["wt_settings"]:
        if os.path.isfile(to_host(c)): return c
    return None

def _skip_ws(s,i):
    n = len(s)
    while i < n:
        if s[i] in " \t\r\n": i+=1
        elif s[i:i+2] == "//":
            j = s.find("\n",i); i = n if j<0 else j
        elif s[i:i+2] == "/*":
            j = s.find("*/",i+2); i = n if j<0 else j+2
        else: break
    return i

def _match_brace(s,i):
    depth, instr, esc, n = 0, False, False, len(s)
    while i < n:
        c = s[i]
        if instr:
            if esc: esc = False
            elif c == "\\": esc = True
            elif c == '"': instr = False
        elif c == '"': instr = True
        elif c == "/" and i+1 < n and s[i+1] == "/":
            j = s.find("\n",i); i = (n-1) if j<0 else j
        elif c == "/" and i+1 < n and s[i+1] == "*":
            j = s.find("*/",i+2)
            if j<0: return -1
            i = j+1
        elif c == "{": depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0: return i
        i += 1
    return -1

def find_wt_profile(text, want):
    m = re.search(r'"profiles"\s*:\s*', text)
    if not m: return None, []
    i = _skip_ws(text, m.end())
    if i >= len(text): return None, []
    if text[i] == "{":
        m2 = re.search(r'"list"\s*:\s*', text[i:])
        if not m2: return None, []
        i = _skip_ws(text, i + m2.end())
    if i >= len(text) or text[i] != "[": return None, []
    names, j = [], _skip_ws(text, i+1)
    while j < len(text) and text[j] != "]":
        if text[j] != "{": break
        end = _match_brace(text, j)
        if end < 0: break
        obj = text[j:end+1]
        nm = re.search(r'"name"\s*:\s*"([^"]*)"', obj)
        if nm:
            names.append(nm.group(1))
            if nm.group(1) == want: return (j, end+1, obj), names
        j = _skip_ws(text, end+1)
        if j < len(text) and text[j] == ",":
            j = _skip_ws(text, j+1)
    return None, names

def _key_value_re(key):
    return re.compile(
        r'("' + re.escape(key) + r'"\s*:\s*)'
        r'(?:"(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?|true|false|null)')

def json_set_key(obj, key, val):
    pat = _key_value_re(key)
    if pat.search(obj):
        return pat.sub(lambda m: m.group(1)+val, obj, count=1)
    if obj.strip() == "{}":
        return "{" + '"%s": %s' % (key,val) + "}"
    m = re.match(r"\{(\s*)", obj)
    ws = m.group(1) if (m and m.group(1)) else ""
    rest = obj[m.end():] if m else obj[1:]
    if not ws: return "{" + '"%s": %s, ' % (key,val) + rest
    return "{" + ws + '"%s": %s,' % (key,val) + ws + rest

def wt_apply(scheme, opacity):
    step("terminal → scheme '%s', opacity %d%%" % (scheme, opacity))
    winp = wt_settings()
    if not winp: bad("settings.json not found"); return False
    host = to_host(winp)
    raw = rb(host)
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8","surrogateescape")
    hit, names = find_wt_profile(text, CFG["wt_profile"])
    if not hit:
        bad('profile "%s" not found' % CFG["wt_profile"])
        if names: print("    available: %s" % ", ".join(names))
        return False
    a, b, obj = hit
    obj = json_set_key(obj, "colorScheme", '"%s"' % scheme)
    obj = json_set_key(obj, "opacity", str(opacity))
    obj = json_set_key(obj, "useAcrylic", "false")
    text2 = text[:a] + obj + text[b:]
    try:
        if not os.path.isfile(host + ".rice-orig"):
            shutil.copyfile(host, host + ".rice-orig")
        shutil.copyfile(host, host + ".rice-bak")
    except OSError as e:
        warn("backup failed (%s)" % e); return False
    atomic_write(host, (b"\xef\xbb\xbf" if bom else b"")
                 + text2.encode("utf-8","surrogateescape"))
    ok("settings.json patched (fonts/cursor untouched).")
    STATE["wt_scheme"], STATE["wt_opacity"] = scheme, opacity
    save_state(STATE); return True

# ── folder browsers ──────────────────────────────────────────────────────
def list_dir(win_dir, exts):
    host = to_host(win_dir)
    if not os.path.isdir(host): return []
    out=[]
    for fn in sorted(os.listdir(host), key=str.lower):
        if os.path.splitext(fn)[1].lower() in exts:
            out.append(ntpath.join(win_dir, fn))
    return out

def paged_picker(title, files, state_key, on_pick, head_items=None, footer=""):
    page, per = 0, 9
    while True:
        current = STATE.get(state_key) if state_key else None
        pages = max(1, (len(files)+per-1)//per)
        chunk = files[page*per : page*per+per]
        items = list(head_items or [])
        for i,f in enumerate(chunk):
            mark = "● " if (current and
                            ntpath.normcase(f) == ntpath.normcase(current)) else "  "
            items.append({"key": str(i+1),
                          "label": "%s%s" % (mark, shorten(wbase(f),48)),
                          "fn": (lambda ff=f: on_pick(ff))})
        if pages > 1:
            items.append({"key":"n",
                          "label":"next page (%d/%d) →" % (page+1,pages),
                          "fn":"next"})
            items.append({"key":"v","label":"← prev page","fn":"prev"})
        items.append({"key":"b","label":"← back","back":True,"fn":None})
        it = ask_menu("%s · %d items · page %d/%d"
                      % (title,len(files),page+1,pages), items, footer)
        if it is None or it.get("back"): return
        if it["fn"] == "next": page = (page+1)%pages; continue
        if it["fn"] == "prev": page = (page-1)%pages; continue
        try: it["fn"]()
        except KeyboardInterrupt: raise
        except Exception as e:
            bad("%s: %s" % (type(e).__name__, e)); dbg(traceback.format_exc())
        if INTERACTIVE: pause()

def wallpaper_menu():
    files = list_dir(CFG["wallpaper_dir"], IMG_EXT)
    if not files: bad("no images in %s" % CFG["wallpaper_dir"]); return
    if not _wide_enough():
        paged_picker("wallpaper", files, "wallpaper", set_wallpaper,
                     footer="↑/↓+Enter · 1-9 pick · n/v pages · ● = current")
        return
    wallpaper_gallery()

def toggle_shuffle():
    STATE["shuffle"] = not STATE.get("shuffle", CFG["shuffle"])
    save_state(STATE)
    ok("shuffle %s." % ("ON" if STATE["shuffle"] else "OFF"))

# ── music player UI ──────────────────────────────────────────────────────
def music_menu():
    files = list_dir(CFG["music_dir"], AUD_EXT)
    if not files: bad("no audio in %s" % CFG["music_dir"]); return
    page, per = 0, 8
    while True:
        t, playing = np_now()
        if t:
            hdr = ("  " + fg(PALHEX) + "♪ " + shorten(t, 44) + RST + DIM +
                   ("  · playing" if playing else "  · paused") + RST + "\n" +
                   "  " + DIM + "─"*46 + RST + "\n")
        else:
            hdr = "  " + DIM + "silence" + RST + "\n" + \
                  "  " + DIM + "─"*46 + RST + "\n"
        pages = max(1, (len(files)+per-1)//per)
        chunk = files[page*per : page*per+per]
        items = [
            {"key":"a","label":"▶  play whole folder (%d tracks)" % len(files),
             "fn": lambda: music_set(CFG["music_dir"])},
            {"key":"s","label":"shuffle: %s" %
             ("on" if STATE.get("shuffle", CFG["shuffle"]) else "off"),
             "fn": toggle_shuffle},
            {"key":"x","label":"■  stop","fn": music_stop},
            {"key":"_","label":" ","fn":None,"skip":True},
        ]
        for i,f in enumerate(chunk):
            cur = STATE.get("now_playing") and \
                  ntpath.normcase(f) == ntpath.normcase(STATE["now_playing"])
            name = os.path.splitext(wbase(f))[0]
            items.append({"key": str(i+1),
                          "label": "%s%02d  %s" % ("♪ " if cur else "  ",
                                                   i+1, shorten(name,44)),
                          "fn": (lambda ff=f: music_set(ff)),
                          "cur": cur})
        if pages > 1:
            items.append({"key":"n","label":"next page (%d/%d) →" % (page+1,pages),
                          "fn":"next"})
            items.append({"key":"v","label":"← prev page","fn":"prev"})
        items.append({"key":"b","label":"← back","back":True,"fn":None})
        it = ask_menu("music · %d tracks · page %d/%d"
                      % (len(files),page+1,pages), items,
                      footer="↑/↓ · enter play · 1-8 · a all · s shuffle · "
                             "p pause · n/v pages", header=hdr)
        if it is None or it.get("back"): return
        if it["fn"] == "next": page = (page+1)%pages; continue
        if it["fn"] == "prev": page = (page-1)%pages; continue
        try:
            if it["fn"]: it["fn"]()
        except KeyboardInterrupt: raise
        except Exception as e:
            bad("%s: %s" % (type(e).__name__, e)); dbg(traceback.format_exc())
        if INTERACTIVE: pause()

# ── submenus + settings ──────────────────────────────────────────────────
def bar_menu():
    items = [{"key":{"amber":"a","pink":"p","blue":"u"}[t],
              "label":"%-6s accent %s" % (t, THEME_PALETTES[t]["accent"]),
              "fn": (lambda tt=t: apply_yasb(tt))} for t in THEME_PALETTES]
    items += [{"key":"c","label":"calibrate accent…","fn":yasb_calibrate},
              {"key":"r","label":"re-capture baseline",
               "fn": lambda: capture_baseline(True)},
              {"key":"b","label":"← back","back":True,"fn":None}]
    submenu("status bar", items)

def term_menu():
    items = [{"key":k,
              "label":"%s · %s @ %d%%" % (p["name"],p["wt_scheme"],p["wt_opacity"]),
              "fn": (lambda pp=p: wt_apply(pp["wt_scheme"],pp["wt_opacity"]))}
             for k,p in PRESETS.items()]
    items.append({"key":"b","label":"← back","back":True,"fn":None})
    submenu("terminal scheme", items)

def settings_menu():
    items = [
        {"key":"d","label":"doctor — full self-check","fn":doctor},
        {"key":"f","label":"fix music link (restart bridge + relay)",
         "fn": fix_music_link},
        {"key":"c","label":"calibrate YASB accent","fn":yasb_calibrate},
        {"key":"b","label":"status bar color only","fn":bar_menu},
        {"key":"t","label":"terminal scheme only","fn":term_menu},
        {"key":"r","label":"re-capture YASB baseline",
         "fn": lambda: capture_baseline(True)},
        {"key":"s","label":"shuffle: %s" %
         ("on" if STATE.get("shuffle", CFG["shuffle"]) else "off"),
         "fn": toggle_shuffle},
        {"key":"x","label":"stop music","fn": music_stop},
        {"key":"q","label":"← back","back":True,"fn":None},
    ]
    submenu("settings", items)

def submenu(title, items, footer=""):
    while True:
        it = ask_menu(title, items, footer)
        if it is None or it.get("back"): return
        try:
            if it["fn"]: it["fn"]()
        except KeyboardInterrupt: raise
        except Exception as e:
            bad("%s: %s" % (type(e).__name__, e)); dbg(traceback.format_exc())
        if INTERACTIVE: pause()

# ── presets (threaded cinema mode — frozen) ──────────────────────────────
def apply_preset(key):
    global QUIET
    if key not in PRESETS: bad("no preset %r" % key); return
    p = PRESETS[key]
    set_palette(p["hex"]); clear()
    print("  applying %s %s …" % (p["emoji"], p["name"]))
    print("  " + DIM + "bar · wallpaper · music · terminal — all at once" + RST)
    QUIET = True
    results = {}
    def run(name, fn):
        try:
            results[name] = bool(fn())
        except Exception as e:
            results[name] = False
            dbg("%s: %s" % (name, traceback.format_exc()))
            bad("%s failed: %s" % (name, e))
    jobs = [("bar",   lambda: apply_yasb(p["yasb"])),
            ("wall",  lambda: set_wallpaper(p["wp"])),
            ("music", lambda: music_set(p["music"])),
            ("term",  lambda: wt_apply(p["wt_scheme"], p["wt_opacity"]))]
    ts = [threading.Thread(target=run, args=j) for j in jobs]
    for t in ts: t.start()
    for t in ts: t.join()
    QUIET = False
    STATE["theme_key"] = key
    save_state(STATE)
    good = sum(1 for v in results.values() if v)
    print()
    if results and good == len(results):
        ok("theme applied — colors flipped, wallpaper dissolved, audio blended")
    else:
        warn("%d/%d components ok: %s" % (good, len(results), results))
    if INTERACTIVE: pause()

# ── doctor ───────────────────────────────────────────────────────────────
def doctor():
    clear()
    print("  " + BOLD + fg(PALHEX) + "SYSTEM SELF-CHECK" + RST + "\n")
    rows = []
    def chk(name, okv, hint=""):
        rows.append((name, bool(okv), str(hint)))
    chk("runtime", True, "WSL2" if IS_WSL else "win")
    chk("csc.exe (helper compiler)", find_csc())
    chk("ffmpeg (gallery previews)", find_ffmpeg())
    tok, tmsg = test_ffmpeg_thumb()
    chk("ffmpeg thumb test", tok, tmsg)
    if IS_WSL:
        chk("WSLg audio", os.path.isdir("/mnt/wslg"))
        chk("mpv (WSL)", shutil.which("mpv"))
    ensure_wall_assets()
    chk("rice_wall.exe (overlay fade)",
        os.path.isfile(os.path.join(HERE,"rice_wall.exe")))
    chk("current wallpaper", STATE.get("wallpaper") or query_wallpaper() or "")
    for k,p in PRESETS.items():
        chk("preset %s wp" % k, os.path.isfile(to_host(p["wp"])), wbase(p["wp"]))
        chk("preset %s music" % k, os.path.isfile(to_host(p["music"])),
            shorten(wbase(p["music"]),40))
    chk("wallpaper folder", os.path.isdir(to_host(CFG["wallpaper_dir"])),
        "%d images" % len(list_dir(CFG["wallpaper_dir"], IMG_EXT)))
    chk("music folder", os.path.isdir(to_host(CFG["music_dir"])),
        "%d tracks" % len(list_dir(CFG["music_dir"], AUD_EXT)))
    try:
        s = socket.create_connection(("127.0.0.1",6600), timeout=0.3)
        s.close(); up = True
    except OSError: up = False
    chk("mpv TCP relay", up, "spawns with music")
    # start=True so --doctor self-heals a dead bridge (previously the
    # doctor would kill+not-respawn it and report "bridge running ✗").
    ensure_smtc(start=True)
    chk("smtc_bridge.exe", os.path.isfile(os.path.join(HERE,"smtc_bridge.exe")))
    chk("bridge running", proc_running("smtc_bridge.exe"))
    if os.path.isfile(NP_JSON):
        age = int(time.time() - os.path.getmtime(NP_JSON))
        chk("np.json (mpv watcher)", True, "age %ds" % age)
    logf = os.path.join(HERE,"smtc_bridge.log")
    if os.path.isfile(logf):
        tail = [l for l in rt(logf).splitlines() if l.strip()][-1:]
        chk("bridge log", True, tail[0][:60] if tail else "")
    scope = yasb_scope()
    chk("YASB styles", scope, "%d found" % len(scope))
    chk("YASB running", proc_running("YASB.exe"))
    winp = wt_settings()
    chk("WT settings.json", winp)
    if winp:
        text = rt(to_host(winp))
        for k,p in PRESETS.items():
            chk('scheme "%s"' % p["wt_scheme"], '"%s"' % p["wt_scheme"] in text)
        hit, names = find_wt_profile(text, CFG["wt_profile"])
        chk('WT profile "%s"' % CFG["wt_profile"], hit,
            ", ".join(names)[:48] if names else "")
    for name,okv,hint in rows:
        icon = "✓" if okv else "✗"; col = "\x1b[32m" if okv else "\x1b[31m"
        print("  %s%s%s %-28s %s" % (col,icon,RST,name,DIM+hint+RST))
    print(); save_state(STATE)

# ── main menu + CLI ──────────────────────────────────────────────────────
def main_menu():
    items = [
        {"key":"1","label":"themes",    "fn": themes_menu},
        {"key":"2","label":"wallpaper", "fn": wallpaper_menu},
        {"key":"3","label":"music",     "fn": music_menu},
        {"key":"4","label":"settings",  "fn": settings_menu},
    ]
    footer = "↑/↓ move · enter run · 1-4 jump · p pause · q quit"
    threading.Thread(target=ensure_relay, daemon=True).start()
    while True:
        it = ask_menu("", items, footer, header=logo_header())
        if it is None: return
        try: it["fn"]()
        except KeyboardInterrupt: raise
        except Exception as e:
            bad("%s: %s" % (type(e).__name__, e)); dbg(traceback.format_exc())

def resolve_asset(arg, field):
    if arg in PRESETS: return PRESETS[arg][field]
    return to_win(arg) if arg.startswith("/") else arg

def main():
    ap = argparse.ArgumentParser(
        description="OUTLAWSYL rice orchestrator — no args = menu")
    ap.add_argument("--apply", metavar="N")
    ap.add_argument("--wall", metavar="N|PATH")
    ap.add_argument("--music", metavar="N|PATH|FOLDER|stop")
    ap.add_argument("--bar", choices=["amber","pink","blue"])
    ap.add_argument("--term", metavar="N")
    ap.add_argument("--pause", action="store_true")
    ap.add_argument("--stop-music", action="store_true")
    ap.add_argument("--doctor", action="store_true")
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--recapture", action="store_true")
    ap.add_argument("--fix-yasb", action="store_true")
    ap.add_argument("--fix-music", action="store_true")
    ap.add_argument("--smtc-test", action="store_true")
    ap.add_argument("--yasb-reload", choices=["live","flag","hard"], metavar="MODE")
    ap.add_argument("--relay", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args.relay:
        relay_main(); return

    tk = STATE.get("theme_key")
    if tk in PRESETS: set_palette(PRESETS[tk]["hex"])

    try:
        if args.yasb_reload:
            STATE["yasb_reload"] = args.yasb_reload; save_state(STATE)
            ok("yasb_reload → %s" % args.yasb_reload)
        elif args.fix_music: fix_music_link()
        elif args.smtc_test: smtc_test()
        elif args.fix_yasb: fix_yasb_perms()
        elif args.doctor: doctor()
        elif args.scan:
            doctor(); yasb_scan()
        elif args.calibrate: yasb_calibrate()
        elif args.recapture: capture_baseline(True)
        elif args.apply: apply_preset(args.apply)
        elif args.wall: set_wallpaper(resolve_asset(args.wall, "wp"))
        elif args.music:
            if args.music == "stop": music_stop()
            else: music_set(resolve_asset(args.music, "music"))
        elif args.bar: apply_yasb(args.bar)
        elif args.term:
            if args.term in PRESETS:
                p = PRESETS[args.term]
                wt_apply(p["wt_scheme"], p["wt_opacity"])
            else: bad("--term takes a preset number (1|2|3)")
        elif args.pause: music_toggle()
        elif args.stop_music: music_stop()
        else: main_menu()
    finally:
        save_state(STATE)
    print("  %s bye~" % DIM)

if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except KeyboardInterrupt:
        print("\n  " + DIM + "bye~" + RST)
    except Exception:
        dbg(traceback.format_exc())
        print(" ! unexpected error — details in rice_debug.log")
        raise