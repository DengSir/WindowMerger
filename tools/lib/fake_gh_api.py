# -*- coding: utf-8 -*-
"""本地假 GitHub releases/latest 服务：update_e2e / update_edge 共用。
被测宿主经 WM_UPDATE_API 指过来（src/Updater.cs 的测试钩子），asset 下载地址取
JSON 里的 browser_download_url——两种场景（发现新版本 / 无更新 / 404 / 坏发布物）
只需换 configure() 参数，不用动服务。纯 stdlib，127.0.0.1 随机端口，不碰真实 API。
"""
from __future__ import annotations

import http.server
import json
import threading


class FakeGitHubApi:
    def __init__(self) -> None:
        self.api_hits = 0
        self.zip_hits = 0
        self._status = 200
        self._tag = "v9.9.9"
        self._assets: list[dict] = []          # [{"name": ..., "bytes": ...}]
        self._srv: http.server.ThreadingHTTPServer | None = None
        self.port = 0

    # ---------- 配置（可在运行中随时改，下一次请求即生效） ----------

    def configure(self, *, status: int = 200, tag: str = "v9.9.9",
                  assets: list[tuple[str, bytes]] | None = None) -> None:
        """status=404 模拟无 Release；assets=None → 空资产（异常发布物→按无更新）；
        asset name 必须以 -win-x64.zip 结尾才会被宿主认作更新包（Updater 同款规则）。"""
        self._status = status
        self._tag = tag
        self._assets = [{"name": n, "bytes": b} for n, b in (assets or [])]

    # ---------- 生命周期 ----------

    def start(self) -> None:
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path.startswith("/releases/latest"):
                    outer.api_hits += 1
                    print("UPDATE_API_HIT", flush=True)
                    if outer._status != 200:
                        outer._send(self, outer._status, b"{}", "application/json")
                        return
                    assets = [{"name": a["name"],
                               "browser_download_url":
                                   f"http://127.0.0.1:{outer.port}/{a['name']}"}
                              for a in outer._assets]
                    body = json.dumps({"tag_name": outer._tag, "assets": assets}).encode()
                    outer._send(self, 200, body, "application/json")
                    return
                for a in outer._assets:
                    if self.path.startswith(f"/{a['name']}"):
                        outer.zip_hits += 1
                        print("UPDATE_ZIP_HIT", flush=True)
                        outer._send(self, 200, a["bytes"], "application/zip")
                        return
                outer._send(self, 404, b"{}", "application/json")

            def log_message(self, *a):  # 静默默认访问日志
                pass

        class _Srv(http.server.ThreadingHTTPServer):
            daemon_threads = True

        self._srv = _Srv(("127.0.0.1", 0), Handler)
        self.port = self._srv.server_address[1]
        threading.Thread(target=self._srv.serve_forever, daemon=True).start()

    def shutdown(self) -> None:
        if self._srv is not None:
            self._srv.shutdown()
            self._srv = None

    @staticmethod
    def _send(handler: http.server.BaseHTTPRequestHandler, code: int,
              body: bytes, ctype: str) -> None:
        handler.send_response(code)
        handler.send_header("Content-Type", ctype)
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)


def zip_bytes(entries: dict[str, bytes]) -> bytes:
    """内存打 zip（坏包场景用：不含 WindowMerger.exe entry / 任意垃圾）。"""
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return buf.getvalue()
