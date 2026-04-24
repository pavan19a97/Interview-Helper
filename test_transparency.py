import webview
import ctypes
import ctypes.wintypes

def on_shown():
    hwnd = ctypes.windll.user32.FindWindowW(None, "Test Transparency 2")
    if hwnd:
        # Try WDA_MONITOR (1) instead of WDA_EXCLUDEFROMCAPTURE (17)
        ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 1)

window = webview.create_window(
    "Test Transparency 2",
    html='<body style="background: rgba(0, 255, 0, 0.5); color: white;"><button onclick="alert(\'clicked\')">Click me</button></body>',
    transparent=True,
    frameless=True,
)

webview.start(on_shown)
