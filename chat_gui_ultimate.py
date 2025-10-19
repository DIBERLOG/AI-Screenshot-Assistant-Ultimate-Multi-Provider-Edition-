# chat_gui_ultimate.py
# -*- coding: utf-8 -*-
"""
AI Screenshot Assistant — Full Russian UI edition
Поддержка провайдеров: openai, deepseek, google, groq, together, custom
Полная версия: сохранение настроек по провайдерам, очистка Markdown, Ctrl+C/V в настройках,
single-instance guard, автоустановка зависимостей при запуске .py
"""

import os
import sys
import json
import time
import re
import threading
import tempfile
import subprocess
import importlib
from datetime import datetime
from pathlib import Path

# ----------------------------
# Автоустановка зависимостей (только при запуске .py, не в скомпилированном exe)
# ----------------------------
if not getattr(sys, "frozen", False):
    REQUIRED_PACKAGES = [
        "customtkinter",
        "pillow",
        "pytesseract",
        "keyboard",
        "pyperclip",
        "requests",
    ]
    for pkg in REQUIRED_PACKAGES:
        try:
            importlib.import_module(pkg)
        except Exception:
            try:
                print(f"[installer] Устанавливаю пакет: {pkg} ...")
                subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", pkg])
            except Exception as e:
                print(f"[installer] Не удалось установить {pkg}: {e}")

# ----------------------------
# Импорты (после автоустановки)
# ----------------------------
import tkinter as tk
from tkinter import messagebox, filedialog
import customtkinter as ctk
from PIL import Image, ImageGrab, ImageTk
import pytesseract
import keyboard
import pyperclip
import requests

# Опционально google-genai SDK
try:
    from google import genai
except Exception:
    genai = None

# ----------------------------
# Конфигурация и пути
# ----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "ai_gui_config.json")
ICON_NAME = "icon_robot.ico"

DEFAULT_CONFIG = {
    "provider": "google",
    "theme": "dark",
    "hotkey": "ctrl+b",
    "tesseract_path": r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    "screenshot_dir": os.path.join(BASE_DIR, "screenshot_temp"),
    "providers": {
        "openai": {
            "api_key": "",
            "model": "gpt-4o-mini",
            "base_url": "https://api.openai.com/v1"
        },
        "deepseek": {
            "api_key": "",
            "model": "deepseek-chat",
            "base_url": "https://api.deepseek.com"
        },
        "google": {
            "api_key": "",
            "model": "gemini-2.0-flash",
            "region": "",
            "project_id": ""
        },
        "groq": {
            "api_key": "",
            "model": "llama-3.3-70b-versatile",
            "base_url": "https://api.groq.com/openai/v1"
        },
        "together": {
            "api_key": "",
            "model": "meta-llama/Llama-3-70b-chat-hf",
            "base_url": "https://api.together.ai/v1"
        },
        "custom": {
            "api_key": "",
            "model": "",
            "base_url": "",
            "auth_header_name": "Authorization"
        }
    }
}

os.makedirs(DEFAULT_CONFIG["screenshot_dir"], exist_ok=True)

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
    else:
        cfg = {}
    merged = DEFAULT_CONFIG.copy()
    # merge shallow for top-level keys
    merged.update({k: v for k, v in cfg.items() if k != "providers"})
    # deep merge providers
    prov = DEFAULT_CONFIG["providers"].copy()
    prov.update(cfg.get("providers", {}))
    merged["providers"] = prov
    # keep other keys from cfg that might be new
    for k,v in cfg.items():
        if k not in merged:
            merged[k] = v
    # ensure screenshot dir exists
    os.makedirs(merged.get("screenshot_dir", DEFAULT_CONFIG["screenshot_dir"]), exist_ok=True)
    return merged

def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Ошибка сохранения конфига:", e)

config = load_config()

# применим путь к tesseract
try:
    pytesseract.pytesseract.tesseract_cmd = config.get("tesseract_path", DEFAULT_CONFIG["tesseract_path"])
except Exception:
    pass

# ----------------------------
# Single-instance guard (lockfile в TEMP)
# ----------------------------
LOCK_PATH = os.path.join(tempfile.gettempdir(), "ai_screenshot_assistant.lock")

def is_already_running():
    try:
        if os.path.exists(LOCK_PATH):
            try:
                with open(LOCK_PATH, "r", encoding="utf-8") as f:
                    pid_text = f.read().strip()
                pid = int(pid_text) if pid_text else 0
                if pid and pid != os.getpid():
                    try:
                        os.kill(pid, 0)
                        return True
                    except Exception:
                        # возможно устаревший PID
                        pass
            except Exception:
                return True
        return False
    except Exception:
        return False

def write_lock():
    try:
        with open(LOCK_PATH, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass

def remove_lock():
    try:
        if os.path.exists(LOCK_PATH):
            os.remove(LOCK_PATH)
    except Exception:
        pass

if is_already_running():
    print("Приложение уже запущено. Выход.")
    sys.exit(0)
else:
    write_lock()

# ----------------------------
# Вспомогательные функции (очистка Markdown и т.д.)
# ----------------------------
def strip_markdown(text: str) -> str:
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    # удалить блоки ```...```
    text = re.sub(r"```(.|\n)*?```", lambda m: m.group(0).replace("```", ""), text)
    # inline code `code`
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # remove bold/italic markers
    text = re.sub(r"(\*\*|\*|__|_)", "", text)
    # headers and blockquotes
    text = re.sub(r"(^|\n)[#]+\s*", r"\1", text)
    text = re.sub(r"(^|\n)>\s*", r"\1", text)
    # tildes and stray backslashes
    text = text.replace("~", "")
    text = text.replace("\\", "")
    # collapse multiple spaces
    text = re.sub(r"[ \t]{2,}", " ", text)
    # remove trailing spaces from lines and reduce excessive blank lines
    lines = [ln.rstrip() for ln in text.splitlines()]
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()

def pretty_format_response(text: str) -> str:
    return strip_markdown(text)

# ----------------------------
# HTTP-вызовы к провайдерам
# ----------------------------
def call_openai_like(base_url: str, api_key: str, model: str, prompt: str, timeout: int = 60) -> str:
    if not base_url:
        raise RuntimeError("Base URL не указан для провайдера.")
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1024,
        "temperature": 0.2
    }
    r = requests.post(url, headers=headers, json=payload, timeout=timeout)
    r.raise_for_status()
    j = r.json()
    if isinstance(j, dict):
        if "choices" in j and len(j["choices"]) > 0:
            first = j["choices"][0]
            # chat completion style
            if isinstance(first.get("message"), dict):
                return first["message"].get("content", "")
            if "text" in first:
                return first.get("text", "")
    return json.dumps(j, ensure_ascii=False)

def call_google_genai(api_key: str, model: str, prompt: str) -> str:
    if genai is None:
        raise RuntimeError("google-genai SDK не установлен. Установите 'google-genai' если хотите использовать Google провайдера.")
    client = genai.Client(api_key=api_key)
    resp = client.models.generate_content(model=model, contents=prompt)
    # try to extract text
    return getattr(resp, "text", str(resp))

def unified_call(provider_name: str, prompt: str) -> str:
    prov = provider_name.lower()
    providers = config.get("providers", {})
    if prov not in providers:
        raise RuntimeError(f"Провайдер '{prov}' не сконфигурирован.")
    pdata = providers.get(prov, {})
    api_key = pdata.get("api_key", "") or ""
    model = pdata.get("model", "") or config.get("model", "")
    base_url = pdata.get("base_url", "") or ""
    if prov == "google":
        google_key = pdata.get("api_key") or config.get("google_api_key") or os.environ.get("GOOGLE_API_KEY", "")
        if not google_key:
            raise RuntimeError("Google API ключ не указан.")
        return call_google_genai(google_key, model, prompt)
    if prov in ("openai", "deepseek", "groq", "together", "custom"):
        if not api_key:
            raise RuntimeError("API ключ не указан для провайдера.")
        # custom: try openai-like then fallback
        if prov == "custom":
            try:
                return call_openai_like(base_url or pdata.get("base_url", ""), api_key, model, prompt)
            except requests.HTTPError:
                # fallback generic
                auth_name = pdata.get("auth_header_name", "Authorization")
                headers = {auth_name: f"Bearer {api_key}", "Content-Type": "application/json"}
                r = requests.post(base_url, headers=headers, json={"model": model, "input": prompt}, timeout=60)
                r.raise_for_status()
                j = r.json()
                return j.get("output") or j.get("result") or str(j)
        else:
            return call_openai_like(base_url or pdata.get("base_url", ""), api_key, model, prompt)
    raise RuntimeError("Неподдерживаемый провайдер")

# ----------------------------
# GUI (полная версия)
# ----------------------------
# ----------------------------
# Splash Screen (экран загрузки)
# ----------------------------
class SplashScreen(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.overrideredirect(True)  # убираем рамку окна
        self.geometry("420x220+600+300")  # размер и позиция по центру
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        frame = ctk.CTkFrame(self, corner_radius=15)
        frame.pack(fill="both", expand=True, padx=8, pady=8)

        ctk.CTkLabel(frame, text="✨ AI Screenshot Assistant", font=("Segoe UI", 22, "bold")).pack(pady=(35,10))
        ctk.CTkLabel(frame, text="Загрузка компонентов...", font=("Segoe UI", 14)).pack(pady=(4,20))

        self.progress = ctk.CTkProgressBar(frame, width=280)
        self.progress.pack(pady=10)
        self.progress.set(0)

        self.update_idletasks()
        self.after(100, self.animate)

    def animate(self):
        for i in range(0, 101, 4):
            self.progress.set(i / 100)
            self.update_idletasks()
            time.sleep(0.05)
        self.destroy()

class ChatApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        # иконка (если есть)
        try:
            if getattr(sys, "frozen", False):
                base = sys._MEIPASS
            else:
                base = BASE_DIR
            icon_path = os.path.join(base, ICON_NAME)
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
        except Exception:
            pass

        self.title("✨ AI Screenshot Assistant Ultimate")
        self.geometry("1200x760")
        ctk.set_appearance_mode(config.get("theme", "dark"))
        ctk.set_default_color_theme("blue")

        # хоткей
        self.hotkey = config.get("hotkey", "ctrl+b")
        self.hotkey_handler = None
        self.after(1500, self._register_hotkey_delayed)

        # сетка
        self.columnconfigure((0,1), weight=1)
        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=0)

        # левая панель: скриншот и OCR
        left = ctk.CTkFrame(self, corner_radius=12)
        left.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        ctk.CTkLabel(left, text="🖼️ Скриншот", font=("Segoe UI", 16, "bold")).grid(row=0, column=0, pady=(8,6))
        self.screenshot_display = ctk.CTkLabel(left, text="Нет изображения", height=260, fg_color="#1e1e1e", corner_radius=8)
        self.screenshot_display.grid(row=1, column=0, sticky="nsew", padx=8, pady=6)
        ctk.CTkLabel(left, text="📄 Распознанный текст:", font=("Segoe UI", 14)).grid(row=2, column=0, sticky="w", padx=8, pady=(8,4))
        self.recognized_text = ctk.CTkTextbox(left, height=180)
        self.recognized_text.grid(row=3, column=0, sticky="nsew", padx=8, pady=(0,12))

        # правая панель: ввод и ответ
        right = ctk.CTkFrame(self, corner_radius=12)
        right.grid(row=0, column=1, sticky="nsew", padx=(0,12), pady=12)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(4, weight=1)

        ctk.CTkLabel(right, text="🤖 Вопрос к AI:", font=("Segoe UI", 15, "bold")).grid(row=0, column=0, sticky="w", padx=10, pady=(8,6))
        self.user_input = ctk.CTkTextbox(right, height=80)
        self.user_input.grid(row=1, column=0, sticky="ew", padx=10, pady=(0,10))
        self.user_input.bind("<Return>", self._on_enter_send)

        quick_frame = ctk.CTkFrame(right)
        quick_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(0,8))
        for t in ["Что это?", "Поясни смысл", "Кратко перескажи", "Примени на практике"]:
            ctk.CTkButton(quick_frame, text=t, height=32, command=lambda tt=t: self.ask_ai(custom_text=tt)).pack(side="left", padx=6, pady=4, expand=True, fill="x")

        ctk.CTkLabel(right, text="💬 Ответ AI:", font=("Segoe UI", 15, "bold")).grid(row=3, column=0, sticky="w", padx=10, pady=(4,6))
        self.ai_answer = tk.Text(right, wrap="word", bg="#1e1e1e", fg="#9cd6ff", font=("Segoe UI", 12))
        self.ai_answer.grid(row=4, column=0, sticky="nsew", padx=10, pady=(0,8))

        # нижняя панель: кнопки
        bottom = ctk.CTkFrame(self, corner_radius=10, height=70)
        bottom.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0,12))
        bottom.pack_propagate(False)

        left_controls = ctk.CTkFrame(bottom)
        left_controls.pack(side="left", padx=6, pady=6)
        ctk.CTkButton(left_controls, text="📸 Скриншот (область)", command=self.capture_area, width=170).pack(side="left", padx=6)
        ctk.CTkButton(left_controls, text="📋 Вставить", command=self.paste_clipboard, width=120).pack(side="left", padx=6)

        right_controls = ctk.CTkFrame(bottom)
        right_controls.pack(side="right", padx=6, pady=6)
        ctk.CTkButton(right_controls, text="⚡ Вопрос", command=self.ask_ai, width=120).pack(side="left", padx=4)
        ctk.CTkButton(right_controls, text="📋 Копировать ответ", command=self.copy_answer, width=160).pack(side="left", padx=4)
        ctk.CTkButton(right_controls, text="🗑 Очистить", command=self.clear_answer, width=120, fg_color="#444", hover_color="#666").pack(side="left", padx=4)
        ctk.CTkButton(right_controls, text="⚙️ Настройки", command=self.show_settings, width=120).pack(side="left", padx=6)
        ctk.CTkButton(right_controls, text="❌ Выход", command=self.on_closing, width=100, fg_color="#c0392b").pack(side="left", padx=6)

    # ---------- хоткей ----------
    def _register_hotkey_delayed(self):
        try:
            if self.hotkey_handler:
                keyboard.remove_hotkey(self.hotkey_handler)
        except Exception:
            pass
        try:
            self.hotkey_handler = keyboard.add_hotkey(self.hotkey, self.capture_area)
        except Exception as e:
            print("Не удалось зарегистрировать хоткей:", e)

    # ---------- скриншот и OCR ----------
    def capture_area(self):
        self.withdraw()
        self.after(200, self._capture_selection)

    def _capture_selection(self):
        root = tk.Tk()
        root.attributes("-fullscreen", True)
        root.attributes("-alpha", 0.25)
        canvas = tk.Canvas(root, cursor="cross", bg="gray")
        canvas.pack(fill="both", expand=True)
        rect = None
        start_x = start_y = 0

        def on_click(e):
            nonlocal start_x, start_y, rect
            start_x, start_y = e.x, e.y
            rect = canvas.create_rectangle(start_x, start_y, start_x, start_y, outline="red", width=2)

        def on_drag(e):
            nonlocal rect
            if rect:
                canvas.coords(rect, start_x, start_y, e.x, e.y)

        def on_release(e):
            x1, x2 = sorted([start_x, e.x])
            y1, y2 = sorted([start_y, e.y])
            root.destroy()
            if x1 == x2 or y1 == y2:
                messagebox.showwarning("Ошибка", "Область скриншота слишком мала!")
                self.deiconify()
                return
            image = ImageGrab.grab(bbox=(x1, y1, x2, y2))
            thumb = image.copy()
            thumb.thumbnail((360, 270))
            tkimg = ImageTk.PhotoImage(thumb)
            self.screenshot_display.configure(image=tkimg, text="")
            self.screenshot_display.image = tkimg
            try:
                text = pytesseract.image_to_string(image, lang="eng+rus", config="--psm 6")
            except Exception as e:
                text = f"[OCR error: {e}]"
            self.recognized_text.delete("1.0", "end")
            self.recognized_text.insert("1.0", text.strip())
            self.deiconify()

        canvas.bind("<ButtonPress-1>", on_click)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)
        root.mainloop()

    # ---------- отправка запроса ----------
    def _on_enter_send(self, event):
        self.ask_ai()
        return "break"

    def ask_ai(self, custom_text=None):
        question = self.user_input.get("1.0", "end").strip()
        if custom_text and not question:
            question = custom_text
        context = self.recognized_text.get("1.0", "end").strip()
        if not question and not context:
            messagebox.showinfo("Внимание", "Введите вопрос или сделайте скриншот.")
            return
        prompt = f"{context}\n\nПользователь спрашивает: {question}"
        self.ai_answer.delete("1.0", "end")
        self.ai_answer.insert("1.0", "⏳ Отправляю запрос...")
        threading.Thread(target=self._generate_thread, args=(prompt,), daemon=True).start()

    def _generate_thread(self, prompt):
        try:
            provider = config.get("provider", "openai")
            raw = unified_call(provider, prompt)
            out = pretty_format_response(raw)
            out = strip_markdown(out)
            self.ai_answer.delete("1.0", "end")
            self.ai_answer.insert("1.0", out.strip())
            self.ai_answer.see("1.0")
        except requests.HTTPError as he:
            try:
                text = he.response.text
            except Exception:
                text = str(he)
            self.ai_answer.delete("1.0", "end")
            self.ai_answer.insert("1.0", f"⚠️ HTTP Error: {he}\n{text}")
        except Exception as e:
            self.ai_answer.delete("1.0", "end")
            self.ai_answer.insert("1.0", f"⚠️ Ошибка: {e}")

    # ---------- буфер обмена ----------
    def paste_clipboard(self):
        try:
            txt = self.clipboard_get()
            self.user_input.insert("end", txt)
        except Exception:
            pass

    def copy_answer(self):
        txt = self.ai_answer.get("1.0", "end").strip()
        if txt:
            pyperclip.copy(txt)
            messagebox.showinfo("Скопировано", "Ответ скопирован в буфер обмена.")

    def clear_answer(self):
        self.ai_answer.delete("1.0", "end")

    # ---------- окно настроек (полное, с сохранением по провайдеру) ----------
    def show_settings(self):
        win = ctk.CTkToplevel(self)
        win.title("⚙️ Настройки — Провайдеры")
        win.geometry("540x560")
        win.resizable(False, False)  # теперь окно фиксированное
        win.grab_set()

        frame = ctk.CTkScrollableFrame(win, corner_radius=10)
        frame.pack(fill="both", expand=True, padx=12, pady=12)

        ctk.CTkLabel(frame, text="Выберите провайдера:", font=("Segoe UI", 14, "bold")).pack(pady=(6, 4))
        provider_var = tk.StringVar(value=config.get("provider", "google"))
        prov_menu = ctk.CTkOptionMenu(frame, values=["openai", "deepseek", "google", "groq", "together", "custom"],
                                      variable=provider_var, width=220)
        prov_menu.pack(pady=(2, 8))

        ctk.CTkLabel(frame, text="API Key:").pack(pady=(6, 2))
        api_entry = ctk.CTkEntry(frame, width=420)
        api_entry.insert(0, config.get("api_key", ""))

        # Включаем Ctrl+C / Ctrl+V
        for key in ("<Control-c>", "<Control-v>", "<Control-x>"):
            api_entry.bind(key, lambda e, k=key: api_entry.event_generate({"<Control-c>": "<<Copy>>",
                                                                           "<Control-v>": "<<Paste>>",
                                                                           "<Control-x>": "<<Cut>>"}[k]))
        api_entry.pack(pady=(0, 8))

        ctk.CTkLabel(frame, text="Модель (model):").pack(pady=(6, 2))
        model_entry = ctk.CTkEntry(frame, width=420)
        model_entry.insert(0, config.get("model", "gemini-2.0-flash"))
        model_entry.pack(pady=(0, 8))

        ctk.CTkLabel(frame, text="Base URL (для кастомных API):").pack(pady=(6, 2))
        base_entry = ctk.CTkEntry(frame, width=420)
        cur_provider = config.get("provider", "google")
        cur_base = config.get("providers", {}).get(cur_provider, {}).get("base_url", "")
        base_entry.insert(0, cur_base)
        base_entry.pack(pady=(0, 8))

        ctk.CTkLabel(frame, text="Путь к Tesseract OCR:").pack(pady=(6, 2))
        tess_entry = ctk.CTkEntry(frame, width=420)
        tess_entry.insert(0, config.get("tesseract_path", DEFAULT_CONFIG["tesseract_path"]))
        tess_entry.pack(pady=(0, 4))

        def browse_tess():
            path = filedialog.askopenfilename(title="Выбери tesseract.exe", filetypes=[("EXE", "*.exe")])
            if path:
                tess_entry.delete(0, "end")
                tess_entry.insert(0, path)

        ctk.CTkButton(frame, text="Обзор...", command=browse_tess, width=100).pack(pady=(4, 8))

        def on_provider_change(pname):
            # Подгружаем индивидуальные настройки
            provider_conf = config.get("providers", {}).get(pname, {})
            api_entry.delete(0, "end")
            base_entry.delete(0, "end")
            model_entry.delete(0, "end")

            if pname == "google":
                # Для Google – предустановленные значения
                api_entry.insert(0, "AIzaSyCeWd_yVFCqw3q6HAn73Uvf4V9PUvciJiQ")
                model_entry.insert(0, "gemini-2.0-flash")
                base_entry.insert(0, "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent")
            else:
                api_entry.insert(0, provider_conf.get("api_key", config.get("api_key", "")))
                model_entry.insert(0, provider_conf.get("model", config.get("model", "")))
                base_entry.insert(0, provider_conf.get("base_url", ""))

            config["provider"] = pname
            save_config(config)

        prov_menu.configure(command=on_provider_change)

        def save_settings():
            pname = provider_var.get()
            provs = config.get("providers", {})
            provs[pname] = provs.get(pname, {})

            provs[pname]["api_key"] = api_entry.get().strip()
            provs[pname]["model"] = model_entry.get().strip()
            provs[pname]["base_url"] = base_entry.get().strip()

            config["providers"] = provs
            config["provider"] = pname
            config["api_key"] = api_entry.get().strip()
            config["model"] = model_entry.get().strip()
            config["tesseract_path"] = tess_entry.get().strip()

            save_config(config)
            messagebox.showinfo("✅ Успешно", f"Настройки для {pname} сохранены!")
            win.destroy()

        ctk.CTkButton(frame, text="💾 Сохранить", command=save_settings, width=140).pack(pady=(10, 12))

    # ---------- выход и очистка ----------
    def on_closing(self):
        save_config(config)
        try:
            if self.hotkey_handler:
                keyboard.remove_hotkey(self.hotkey_handler)
        except Exception:
            pass
        remove_lock()
        self.destroy()

# ----------------------------
# Запуск
# ----------------------------
def main():
    try:
        # показываем экран загрузки
        splash = SplashScreen()
        splash.update()
        splash.after(2000, splash.destroy)  # заставка 2 сек
        splash.mainloop()

        # после закрытия splash запускаем основное окно
        app = ChatApp()
        app.protocol("WM_DELETE_WINDOW", app.on_closing)
        app.mainloop()
    finally:
        remove_lock()


if __name__ == "__main__":
    main()
