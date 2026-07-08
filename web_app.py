import asyncio
import json
import mimetypes
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)

import data_gather
import history_store_json as history_store


WEB_ROOT = ROOT / "web"
SHOP_LIST = ROOT / "shops.txt"
HOST = "127.0.0.1"
PORT = 8765
TASK_LOCK = threading.Lock()
TASK = {
    "status": "idle",
    "message": "等待任务",
    "events": [],
    "error": "",
}


def read_shops():
    if not SHOP_LIST.exists():
        return []
    return data_gather.parse_shop_list(SHOP_LIST)


def write_shops(shops):
    lines = []
    for shop in shops:
        name = str(shop.get("name", "")).strip()
        url = str(shop.get("url", "")).strip()
        if not name or not url.startswith("https://buyin.jinritemai.com/"):
            raise ValueError("每个店铺都需要名称和有效的百应达人主页网址")
        lines.append("{}\t{}".format(name, url))
    if not lines:
        raise ValueError("至少保留一个店铺")
    SHOP_LIST.write_text("\n".join(lines) + "\n", encoding="utf-8")


def selected_shop_names(query):
    value = query.get("shops", [""])[0]
    return [item for item in value.split(",") if item]


def task_snapshot():
    with TASK_LOCK:
        return dict(TASK, events=list(TASK["events"]))


def update_task(**changes):
    with TASK_LOCK:
        TASK.update(changes)


def record_progress(event):
    with TASK_LOCK:
        TASK["message"] = event.get("message", "")
        TASK["events"].append(event)
        TASK["events"] = TASK["events"][-80:]


def run_crawl(payload):
    try:
        shops_by_name = {shop["name"]: shop for shop in read_shops()}
        names = payload.get("shops") or list(shops_by_name)
        shops = [shops_by_name[name] for name in names if name in shops_by_name]
        if not shops:
            raise ValueError("没有选中可抓取的店铺")
        asyncio.run(
            data_gather.raw_capture_scene_products_for_shops(
                payload.get("cdp_url") or data_gather.CDP_URL,
                shops,
                start_date=payload.get("start_date", ""),
                end_date=payload.get("end_date", ""),
                max_live_pages=max(1, min(int(payload.get("max_pages") or 2), 50)),
                force=bool(payload.get("force")),
                progress=record_progress,
                export_after=False,
            )
        )
        update_task(status="complete", message="增量抓取完成", error="")
    except Exception as exc:
        data_gather.append_debug(f"web crawl failed: {type(exc).__name__}: {exc}")
        update_task(status="error", message="抓取失败", error=str(exc))


def chrome_status():
    try:
        with urllib.request.urlopen(data_gather.CDP_URL + "/json/list", timeout=1.5) as response:
            targets = json.loads(response.read().decode("utf-8"))
        buyin_pages = [
            target for target in targets
            if target.get("type") == "page" and "buyin.jinritemai.com" in target.get("url", "")
        ]
        return {"connected": True, "buyin_ready": bool(buyin_pages)}
    except Exception:
        return {"connected": False, "buyin_ready": False}


def start_debug_browser():
    current = chrome_status()
    if current["connected"]:
        return {"browser": "已运行的登录浏览器", **current}

    script = ROOT / "start_baiying_chrome_debug.cmd"
    if not script.exists():
        raise RuntimeError(f"Chrome 启动脚本不存在：{script}")
    try:
        os.startfile(str(script))
    except OSError as exc:
        raise RuntimeError(f"无法通过 Windows 桌面启动 Google Chrome：{exc}") from exc

    deadline = time.time() + 18
    while time.time() < deadline:
        status = chrome_status()
        if status["connected"]:
            return {"browser": "Google Chrome", **status}
        time.sleep(0.4)

    raise RuntimeError(
        "Google Chrome 未建立调试端口 9222。请关闭当前网页服务，然后双击 start_web_ui.bat 重新启动。"
    )


class AppHandler(BaseHTTPRequestHandler):
    server_version = "BaiyingHistory/1.0"

    def log_message(self, format, *args):
        return

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        if parsed.path == "/api/bootstrap":
            history_store.import_legacy_json_if_needed()
            self.send_json(
                {
                    "shops": read_shops(),
                    "summary": history_store.get_summary(),
                    "task": task_snapshot(),
                    "chrome": chrome_status(),
                    "today": date.today().isoformat(),
                    "default_start": (date.today() - timedelta(days=30)).isoformat(),
                }
            )
            return
        if parsed.path == "/api/records":
            start_date = query.get("start_date", [""])[0]
            end_date = query.get("end_date", [""])[0]
            shops = selected_shop_names(query)
            page = max(1, int(query.get("page", ["1"])[0]))
            page_size = max(20, min(200, int(query.get("page_size", ["50"])[0])))
            rows = history_store.query_records(start_date, end_date, shops or None)
            start = (page - 1) * page_size
            self.send_json(
                {
                    "rows": rows[start : start + page_size],
                    "total": len(rows),
                    "page": page,
                    "page_size": page_size,
                    "summary": history_store.get_summary(start_date, end_date, shops or None),
                }
            )
            return
        if parsed.path == "/api/task":
            self.send_json(task_snapshot())
            return
        if parsed.path == "/api/chrome":
            self.send_json(chrome_status())
            return
        if parsed.path == "/download/xlsx":
            requested = query.get("name", [""])[0]
            allowed = {
                data_gather.SCENE_PRODUCTS_XLSX.name: data_gather.SCENE_PRODUCTS_XLSX,
                data_gather.SCENE_PRODUCTS_XLSX_HD.name: data_gather.SCENE_PRODUCTS_XLSX_HD,
            }
            path = allowed.get(requested)
            if not path or not path.exists():
                self.send_error(404)
                return
            encoded_name = urllib.parse.quote(path.name)
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{encoded_name}")
            self.send_header("Content-Length", str(path.stat().st_size))
            self.end_headers()
            with path.open("rb") as file:
                shutil.copyfileobj(file, self.wfile, length=1024 * 1024)
            return
        self.serve_static(parsed.path)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        try:
            payload = self.read_json()
            if parsed.path == "/api/crawl":
                with TASK_LOCK:
                    if TASK["status"] == "running":
                        self.send_json({"error": "已有抓取任务正在运行"}, 409)
                        return
                    TASK.update(status="running", message="正在连接浏览器", events=[], error="")
                thread = threading.Thread(target=run_crawl, args=(payload,), daemon=True)
                thread.start()
                self.send_json({"ok": True, "task": task_snapshot()}, 202)
                return
            if parsed.path == "/api/shops":
                write_shops(payload.get("shops") or [])
                self.send_json({"ok": True, "shops": read_shops()})
                return
            if parsed.path == "/api/chrome/start":
                result = start_debug_browser()
                self.send_json({"ok": True, **result})
                return
            if parsed.path == "/api/export":
                rows = history_store.query_records(
                    payload.get("start_date", ""),
                    payload.get("end_date", ""),
                    payload.get("shops") or None,
                )
                output = data_gather.save_scene_products_xlsx(rows)
                if output is None:
                    raise RuntimeError("缺少 openpyxl 或 Pillow，请先安装依赖")
                self.send_json(
                    {
                        "ok": True,
                        "count": len(rows),
                        "download_url": "/download/xlsx?name=" + urllib.parse.quote(output.name),
                    }
                )
                return
            self.send_error(404)
        except (ValueError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, 400)
        except Exception as exc:
            data_gather.append_debug(f"web api failed: {parsed.path} {type(exc).__name__}: {exc}")
            self.send_json({"error": str(exc)}, 500)

    def serve_static(self, request_path):
        relative = "index.html" if request_path == "/" else request_path.lstrip("/")
        target = (WEB_ROOT / relative).resolve()
        if WEB_ROOT.resolve() not in target.parents and target != WEB_ROOT.resolve():
            self.send_error(403)
            return
        if not target.exists() or not target.is_file():
            self.send_error(404)
            return
        body = target.read_bytes()
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type + ("; charset=utf-8" if content_type.startswith("text/") else ""))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    history_store.import_legacy_json_if_needed()
    server = ThreadingHTTPServer((HOST, PORT), AppHandler)
    url = f"http://{HOST}:{PORT}"
    print("百应成交商品库：", url, flush=True)
    if "--no-open" not in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
