import os
import time
import json
import platform
from dataclasses import dataclass, asdict
from typing import List, Optional, Tuple
import subprocess

import pyautogui
from pynput import mouse, keyboard
from PIL import Image, ImageDraw, ImageFont
from jinja2 import Template

# Opcional: título da janela ativa (funciona bem no Windows; no mac pode variar)
try:
    import pygetwindow as gw
except Exception:
    gw = None

pyautogui.FAILSAFE = False

OUTPUT_DIR = time.strftime("tango_%Y-%m-%d_%H-%M-%S")
IMAGES_DIR = os.path.join(OUTPUT_DIR, "steps")
os.makedirs(IMAGES_DIR, exist_ok=True)

START_PAUSE_KEY = keyboard.Key.f8   # alterna gravar/pausar
FINISH_KEY = keyboard.Key.f9        # finaliza e gera

# Ajustes
CLICK_DEBOUNCE_SECONDS = 0.25       # evita registrar cliques em excesso
TYPE_IDLE_FLUSH_SECONDS = 1.2       # se ficar X segundos sem digitar, vira um passo
MAX_TYPED_PREVIEW = 120            # limita o texto exibido no passo

HTML_FILE = os.path.join(OUTPUT_DIR, "tutorial.html")
MD_FILE = os.path.join(OUTPUT_DIR, "tutorial.md")
JSON_FILE = os.path.join(OUTPUT_DIR, "steps.json")


@dataclass
class Step:
    number: int
    kind: str  # click | scroll | type | hotkey
    timestamp: float
    window_title: str
    description: str
    screenshot: Optional[str] = None
    x: Optional[int] = None
    y: Optional[int] = None
    button: Optional[str] = None
    scroll_dx: Optional[int] = None
    scroll_dy: Optional[int] = None
    typed_text: Optional[str] = None


def get_active_window_title() -> str:
    if gw is None:
        return ""
    try:
        w = gw.getActiveWindow()
        if w and getattr(w, "title", None):
            return w.title.strip()
    except Exception:
        pass
    return ""


def safe_filename(n: int) -> str:
    return os.path.join(IMAGES_DIR, f"step_{n:03d}.png")


def draw_click_marker(img: Image.Image, x: int, y: int) -> Image.Image:
    """Desenha um target no local do clique."""
    draw = ImageDraw.Draw(img)
    r_outer = 28
    r_inner = 10
    # círculo externo
    draw.ellipse((x - r_outer, y - r_outer, x + r_outer, y + r_outer), outline="red", width=5)
    # círculo interno
    draw.ellipse((x - r_inner, y - r_inner, x + r_inner, y + r_inner), outline="red", width=5)
    # cruz
    draw.line((x - r_outer - 10, y, x + r_outer + 10, y), fill="red", width=3)
    draw.line((x, y - r_outer - 10, x, y + r_outer + 10), fill="red", width=3)
    return img


def capture_screenshot_with_marker(path: str, click_pos: Optional[Tuple[int, int]] = None) -> None:
    shot = pyautogui.screenshot()
    img = shot.convert("RGB")
    if click_pos is not None:
        x, y = click_pos
        img = draw_click_marker(img, x, y)
    img.save(path, "PNG")


HTML_TEMPLATE = """
<!doctype html>
<html lang="pt-br">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ title }}</title>
  <style>
    :root { --bg:#0b0f17; --card:#121a2a; --text:#e8eefc; --muted:#9fb0d0; --accent:#6aa6ff; --border:#23304a; }
    body { margin:0; font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial; background:var(--bg); color:var(--text); }
    .wrap { max-width: 980px; margin: 0 auto; padding: 28px 18px 60px; }
    header { display:flex; gap:14px; align-items:center; justify-content:space-between; margin-bottom: 18px; }
    h1 { font-size: 22px; margin: 0; }
    .meta { color: var(--muted); font-size: 13px; }
    .step { background: var(--card); border: 1px solid var(--border); border-radius: 16px; padding: 16px; margin: 14px 0; box-shadow: 0 8px 22px rgba(0,0,0,.25); }
    .top { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; }
    .n { font-weight: 800; color: var(--accent); }
    .desc { font-size: 15px; line-height: 1.45; margin-top: 6px; }
    .tag { font-size: 12px; color: var(--muted); margin-top: 6px; }
    img { width: 100%; border-radius: 12px; border:1px solid var(--border); margin-top: 12px; }
    .footer { margin-top: 24px; color: var(--muted); font-size: 12px; }
    .kbd { padding: 2px 8px; border:1px solid var(--border); border-radius: 10px; background: rgba(255,255,255,.03); }
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <div>
        <h1>{{ title }}</h1>
        <div class="meta">Gerado em {{ generated_at }} • Passos: {{ steps|length }}</div>
      </div>
      <div class="meta">
        Atalhos: <span class="kbd">F8</span> pausar/retomar • <span class="kbd">F9</span> finalizar
      </div>
    </header>

    {% for s in steps %}
      <section class="step">
        <div class="top">
          <div>
            <div class="n">Passo {{ s.number }} • {{ s.kind|upper }}</div>
            {% if s.window_title %}
              <div class="tag">Janela: {{ s.window_title }}</div>
            {% endif %}
          </div>
          <div class="tag">{{ s.human_time }}</div>
        </div>
        {% if s.screenshot %}
          <img src="{{ s.screenshot }}" alt="Passo {{ s.number }}">
        {% endif %}
      </section>
    {% endfor %}

    <div class="footer">Saída em: {{ output_dir }}</div>
  </div>
</body>
</html>
"""
# <div class="desc">{{ s.description }}</div>

def render_html(steps: List[dict]) -> None:
    title = "Tutorial gravado (Tango-like)"
    generated_at = time.strftime("%Y-%m-%d %H:%M:%S")
    template = Template(HTML_TEMPLATE)
    html = template.render(
        title=title,
        generated_at=generated_at,
        steps=steps,
        output_dir=os.path.abspath(OUTPUT_DIR),
    )
    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html)


def render_markdown(steps: List[dict]) -> None:
    lines = []
    lines.append("# Tutorial gravado (Tango-like)")
    lines.append("")
    lines.append(f"_Gerado em {time.strftime('%Y-%m-%d %H:%M:%S')}_")
    lines.append("")
    for s in steps:
        lines.append(f"## Passo {s['number']} — {s['kind'].upper()}")
        lines.append(s["description"])
        if s.get("window_title"):
            lines.append(f"- Janela: {s['window_title']}")
        if s.get("screenshot"):
            lines.append(f"![Passo {s['number']}]({s['screenshot']})")
        lines.append("")
    with open(MD_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

# Commit to git
def commit_to_github():
    try:
        subprocess.run(["git", "add", "."], check=True)

        msg = time.strftime("tutorial %Y-%m-%d %H:%M:%S")

        subprocess.run(["git", "commit", "-m", msg], check=True)

        subprocess.run(["git", "push"], check=True)

        print("\n✅ Commit enviado para o GitHub")

    except Exception as e:
        print("Erro ao enviar para GitHub:", e)

class Recorder:
    def __init__(self):
        self.steps: List[Step] = []
        self.is_recording = False
        self.step_number = 1

        self._last_click_time = 0.0

        self._typed_buffer = []
        self._last_type_time = 0.0

        self._mouse_listener = None
        self._kbd_listener = None

    def _flush_typed_if_needed(self, force: bool = False):
        if not self._typed_buffer:
            return
        now = time.time()
        if force or (now - self._last_type_time) >= TYPE_IDLE_FLUSH_SECONDS:
            typed = "".join(self._typed_buffer).strip()
            self._typed_buffer = []
            if typed:
                preview = typed
                if len(preview) > MAX_TYPED_PREVIEW:
                    preview = preview[:MAX_TYPED_PREVIEW] + "…"
                self._add_step(
                    kind="type",
                    description=f"Digite: “{preview}”",
                    typed_text=typed,
                    take_screenshot=True,
                    marker=None,
                )

    def _add_step(
        self,
        kind: str,
        description: str,
        take_screenshot: bool = False,
        marker: Optional[Tuple[int, int]] = None,
        x: Optional[int] = None,
        y: Optional[int] = None,
        button: Optional[str] = None,
        scroll_dx: Optional[int] = None,
        scroll_dy: Optional[int] = None,
        typed_text: Optional[str] = None,
    ):
        window_title = get_active_window_title()
        ts = time.time()
        shot_path = None

        if take_screenshot:
            shot_path_abs = safe_filename(self.step_number)
            capture_screenshot_with_marker(shot_path_abs, click_pos=marker)
            # caminho relativo pro HTML
            shot_path = os.path.relpath(shot_path_abs, OUTPUT_DIR).replace("\\", "/")

        step = Step(
            number=self.step_number,
            kind=kind,
            timestamp=ts,
            window_title=window_title,
            description=description,
            screenshot=shot_path,
            x=x,
            y=y,
            button=button,
            scroll_dx=scroll_dx,
            scroll_dy=scroll_dy,
            typed_text=typed_text,
        )
        self.steps.append(step)
        print(f"[{self.step_number:03d}] {kind}: {description}")
        self.step_number += 1

    # ---------- Eventos ----------
    def on_click(self, x, y, button, pressed):
        if not self.is_recording:
            return
        if not pressed:
            return

        self._flush_typed_if_needed(force=True)

        now = time.time()
        if now - self._last_click_time < CLICK_DEBOUNCE_SECONDS:
            return
        self._last_click_time = now

        btn = str(button).replace("Button.", "")
        desc = f"Clique ({btn}) em ({x}, {y})."
        self._add_step(
            kind="click",
            description=desc,
            take_screenshot=True,
            marker=(x, y),
            x=x,
            y=y,
            button=btn,
        )

    def on_scroll(self, x, y, dx, dy):
        if not self.is_recording:
            return
        self._flush_typed_if_needed(force=True)
        direction = "para cima" if dy > 0 else "para baixo"
        desc = f"Role {direction} na posição ({x}, {y})."
        self._add_step(
            kind="scroll",
            description=desc,
            take_screenshot=True,
            marker=(x, y),
            x=x,
            y=y,
            scroll_dx=dx,
            scroll_dy=dy,
        )

    def on_press(self, key):
        # Hotkeys sempre funcionam, gravando ou não
        if key == START_PAUSE_KEY:
            self.is_recording = not self.is_recording
            state = "RETOMADO" if self.is_recording else "PAUSADO"
            print(f"== {state} (F8) ==")
            return

        if key == FINISH_KEY:
            print("== FINALIZANDO (F9) ==")
            self.stop()
            self.generate_outputs()
            return False  # para o listener de teclado

        if not self.is_recording:
            return

        # Digitação: vamos agrupar caracteres
        try:
            if isinstance(key, keyboard.KeyCode) and key.char is not None:
                self._typed_buffer.append(key.char)
                self._last_type_time = time.time()
                return
        except Exception:
            pass

        # Teclas especiais comuns
        specials = {
            keyboard.Key.enter: "\n",
            keyboard.Key.space: " ",
            keyboard.Key.tab: "[TAB]",
            keyboard.Key.backspace: "[BACKSPACE]",
        }
        if key in specials:
            self._typed_buffer.append(specials[key])
            self._last_type_time = time.time()

    # ---------- Controle ----------
    def start(self):
        print("Atalhos: F8 = pausar/retomar | F9 = finalizar e gerar tutorial")
        print("Começa PAUSADO. Aperte F8 para iniciar a gravação.")
        self.is_recording = False

        self._mouse_listener = mouse.Listener(on_click=self.on_click, on_scroll=self.on_scroll)
        self._kbd_listener = keyboard.Listener(on_press=self.on_press)

        self._mouse_listener.start()
        self._kbd_listener.start()

        self._kbd_listener.join()

    def stop(self):
        self._flush_typed_if_needed(force=True)
        try:
            if self._mouse_listener:
                self._mouse_listener.stop()
        except Exception:
            pass

    def generate_outputs(self):
        # Enriquecer com tempo humano para exibir no HTML
        out = []
        for s in self.steps:
            d = asdict(s)
            d["human_time"] = time.strftime("%H:%M:%S", time.localtime(s.timestamp))
            out.append(d)

        os.makedirs(OUTPUT_DIR, exist_ok=True)

        with open(JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)

        render_html(out)
        render_markdown(out)

        print("\n✅ Gerado:")
        print(f"- HTML:  {os.path.abspath(HTML_FILE)}")
        print(f"- MD:    {os.path.abspath(MD_FILE)}")
        print(f"- JSON:  {os.path.abspath(JSON_FILE)}")
        print(f"- IMG:   {os.path.abspath(IMAGES_DIR)}")
        commit_to_github()
        repo = subprocess.check_output(
            ["git", "config", "--get", "remote.origin.url"]
        ).decode().strip()

        # repo = repo.replace(".git","").replace("git@github.com:","https://github.com/")

        print("\n🔗 Tutorial online:")
        print("https://ecommerceferpam.github.io/tango-recordings/" + HTML_FILE)


if __name__ == "__main__":
    # Evita um bug comum de DPI em Windows (alguns PCs)
    try:
        if platform.system().lower().startswith("win"):
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    Recorder().start()