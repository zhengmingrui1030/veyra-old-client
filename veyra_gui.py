# 作用：旧版 Veyra 桌面客户端（Windows 原生窗口、对话、托盘）
# 调用关系：独立运行，读同目录 config.json；与 veyra_admin.py 无依赖
# 版权：Copyright (c) 2026 zhengmingrui1030，许可见 LICENSE（PolyForm Noncommercial 1.0.0）

#!/usr/bin/env python
# -*- coding: utf-8 -*-

import ctypes
from ctypes import wintypes
import os
import sys
import time
import json
import threading
import subprocess
import requests

# ========== 路径配置 ==========
if getattr(sys, 'frozen', False):
    SCRIPT_DIR = os.path.dirname(os.path.abspath(sys.executable))
    BASE_DIR = SCRIPT_DIR
    INTERNAL_DIR = os.path.join(SCRIPT_DIR, '_internal')
    if os.path.exists(os.path.join(INTERNAL_DIR, "config.json")):
        CONFIG_PATH = os.path.join(INTERNAL_DIR, "config.json")
    else:
        CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")
else:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    BASE_DIR = os.path.dirname(SCRIPT_DIR)
    CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")

RUNTIME_DIR = os.path.join(BASE_DIR, "运行时")
MODELS_DIR = os.path.join(BASE_DIR, "模型")
os.makedirs(RUNTIME_DIR, exist_ok=True)

AVAILABLE_MODELS = [
    "qwen2.5:0.5b",
    "qwen2.5:1.5b",
    "qwen2.5:3b",
    "qwen2:7b",
    "qwen2.5:7b-instruct",
    "gemma3:1b",
    "llama3.2:1b",
    "llama3.2:3b",
    "llama3.1:8b",
    "gemma2:9b",
]

DEFAULT_CONFIG = {
    "model_name": "qwen2.5:0.5b",
    "ollama_base_url": "http://localhost:11434",
    "server_port": 7860,
    "auto_start": True,
}

def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
                result = DEFAULT_CONFIG.copy()
                result.update(cfg)
                return result
        except:
            pass
    return DEFAULT_CONFIG.copy()

def save_config(cfg):
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        return True
    except:
        return False

CONFIG = load_config()

# ========== 全局状态 ==========
class State:
    ollama_running = False
    web_running = False
    ollama_process = None
    web_process = None
    logs = []
    should_exit = False
    last_log_count = 0

    @classmethod
    def log(cls, msg):
        ts = time.strftime("%H:%M:%S")
        cls.logs.append(f"[{ts}] {msg}")
        if len(cls.logs) > 100:
            cls.logs = cls.logs[-100:]
        if hwnd_main:
            user32.PostMessageW(hwnd_main, WM_TIMER, ID_TIMER, 0)

# ========== 服务管理 ==========
def find_ollama_exe():
    if getattr(sys, 'frozen', False) and os.name == "nt":
        internal_dir = os.path.join(os.path.dirname(sys.executable), '_internal')
        for p in [
            os.path.join(internal_dir, 'Ollama', 'ollama.exe'),
            os.path.join(internal_dir, 'Ollama', 'lib', 'ollama', 'ollama.exe'),
        ]:
            if os.path.exists(p):
                return p
    if os.name == "nt":
        for drive in "DEFGHIJKLMNOPQRSTUVWXYZ":
            for folder in ["软件", "software"]:
                p = f"{drive}:/Veyra/{folder}/Ollama/ollama.exe"
                if os.path.exists(p):
                    return p
    import shutil
    return shutil.which("ollama.exe") or shutil.which("ollama")

def _hidden_startup():
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = subprocess.SW_HIDE
    return si

def _kill_process_tree(proc):
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                timeout=5,
                startupinfo=_hidden_startup(),
                creationflags=subprocess.CREATE_NO_WINDOW
            )
        except:
            pass
    else:
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except:
            try:
                proc.kill()
            except:
                pass

def start_ollama():
    State.log("启动Ollama...")
    exe = find_ollama_exe()
    State.log(f"Ollama路径: {exe}")
    if not exe:
        State.log("错误: 未找到ollama.exe，请确保已安装Ollama")
        return False
    env = os.environ.copy()
    env["OLLAMA_MODELS"] = MODELS_DIR
    env["OLLAMA_NUM_GPUS"] = "0"
    try:
        State.ollama_process = subprocess.Popen(
            [exe, "serve"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, startupinfo=_hidden_startup(),
            creationflags=subprocess.CREATE_NO_WINDOW,
            text=True)
        State.log("Ollama已启动")
        State.log(f"Ollama PID: {State.ollama_process.pid}")
        return True
    except Exception as e:
        State.log(f"Ollama启动失败: {type(e).__name__}: {e}")
        return False

def stop_ollama():
    State.log("停止Ollama...")
    if State.ollama_process:
        _kill_process_tree(State.ollama_process)
        State.ollama_process = None
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", "ollama.exe"],
                capture_output=True, timeout=5,
                startupinfo=_hidden_startup(),
                creationflags=subprocess.CREATE_NO_WINDOW
            )
        except:
            pass
    State.ollama_running = False
    State.log("Ollama已停止")

def check_ollama():
    try:
        r = requests.get(f"{CONFIG['ollama_base_url']}/api/tags", timeout=2)
        State.ollama_running = r.status_code == 200
    except:
        State.ollama_running = False

def find_web_exe():
    if getattr(sys, 'frozen', False):
        exe_path = os.path.join(os.path.dirname(sys.executable), 'veyra_server.exe')
        if os.path.exists(exe_path):
            return exe_path
    script = os.path.join(SCRIPT_DIR, "veyra_server.py")
    if os.path.exists(script):
        return script
    for d in "DEFGHIJKLMNOPQRSTUVWXYZ":
        for folder in ["代码", "code"]:
            p = f"{d}:/Veyra/{folder}/veyra_server.py"
            if os.path.exists(p):
                return p
    return None

def start_web():
    State.log("启动Web服务...")
    web_target = find_web_exe()
    if not web_target:
        State.log("错误: 未找到主程序")
        return False
    env = os.environ.copy()
    env["OLLAMA_MODELS"] = MODELS_DIR
    env["OLLAMA_NUM_GPUS"] = "0"
    try:
        if web_target.endswith('.exe'):
            State.web_process = subprocess.Popen(
                [web_target],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env=env, cwd=os.path.dirname(web_target),
                startupinfo=_hidden_startup(),
                creationflags=subprocess.CREATE_NO_WINDOW,
                text=True)
        else:
            State.web_process = subprocess.Popen(
                [sys.executable, web_target],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env=env, cwd=os.path.dirname(web_target),
                startupinfo=_hidden_startup(),
                creationflags=subprocess.CREATE_NO_WINDOW,
                text=True)
        State.web_running = True
        State.log(f"Web服务已启动 (端口:{CONFIG.get('web_port',7860)})")
        State.log(f"Web PID: {State.web_process.pid}")
        return True
    except Exception as e:
        State.log(f"Web启动失败: {type(e).__name__}: {e}")
        return False

def stop_web():
    State.log("停止Web服务...")
    if State.web_process:
        _kill_process_tree(State.web_process)
        State.web_process = None
    State.web_running = False
    State.log("Web服务已停止")

def open_ai_browser():
    port = CONFIG.get('server_port', 7860)
    import webbrowser
    webbrowser.open(f"http://localhost:{port}")
    State.log(f"打开AI界面: http://localhost:{port}")

def set_model(model_name):
    CONFIG['model_name'] = model_name
    save_config(CONFIG)
    State.log(f"已设置默认模型: {model_name}")
    if State.web_running:
        State.log("重启Web服务以应用新模型...")
        stop_web()
        time.sleep(2)
        start_web()

# ========== Win32 API ==========
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
gdi32 = ctypes.windll.gdi32

# Window styles
WS_OVERLAPPEDWINDOW = 0x00CF0000
WS_CHILD = 0x40000000
WS_VISIBLE = 0x10000000
WS_BORDER = 0x00800000
WS_VSCROLL = 0x00200000
WS_TABSTOP = 0x00010000
ES_MULTILINE = 0x0004
ES_READONLY = 0x0800
ES_AUTOVSCROLL = 0x0040
CBS_DROPDOWNLIST = 0x0003

# Messages
WM_COMMAND = 0x0111
WM_TIMER = 0x0013
WM_DESTROY = 0x0002
WM_SETFONT = 0x0030
WM_ERASEBKGND = 0x0014
WM_PAINT = 0x000F
WM_SIZE = 0x0005
EM_SETSEL = 0x00B1
EM_SCROLLCARET = 0x00B7
BN_CLICKED = 0
CBN_SELCHANGE = 1

# Button IDs
ID_BTN_START_OL = 101
ID_BTN_STOP_OL = 102
ID_BTN_START_WEB = 103
ID_BTN_STOP_WEB = 104
ID_BTN_OPEN = 105
ID_BTN_EXIT = 106
ID_CMB_MODEL = 107
ID_TIMER = 200

# Control handles
hwnd_main = None
hwnd_log = None
hwnd_lbl_ol = None
hwnd_lbl_web = None
hwnd_cmb_model = None
hInstance = None
model_bufs = []

# COMBOBOXITEM info
CB_ADDSTRING = 0x0143
CB_SETCURSEL = 0x014E
CB_GETCURSEL = 0x0147

# WNDCLASSW struct (wintypes only has ANSI WNDCLASS, need W version)
WNDPROCTYPE = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t)

class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", ctypes.c_uint32),
        ("lpfnWndProc", WNDPROCTYPE),
        ("cbClsExtra", ctypes.c_int32),
        ("cbWndExtra", ctypes.c_int32),
        ("hInstance", ctypes.c_void_p),
        ("hIcon", ctypes.c_void_p),
        ("hCursor", ctypes.c_void_p),
        ("hbrBackground", ctypes.c_void_p),
        ("lpszMenuName", ctypes.c_wchar_p),
        ("lpszClassName", ctypes.c_wchar_p),
    ]

class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [
        ("hdc", ctypes.c_void_p),
        ("fErase", ctypes.c_int),
        ("rcPaint", wintypes.RECT),
        ("fRestore", ctypes.c_int),
        ("fIncUpdate", ctypes.c_int),
        ("rgbReserved", ctypes.c_byte * 32),
    ]

# Set Win32 function types
kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
kernel32.GetModuleHandleW.restype = ctypes.c_void_p

user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.RegisterClassW.restype = ctypes.c_uint16

user32.CreateWindowExW.argtypes = [ctypes.c_uint32, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
user32.CreateWindowExW.restype = ctypes.c_void_p

user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
user32.ShowWindow.restype = ctypes.c_int

user32.UpdateWindow.argtypes = [ctypes.c_void_p]
user32.UpdateWindow.restype = ctypes.c_int

user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint]
user32.GetMessageW.restype = ctypes.c_int

user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.TranslateMessage.restype = ctypes.c_int

user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.restype = ctypes.c_ssize_t

user32.PostQuitMessage.argtypes = [ctypes.c_int]

user32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
user32.PostMessageW.restype = ctypes.c_int

user32.LoadCursorW.argtypes = [ctypes.c_void_p, ctypes.c_int]
user32.LoadCursorW.restype = ctypes.c_void_p

gdi32.GetStockObject.argtypes = [ctypes.c_int]
gdi32.GetStockObject.restype = ctypes.c_void_p

user32.SetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
user32.SetWindowTextW.restype = ctypes.c_int

user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
user32.SendMessageW.restype = ctypes.c_ssize_t

user32.SetTimer.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p]
user32.SetTimer.restype = ctypes.c_uint

user32.DestroyWindow.argtypes = [ctypes.c_void_p]
user32.DestroyWindow.restype = ctypes.c_int

user32.EnumChildWindows.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ssize_t]
user32.EnumChildWindows.restype = ctypes.c_int

user32.DefWindowProcW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
user32.DefWindowProcW.restype = ctypes.c_ssize_t

user32.GetClientRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.RECT)]
user32.GetClientRect.restype = ctypes.c_int

user32.InvalidateRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.RECT), ctypes.c_int]
user32.InvalidateRect.restype = ctypes.c_int

user32.FillRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.RECT), ctypes.c_void_p]
user32.FillRect.restype = ctypes.c_int

user32.BeginPaint.argtypes = [ctypes.c_void_p, ctypes.POINTER(PAINTSTRUCT)]
user32.BeginPaint.restype = ctypes.c_void_p

user32.EndPaint.argtypes = [ctypes.c_void_p, ctypes.POINTER(PAINTSTRUCT)]
user32.EndPaint.restype = ctypes.c_int

user32.LoadImageW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
user32.LoadImageW.restype = ctypes.c_void_p

IMAGE_ICON = 1
LR_LOADFROMFILE = 0x00000010

def wnd_proc(hwnd, msg, wparam, lparam):
    global hwnd_main
    if msg == WM_COMMAND:
        ctrl_id = wparam & 0xFFFF
        notification = (wparam >> 16) & 0xFFFF
        if notification == BN_CLICKED:
            if ctrl_id == ID_BTN_START_OL:
                threading.Thread(target=start_ollama, daemon=True).start()
            elif ctrl_id == ID_BTN_STOP_OL:
                threading.Thread(target=stop_ollama, daemon=True).start()
            elif ctrl_id == ID_BTN_START_WEB:
                threading.Thread(target=start_web, daemon=True).start()
            elif ctrl_id == ID_BTN_STOP_WEB:
                threading.Thread(target=stop_web, daemon=True).start()
            elif ctrl_id == ID_BTN_OPEN:
                threading.Thread(target=open_ai_browser, daemon=True).start()
            elif ctrl_id == ID_BTN_EXIT:
                State.should_exit = True
                stop_web()
                stop_ollama()
                user32.DestroyWindow(hwnd)
        elif notification == CBN_SELCHANGE and ctrl_id == ID_CMB_MODEL:
            sel_idx = user32.SendMessageW(hwnd_cmb_model, CB_GETCURSEL, 0, 0)
            if sel_idx >= 0 and sel_idx < len(AVAILABLE_MODELS):
                model_name = AVAILABLE_MODELS[sel_idx]
                threading.Thread(target=set_model, args=(model_name,), daemon=True).start()
        return 0
    elif msg == WM_ERASEBKGND:
        hdc = wparam
        rect = wintypes.RECT()
        user32.GetClientRect(hwnd, ctypes.byref(rect))
        brush = gdi32.GetStockObject(15)
        user32.FillRect(hdc, ctypes.byref(rect), brush)
        return 1
    elif msg == WM_PAINT:
        ps = PAINTSTRUCT()
        hdc = user32.BeginPaint(hwnd, ctypes.byref(ps))
        rect = wintypes.RECT()
        user32.GetClientRect(hwnd, ctypes.byref(rect))
        brush = gdi32.GetStockObject(15)
        user32.FillRect(hdc, ctypes.byref(rect), brush)
        user32.EndPaint(hwnd, ctypes.byref(ps))
        return 0
    elif msg == WM_SIZE:
        user32.InvalidateRect(hwnd, None, True)
        return 0
    elif msg == WM_TIMER:
        if wparam == ID_TIMER:
            check_ollama()
            update_status_labels()
            update_log_text()
        return 0
    elif msg == WM_DESTROY:
        State.should_exit = True
        stop_web()
        stop_ollama()
        user32.PostQuitMessage(0)
        return 0
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

wnd_proc_ptr = WNDPROCTYPE(wnd_proc)

def create_window():
    global hwnd_main, hwnd_log, hwnd_lbl_ol, hwnd_lbl_web, hwnd_cmb_model, hInstance

    hInstance = kernel32.GetModuleHandleW(None)

    icon_path = os.path.join(SCRIPT_DIR, 'robot.ico')
    hIcon = None
    if os.path.exists(icon_path):
        hIcon = user32.LoadImageW(hInstance, icon_path, IMAGE_ICON, 0, 0, LR_LOADFROMFILE)

    wc = WNDCLASSW()
    wc.style = 0
    wc.lpfnWndProc = wnd_proc_ptr
    wc.cbClsExtra = 0
    wc.cbWndExtra = 0
    wc.hInstance = hInstance
    wc.hIcon = hIcon
    wc.hCursor = user32.LoadCursorW(None, 32512)
    wc.hbrBackground = gdi32.GetStockObject(15)
    wc.lpszMenuName = None
    wc.lpszClassName = "Veyra"

    user32.RegisterClassW(ctypes.byref(wc))

    hwnd_main = user32.CreateWindowExW(
        0, "Veyra", "Veyra助手 v8.7.2",
        WS_OVERLAPPEDWINDOW,
        100, 100, 800, 600,
        0, 0, hInstance, None)

    hwnd_lbl_ol = user32.CreateWindowExW(
        0, "STATIC", "Ollama: 检测中...",
        WS_CHILD | WS_VISIBLE,
        20, 20, 250, 28,
        hwnd_main, 0, hInstance, None)

    user32.CreateWindowExW(
        0, "BUTTON", "启动Ollama",
        WS_CHILD | WS_VISIBLE | WS_TABSTOP,
        280, 18, 100, 30,
        hwnd_main, ID_BTN_START_OL, hInstance, None)

    user32.CreateWindowExW(
        0, "BUTTON", "停止Ollama",
        WS_CHILD | WS_VISIBLE | WS_TABSTOP,
        390, 18, 100, 30,
        hwnd_main, ID_BTN_STOP_OL, hInstance, None)

    hwnd_lbl_web = user32.CreateWindowExW(
        0, "STATIC", "Web服务: 未启动",
        WS_CHILD | WS_VISIBLE,
        20, 65, 250, 28,
        hwnd_main, 0, hInstance, None)

    user32.CreateWindowExW(
        0, "BUTTON", "启动Web",
        WS_CHILD | WS_VISIBLE | WS_TABSTOP,
        280, 63, 100, 30,
        hwnd_main, ID_BTN_START_WEB, hInstance, None)

    user32.CreateWindowExW(
        0, "BUTTON", "停止Web",
        WS_CHILD | WS_VISIBLE | WS_TABSTOP,
        390, 63, 100, 30,
        hwnd_main, ID_BTN_STOP_WEB, hInstance, None)

    user32.CreateWindowExW(
        0, "BUTTON", "打开AI界面",
        WS_CHILD | WS_VISIBLE | WS_TABSTOP,
        500, 63, 120, 30,
        hwnd_main, ID_BTN_OPEN, hInstance, None)

    user32.CreateWindowExW(
        0, "STATIC", "默认模型:",
        WS_CHILD | WS_VISIBLE,
        20, 110, 80, 28,
        hwnd_main, 0, hInstance, None)

    hwnd_cmb_model = user32.CreateWindowExW(
        0, "COMBOBOX", "",
        WS_CHILD | WS_VISIBLE | WS_TABSTOP | CBS_DROPDOWNLIST,
        100, 108, 200, 200,
        hwnd_main, ID_CMB_MODEL, hInstance, None)

    current_model = CONFIG.get('model_name', 'qwen2.5:0.5b')
    global model_bufs
    model_bufs = []
    for i, model in enumerate(AVAILABLE_MODELS):
        buf = ctypes.create_unicode_buffer(model)
        model_bufs.append(buf)
        ptr_addr = ctypes.addressof(buf)
        user32.SendMessageW(hwnd_cmb_model, CB_ADDSTRING, 0, ptr_addr)
        if model == current_model:
            user32.SendMessageW(hwnd_cmb_model, CB_SETCURSEL, i, 0)

    user32.CreateWindowExW(
        0, "STATIC", "运行日志:",
        WS_CHILD | WS_VISIBLE,
        20, 155, 200, 28,
        hwnd_main, 0, hInstance, None)

    hwnd_log = user32.CreateWindowExW(
        0x200, "EDIT", "",
        WS_CHILD | WS_VISIBLE | WS_BORDER | WS_VSCROLL |
        ES_MULTILINE | ES_READONLY | ES_AUTOVSCROLL,
        20, 190, 750, 330,
        hwnd_main, 0, hInstance, None)

    user32.CreateWindowExW(
        0, "BUTTON", "退出程序",
        WS_CHILD | WS_VISIBLE | WS_TABSTOP,
        680, 540, 100, 32,
        hwnd_main, ID_BTN_EXIT, hInstance, None)

    hfont = gdi32.CreateFontW(
        16, 0, 0, 0, 400, 0, 0, 0,
        0x86, 0, 0, 0, 0, "微软雅黑")

    def set_font(hwnd):
        user32.SendMessageW(hwnd, WM_SETFONT, hfont, 0)

    for ctrl in [hwnd_lbl_ol, hwnd_lbl_web, hwnd_log, hwnd_cmb_model]:
        set_font(ctrl)

    def enum_child(hwnd, lparam):
        set_font(hwnd)
        return 1
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_ssize_t)
    user32.EnumChildWindows(hwnd_main, WNDENUMPROC(enum_child), 0)

    user32.SetTimer(hwnd_main, ID_TIMER, 3000, None)

    check_ollama()
    update_status_labels()
    update_log_text()

    user32.ShowWindow(hwnd_main, 1)
    user32.UpdateWindow(hwnd_main)

def update_status_labels():
    if State.ollama_running:
        text = "Ollama: 运行中"
    else:
        text = "Ollama: 未运行"
    user32.SetWindowTextW(hwnd_lbl_ol, text)

    if State.web_running:
        text = "Web服务: 运行中"
    else:
        text = "Web服务: 未启动"
    user32.SetWindowTextW(hwnd_lbl_web, text)

def update_log_text():
    if not State.logs or len(State.logs) == State.last_log_count:
        return
    State.last_log_count = len(State.logs)
    text = "\r\n".join(State.logs[-50:])
    user32.SetWindowTextW(hwnd_log, text)
    user32.SendMessageW(hwnd_log, EM_SETSEL, -1, -1)
    user32.SendMessageW(hwnd_log, EM_SCROLLCARET, 0, 0)

def main():
    State.log("Veyra助手启动中...")
    State.log(f"模型目录: {MODELS_DIR}")
    State.log(f"默认模型: {CONFIG.get('model_name', 'qwen2.5:0.5b')}")

    create_window()

    if CONFIG.get('auto_start', True):
        State.log("自动启动服务...")
        def auto_start():
            start_ollama()
            time.sleep(5)
            start_web()
        threading.Thread(target=auto_start, daemon=True).start()

    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))

    State.should_exit = True
    stop_web()
    stop_ollama()
    State.log("程序已退出")

if __name__ == "__main__":
    main()
