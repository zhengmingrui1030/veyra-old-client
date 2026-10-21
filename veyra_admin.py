# 作用：旧版 Web 管理界面（浏览器打开 localhost:9999 管服务、看状态、选模型）
# 调用关系：独立运行，调用 veyra_server.py 启动/停止；不依赖 veyra_gui.py
# 版权：Copyright (c) 2026 zhengmingrui1030，许可见 LICENSE（PolyForm Noncommercial 1.0.0）

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Veyra助手 - Web管理界面
提供图形化的服务管理、状态监控、模型选择等功能
运行后打开浏览器访问 http://localhost:9999
"""

import http.server
import socketserver
import threading
import subprocess
import os
import sys
import json
import time
import webbrowser
import requests

# ========== 路径配置 ==========
if getattr(sys, 'frozen', False):
    SCRIPT_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)

CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")
RUNTIME_DIR = os.path.join(BASE_DIR, "运行时")
MODELS_DIR = os.path.join(BASE_DIR, "模型")
os.makedirs(RUNTIME_DIR, exist_ok=True)

DEFAULT_CONFIG = {
    "model_name": "qwen2.5:3b",
    "ollama_base_url": "http://localhost:11434",
    "server_port": 8080,
}

def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                return {**DEFAULT_CONFIG, **json.load(f)}
        except:
            pass
    return DEFAULT_CONFIG.copy()

def save_config(cfg):
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

CONFIG = load_config()

# ========== 全局状态 ==========
class State:
    ollama_running = False
    web_running = False
    ollama_process = None
    web_process = None
    available_models = []
    logs = []
    
    @classmethod
    def add_log(cls, msg):
        timestamp = time.strftime("%H:%M:%S")
        cls.logs.append(f"[{timestamp}] {msg}")
        if len(cls.logs) > 100:
            cls.logs = cls.logs[-100:]

# ========== Ollama管理 ==========
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

def start_ollama():
    State.add_log("正在启动Ollama服务...")
    ollama_exe = find_ollama_exe()
    if not ollama_exe:
        State.add_log("错误: 未找到ollama.exe")
        return False
    State.add_log(f"使用: {ollama_exe}")
    env = os.environ.copy()
    env["OLLAMA_MODELS"] = MODELS_DIR
    env["OLLAMA_NUM_GPUS"] = "0"
    try:
        State.ollama_process = subprocess.Popen(
            [ollama_exe, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        )
        State.add_log("Ollama服务已启动")
        return True
    except Exception as e:
        State.add_log(f"启动失败: {e}")
        return False

def stop_ollama():
    State.add_log("正在停止Ollama服务...")
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/IM", "ollama.exe"],
                      capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    State.ollama_running = False
    State.add_log("Ollama服务已停止")

def check_ollama():
    try:
        response = requests.get(f"{CONFIG['ollama_base_url']}/api/tags", timeout=2)
        State.ollama_running = response.status_code == 200
    except:
        State.ollama_running = False

def get_models():
    try:
        response = requests.get(f"{CONFIG['ollama_base_url']}/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get("models", [])
            State.available_models = [m["name"] for m in models]
            return State.available_models
    except:
        pass
    return []

# ========== Web服务管理 ==========
def start_web():
    State.add_log("正在启动Web服务...")
    main_script = os.path.join(SCRIPT_DIR, "veyra_server.py")
    if not os.path.exists(main_script):
        for drive in "DEFGHIJKLMNOPQRSTUVWXYZ":
            alt_path = f"{drive}:/Veyra/代码/veyra_server.py"
            if os.path.exists(alt_path):
                main_script = alt_path
                break
    if not os.path.exists(main_script):
        State.add_log("错误: 未找到主程序")
        return False
    env = os.environ.copy()
    env["OLLAMA_MODELS"] = MODELS_DIR
    try:
        State.web_process = subprocess.Popen(
            [sys.executable, main_script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            cwd=os.path.dirname(main_script),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        )
        State.web_running = True
        State.add_log(f"Web服务已启动 (端口: {CONFIG.get('server_port', 8080)})")
        return True
    except Exception as e:
        State.add_log(f"启动失败: {e}")
        return False

def stop_web():
    State.add_log("正在停止Web服务...")
    if State.web_process:
        State.web_process.terminate()
        try:
            State.web_process.wait(timeout=5)
        except:
            State.web_process.kill()
    State.web_running = False
    State.add_log("Web服务已停止")

# ========== HTTP管理服务 ==========
HTML_PAGE = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Veyra管理面板</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Microsoft YaHei", sans-serif; background: #f5f5f5; padding: 20px; }
        .container { max-width: 800px; margin: 0 auto; }
        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 12px; margin-bottom: 20px; text-align: center; }
        .header h1 { font-size: 28px; margin-bottom: 10px; }
        .header p { opacity: 0.9; }
        .card { background: white; border-radius: 12px; padding: 20px; margin-bottom: 15px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .card h2 { font-size: 18px; margin-bottom: 15px; color: #333; border-bottom: 1px solid #eee; padding-bottom: 10px; }
        .status-row { display: flex; align-items: center; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid #f0f0f0; }
        .status-row:last-child { border-bottom: none; }
        .status-label { font-weight: 500; }
        .status-value { display: flex; align-items: center; gap: 10px; }
        .badge { padding: 4px 12px; border-radius: 20px; font-size: 13px; font-weight: 500; }
        .badge.running { background: #e8f5e9; color: #2e7d32; }
        .badge.stopped { background: #ffebee; color: #c62828; }
        .btn { padding: 8px 16px; border: none; border-radius: 6px; cursor: pointer; font-size: 14px; transition: all 0.2s; }
        .btn-start { background: #4caf50; color: white; }
        .btn-start:hover { background: #43a047; }
        .btn-stop { background: #f44336; color: white; }
        .btn-stop:hover { background: #e53935; }
        .btn-action { background: #2196f3; color: white; }
        .btn-action:hover { background: #1e88e5; }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .model-select { padding: 8px 12px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px; min-width: 200px; }
        .quick-actions { display: flex; gap: 10px; flex-wrap: wrap; }
        .log-area { background: #1e1e1e; color: #00ff00; padding: 15px; border-radius: 8px; font-family: "Consolas", monospace; font-size: 13px; height: 200px; overflow-y: auto; }
        .log-area .time { color: #888; }
        .footer { text-align: center; padding: 20px; color: #666; font-size: 13px; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        .updating { animation: pulse 1s infinite; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🤖 Veyra助手</h1>
            <p>管理面板 v8.6.0</p>
        </div>
        
        <div class="card">
            <h2>📊 服务状态</h2>
            <div class="status-row">
                <span class="status-label">Ollama服务</span>
                <div class="status-value">
                    <span id="ollama-status" class="badge stopped">检测中...</span>
                    <button id="ollama-btn" class="btn btn-start" onclick="toggleOllama()">启动</button>
                </div>
            </div>
            <div class="status-row">
                <span class="status-label">Web服务</span>
                <div class="status-value">
                    <span id="web-status" class="badge stopped">未启动</span>
                    <button id="web-btn" class="btn btn-start" onclick="toggleWeb()">启动</button>
                    <button id="browser-btn" class="btn btn-action" onclick="openBrowser()" disabled>打开界面</button>
                </div>
            </div>
        </div>
        
        <div class="card">
            <h2>🎯 模型设置</h2>
            <div class="status-row">
                <span class="status-label">当前模型</span>
                <div class="status-value">
                    <select id="model-select" class="model-select">
                        <option value="">加载中...</option>
                    </select>
                    <button class="btn btn-action" onclick="refreshModels()">刷新</button>
                    <button class="btn btn-action" onclick="applyModel()">应用</button>
                </div>
            </div>
        </div>
        
        <div class="card">
            <h2>⚡ 快捷操作</h2>
            <div class="quick-actions">
                <button class="btn btn-start" onclick="startAll()">🚀 一键启动全部</button>
                <button class="btn btn-stop" onclick="stopAll()">⏹️ 一键停止全部</button>
                <button class="btn btn-action" onclick="openModelsDir()">📁 打开模型目录</button>
            </div>
        </div>
        
        <div class="card">
            <h2>📝 运行日志</h2>
            <div id="log-area" class="log-area">
                <span class="time">[系统]</span> 管理面板已启动...
            </div>
        </div>
        
        <div class="footer">
            <p>服务端口: <span id="server-port">8080</span> | 模型目录: <span id="models-dir">加载中...</span></p>
        </div>
    </div>
    
    <script>
        let ollamaRunning = false;
        let webRunning = false;
        
        async function fetchAPI(action) {
            try {
                const response = await fetch('/api/' + action);
                return await response.json();
            } catch (e) {
                console.error('API error:', e);
                return { error: e.message };
            }
        }
        
        async function updateStatus() {
            const data = await fetchAPI('status');
            ollamaRunning = data.ollama_running;
            webRunning = data.web_running;
            
            const ollamaStatus = document.getElementById('ollama-status');
            const ollamaBtn = document.getElementById('ollama-btn');
            ollamaStatus.textContent = ollamaRunning ? '运行中' : '未运行';
            ollamaStatus.className = 'badge ' + (ollamaRunning ? 'running' : 'stopped');
            ollamaBtn.textContent = ollamaRunning ? '停止' : '启动';
            ollamaBtn.className = 'btn ' + (ollamaRunning ? 'btn-stop' : 'btn-start');
            
            const webStatus = document.getElementById('web-status');
            const webBtn = document.getElementById('web-btn');
            const browserBtn = document.getElementById('browser-btn');
            webStatus.textContent = webRunning ? '运行中' : '未启动';
            webStatus.className = 'badge ' + (webRunning ? 'running' : 'stopped');
            webBtn.textContent = webRunning ? '停止' : '启动';
            webBtn.className = 'btn ' + (webRunning ? 'btn-stop' : 'btn-start');
            browserBtn.disabled = !webRunning;
            
            if (data.logs) {
                const logArea = document.getElementById('log-area');
                logArea.innerHTML = data.logs.map(l => `<div>${l}</div>`).join('');
                logArea.scrollTop = logArea.scrollHeight;
            }
            
            if (data.models) {
                const select = document.getElementById('model-select');
                select.innerHTML = data.models.map(m => `<option value="${m}">${m}</option>`).join('');
                if (data.current_model) {
                    select.value = data.current_model;
                }
            }
            
            if (data.server_port) document.getElementById('server-port').textContent = data.server_port;
            if (data.models_dir) document.getElementById('models-dir').textContent = data.models_dir;
        }
        
        async function toggleOllama() {
            if (ollamaRunning) {
                await fetchAPI('ollama/stop');
            } else {
                await fetchAPI('ollama/start');
            }
            setTimeout(updateStatus, 1000);
        }
        
        async function toggleWeb() {
            if (webRunning) {
                await fetchAPI('web/stop');
            } else {
                await fetchAPI('web/start');
            }
            setTimeout(updateStatus, 1000);
        }
        
        async function startAll() {
            await fetchAPI('ollama/start');
            await new Promise(r => setTimeout(r, 3000));
            await fetchAPI('web/start');
            setTimeout(updateStatus, 1000);
        }
        
        async function stopAll() {
            await fetchAPI('web/stop');
            await fetchAPI('ollama/stop');
            setTimeout(updateStatus, 500);
        }
        
        async function refreshModels() {
            await fetchAPI('models/refresh');
            setTimeout(updateStatus, 500);
        }
        
        async function applyModel() {
            const model = document.getElementById('model-select').value;
            if (model) {
                await fetchAPI('model/apply?name=' + encodeURIComponent(model));
            }
        }
        
        async function openBrowser() {
            await fetchAPI('browser/open');
        }
        
        async function openModelsDir() {
            await fetchAPI('models/open-dir');
        }
        
        updateStatus();
        setInterval(updateStatus, 3000);
    </script>
</body>
</html>'''

class AdminHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode('utf-8'))
        elif self.path.startswith('/api/'):
            self.handle_api(self.path[5:])
        else:
            self.send_error(404)
    
    def handle_api(self, action):
        result = {}
        try:
            if action == 'status':
                check_ollama()
                result = {
                    'ollama_running': State.ollama_running,
                    'web_running': State.web_running,
                    'logs': State.logs[-20:],
                    'models': State.available_models,
                    'current_model': CONFIG.get('model_name', ''),
                    'server_port': CONFIG.get('server_port', 8080),
                    'models_dir': MODELS_DIR,
                }
            elif action == 'ollama/start':
                result = {'success': start_ollama()}
            elif action == 'ollama/stop':
                stop_ollama()
                result = {'success': True}
            elif action == 'web/start':
                result = {'success': start_web()}
            elif action == 'web/stop':
                stop_web()
                result = {'success': True}
            elif action == 'models/refresh':
                get_models()
                result = {'success': True, 'models': State.available_models}
            elif action.startswith('model/apply'):
                import urllib.parse
                params = urllib.parse.parse_qs(action.split('?')[1] if '?' in action else '')
                model_name = params.get('name', [''])[0]
                if model_name:
                    CONFIG['model_name'] = model_name
                    save_config(CONFIG)
                    State.add_log(f"已切换模型: {model_name}")
                    result = {'success': True}
            elif action == 'browser/open':
                port = CONFIG.get('server_port', 8080)
                webbrowser.open(f"http://localhost:{port}")
                result = {'success': True}
            elif action == 'models/open-dir':
                if os.path.exists(MODELS_DIR) and os.name == "nt":
                    os.startfile(MODELS_DIR)
                result = {'success': True}
        except Exception as e:
            result = {'error': str(e)}
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(result).encode('utf-8'))

def main():
    PORT = 9999
    State.add_log("管理面板启动中...")
    State.add_log(f"访问地址: http://localhost:{PORT}")
    
    with socketserver.TCPServer(("", PORT), AdminHandler) as httpd:
        webbrowser.open(f"http://localhost:{PORT}")
        print(f"Veyra管理面板运行中: http://localhost:{PORT}")
        httpd.serve_forever()

if __name__ == "__main__":
    main()
