"""เปิด dashboard ผ่าน server ในเครื่อง เพื่อให้ปุ่ม Update ในหน้าเว็บดึงข้อมูลใหม่ได้

รัน:  python3 dashboard/serve.py   แล้วเปิด http://127.0.0.1:8765
ผูกกับ 127.0.0.1 เท่านั้น (ไม่เปิดให้เครื่องอื่นเข้า) ใช้แค่ standard library
การอัปเดตรันเบื้องหลัง หน้าเว็บถามความคืบหน้าจาก GET /status
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import build_dashboard

HOST, PORT = "127.0.0.1", 8765
state = {"running": False, "done": 0, "total": 0, "error": None, "finished": None}
state_lock = threading.Lock()


def run_update():
    def progress(done, total):
        state.update(done=done, total=total)

    try:
        payload = build_dashboard.build(progress=progress)
        state.update(error=None, finished=payload["accessed"])
    except Exception as e:  # เก็บสาเหตุไว้ให้หน้าเว็บแสดง ไม่ปล่อยให้เธรดตายเงียบ ๆ
        state.update(error=str(e)[:200])
    finally:
        state["running"] = False


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json")

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            if not build_dashboard.HTML_FILE.exists():
                with state_lock:
                    if not state["running"]:
                        build_dashboard.build()
            self._send(200, build_dashboard.HTML_FILE.read_bytes(), "text/html; charset=utf-8")
        elif path == "/status":
            self._json(200, state)
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self):
        # กันเว็บอื่นยิงมาที่ server นี้: รับเฉพาะคำขอที่มาจากหน้าเดียวกันหรือไม่มี Origin
        origin = self.headers.get("Origin")
        if origin and origin != f"http://{HOST}:{PORT}":
            return self._json(403, {"error": "forbidden origin"})
        if self.path != "/update":
            return self._send(404, b"not found", "text/plain")
        with state_lock:
            if state["running"]:
                return self._json(409, {"error": "กำลังอัปเดตอยู่"})
            state.update(running=True, done=0, total=0, error=None)
        threading.Thread(target=run_update, daemon=True).start()
        self._json(202, {"started": True})

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))


if __name__ == "__main__":
    print(f"Dashboard: http://{HOST}:{PORT}  (Ctrl+C เพื่อหยุด)")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
