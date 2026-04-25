import asyncio
import ctypes
import ctypes.wintypes
import json
import logging
import threading
import sys

import uvicorn
import webview
import socket
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

# Configure logging to show startup issues
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

# Suppress pywebview's excessive logging but keep warnings
logging.getLogger('pywebview').setLevel(logging.CRITICAL)

import core.audio_engine as audio_engine

# ── Shared state ───────────────────────────────────────────────────────────────
app = FastAPI()
connected_clients: set[WebSocket] = set()
current_engine: str = "groq"
current_muted: bool = False

# Uvicorn's event loop — captured at startup so broadcast() can schedule
# sends on the correct loop from any thread.
_server_loop: asyncio.AbstractEventLoop = None

print("[main] Starting Interview Helper...", flush=True)


@app.on_event("startup")
async def _capture_loop():
    global _server_loop
    _server_loop = asyncio.get_running_loop()


@app.get("/")
def serve_ui():
    with open("web/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.websocket("/ws/ui")
async def ws_ui(websocket: WebSocket):
    global current_engine, current_muted
    print("[main] Client connected", flush=True)
    await websocket.accept()
    connected_clients.add(websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if msg.get("type") == "set_engine" and msg.get("value") in ("groq", "claude"):
                current_engine = msg["value"]
                print(f"[main] Engine switched to: {current_engine}", flush=True)
            elif msg.get("type") == "set_muted" and isinstance(msg.get("value"), bool):
                current_muted = msg["value"]
                print(f"[main] Muted: {current_muted}", flush=True)
                await _broadcast_impl(json.dumps({"type": "mute_state", "muted": current_muted}))
    except WebSocketDisconnect:
        print("[main] Client disconnected", flush=True)
        pass
    finally:
        connected_clients.discard(websocket)


async def _broadcast_impl(payload: str) -> None:
    """Runs on uvicorn's loop — safe to call send_text here."""
    dead = set()
    for client in list(connected_clients):
        try:
            await client.send_text(payload)
        except Exception:
            dead.add(client)
    connected_clients.difference_update(dead)


def broadcast(message: dict) -> None:
    """Thread-safe broadcast: schedules the send on uvicorn's event loop."""
    if _server_loop is None:
        print("[main] ⚠ broadcast called but _server_loop is None!", flush=True)
        return
    try:
        asyncio.run_coroutine_threadsafe(
            _broadcast_impl(json.dumps(message)), _server_loop
        )
    except Exception as e:
        print(f"[main] ⚠ broadcast error: {e}", flush=True)


# ── Everything below only runs when launched directly (not on import) ─────────
if __name__ == "__main__":

    def find_free_port():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('127.0.0.1', 0))
            return s.getsockname()[1]

    print("[main] Finding free port...", flush=True)
    app_port = find_free_port()
    print(f"[main] Using port: {app_port}", flush=True)
    
    print("[main] Starting uvicorn server...", flush=True)
    _config = uvicorn.Config(app, host="127.0.0.1", port=app_port, log_level="info")
    _server = uvicorn.Server(_config)
    threading.Thread(target=_server.run, daemon=True).start()

    # Give uvicorn a moment to bind to the port before loading the webview
    import time
    time.sleep(0.5)
    print("[main] ✓ Server started", flush=True)

    class _WindowAPI:
        def __init__(self):
            self.win = None
            self._hwnd = None

        def minimize(self):
            if self.win:
                self.win.minimize()

        def close(self):
            import os
            if self.win:
                try:
                    self.win.destroy()
                except Exception:
                    pass
            os._exit(0)

        def get_size(self):
            if self.win:
                return [self.win.width, self.win.height]
            return [420, 600]

        def get_position(self):
            if self.win:
                return [self.win.x, self.win.y]
            return [0, 0]

        def resize(self, width: int, height: int):
            if self.win:
                self.win.resize(max(320, width), max(350, height))

        def move_to(self, x: int, y: int):
            if self.win:
                self.win.move(x, y)

        def set_opacity(self, value: int):
            """value: 10–100. Sets window-level alpha."""
            if not self._hwnd:
                return
            GWL_EXSTYLE    = -20
            WS_EX_LAYERED  = 0x00080000
            LWA_ALPHA      = 0x00000002
            alpha = max(25, min(255, int(value * 255 / 100)))
            style = ctypes.windll.user32.GetWindowLongW(self._hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(self._hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED)
            ctypes.windll.user32.SetLayeredWindowAttributes(
                self._hwnd, 0, alpha, LWA_ALPHA
            )

    _api = _WindowAPI()

    print("[main] Creating webview window...", flush=True)
    window = webview.create_window(
        "Interview Copilot",
        f"http://127.0.0.1:{app_port}/",
        frameless=True,
        easy_drag=False,
        resizable=True,
        on_top=True,
        width=420,
        height=600,
        js_api=_api,
        background_color="#111111",
    )
    _api.win = window
    print("[main] ✓ Window created", flush=True)

    def apply_transparency(hwnd):
        import time
        time.sleep(0.5)
        GWL_EXSTYLE   = -20
        WS_EX_LAYERED = 0x00080000
        LWA_ALPHA     = 0x00000002
        try:
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED)
            ctypes.windll.user32.SetLayeredWindowAttributes(hwnd, 0, 237, LWA_ALPHA)
            ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x00000011)
            print("[main] Alpha transparency + Screen-capture exclusion applied safely.")
        except Exception as e:
            print(f"[main] Error applying transparency: {e}")

    def on_window_shown():
        ctypes.windll.user32.FindWindowW.restype = ctypes.wintypes.HWND
        hwnd = ctypes.windll.user32.FindWindowW(None, "Interview Copilot")
        if hwnd:
            _api._hwnd = hwnd
            threading.Thread(target=apply_transparency, args=(hwnd,), daemon=True).start()
        else:
            print("[main] HWND not found.")

    window.events.shown += on_window_shown

    def on_window_closed():
        _server.should_exit = True

    window.events.closed += on_window_closed

    def _start_audio():
        print("[main] Initializing audio thread...", flush=True)
        ctypes.windll.ole32.CoInitializeEx(None, 0x2)
        loop = asyncio.SelectorEventLoop()
        asyncio.set_event_loop(loop)
        try:
            print("[main] Running audio engine...", flush=True)
            loop.run_until_complete(audio_engine.run())
        except Exception as e:
            print(f"[main] Audio thread error: {e}", flush=True)
        finally:
            try:
                loop.run_until_complete(asyncio.sleep(0.1))
            except Exception:
                pass
            loop.close()
            ctypes.windll.ole32.CoUninitialize()
            print("[main] Audio thread ended", flush=True)

    print("[main] Starting audio thread...", flush=True)
    threading.Thread(target=_start_audio, daemon=True).start()

    print("[main] Starting webview...", flush=True)
    webview.start()
    print("[main] Application closed", flush=True)
