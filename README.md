# Veyra 旧版客户端（部分开源）

这是 Veyra 助手**旧版本**的客户端源码，仅存档公开，用于学习参考。

> 说明：这里只是「一部分」——新版的服务端（`veyra_server.py`）、云端账号体系、外网隧道、打包脚本均未包含。

## 包含内容

| 文件 | 作用 |
|---|---|
| `veyra_gui.py` | 桌面客户端：Windows 原生窗口、对话气泡、托盘 |
| `veyra_admin.py` | Web 管理界面：浏览器打开 `http://localhost:9999`，管理服务、查看状态、选模型 |
| `gpu_ai_system.py` | 旧版核心：本地 Ollama 对话、记忆、网页服务 |

## 运行前提

- Python 3.9+
- 本机已装 Ollama，并拉取任意模型（例如 `ollama pull qwen2.5:1.5b`）
- 依赖：`pip install -r requirements.txt`

```bash
python gpu_ai_system.py      # 直接跑核心
python veyra_admin.py        # 跑管理界面（浏览器访问 localhost:9999）
python veyra_gui.py          # 跑桌面客户端
```

## 注意

- 这是旧代码，目录结构、配置字段与当前版本**不一致**，不保证开箱即用。
- 代码里没有任何账号密钥、云服务密钥或个人数据。
- 请自备 `config.json`（可参考 `config.example.json` 自行填写模型名与端口）。

## 许可证

**PolyForm Noncommercial License 1.0.0** —— 可以自由使用、修改、分享，**但不能用于商业用途**。
全文见 [LICENSE](LICENSE)。

Required Notice: Copyright (c) 2026 zhengmingrui1030

## 免责

代码按「现状」提供，不附带任何担保。使用产生的任何后果由使用者自行承担。
