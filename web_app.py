#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

import netkeiba_objective_summary as core


MAX_REQUEST_BYTES = 64 * 1024


INDEX_HTML = """\
<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>netkeiba 客観情報サマリー</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --line: #d9dee7;
      --text: #17202c;
      --muted: #667085;
      --accent: #0f766e;
      --accent-strong: #115e59;
      --danger: #b42318;
      --warning: #9a6700;
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.5;
    }

    main {
      width: min(1160px, calc(100% - 32px));
      margin: 0 auto;
      padding: 28px 0 40px;
    }

    header {
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      gap: 20px;
      margin-bottom: 20px;
      border-bottom: 1px solid var(--line);
      padding-bottom: 16px;
    }

    h1 {
      margin: 0;
      font-size: 26px;
      font-weight: 700;
      letter-spacing: 0;
    }

    .status {
      color: var(--muted);
      font-size: 13px;
      white-space: nowrap;
    }

    .layout {
      display: grid;
      grid-template-columns: minmax(300px, 380px) minmax(0, 1fr);
      gap: 20px;
      align-items: start;
    }

    section {
      min-width: 0;
    }

    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
    }

    form {
      display: grid;
      gap: 14px;
    }

    label {
      display: grid;
      gap: 6px;
      font-size: 13px;
      font-weight: 600;
      color: #344054;
    }

    input,
    select {
      width: 100%;
      border: 1px solid #c8d0dc;
      border-radius: 6px;
      background: #fff;
      color: var(--text);
      font: inherit;
      min-height: 40px;
      padding: 8px 10px;
    }

    input:focus,
    select:focus,
    button:focus {
      outline: 3px solid rgba(15, 118, 110, 0.22);
      outline-offset: 1px;
    }

    .grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }

    .actions {
      display: flex;
      gap: 10px;
      align-items: center;
      margin-top: 4px;
    }

    button {
      border: 1px solid var(--accent);
      border-radius: 6px;
      background: var(--accent);
      color: #fff;
      font: inherit;
      font-weight: 700;
      min-height: 42px;
      padding: 9px 14px;
      cursor: pointer;
    }

    button:hover {
      background: var(--accent-strong);
      border-color: var(--accent-strong);
    }

    button:disabled {
      cursor: not-allowed;
      opacity: 0.65;
    }

    .hint {
      color: var(--muted);
      font-size: 12px;
      font-weight: 400;
    }

    .message {
      border-radius: 6px;
      padding: 10px 12px;
      font-size: 13px;
      border: 1px solid var(--line);
      background: #f9fafb;
      color: #344054;
    }

    .message.error {
      border-color: #fecdca;
      background: #fff4f2;
      color: var(--danger);
    }

    .message.loading {
      border-color: #a7f3d0;
      background: #ecfdf3;
      color: #065f46;
    }

    .result-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-bottom: 14px;
    }

    h2 {
      margin: 0;
      font-size: 18px;
      letter-spacing: 0;
    }

    h3 {
      margin: 24px 0 10px;
      font-size: 15px;
      letter-spacing: 0;
    }

    .summary-list {
      display: grid;
      gap: 10px;
      padding: 0;
      margin: 0;
      list-style: none;
    }

    .summary-item {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #fff;
    }

    .summary-item strong {
      display: block;
      margin-bottom: 4px;
    }

    .meta {
      margin-top: 8px;
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      color: var(--muted);
      font-size: 12px;
    }

    .pill {
      border: 1px solid #c8d0dc;
      border-radius: 999px;
      padding: 2px 8px;
      background: #f9fafb;
    }

    .caveat {
      margin-top: 8px;
      color: var(--warning);
      font-size: 13px;
    }

    .plain-list {
      margin: 0;
      padding-left: 1.2em;
    }

    details {
      margin-top: 18px;
      border-top: 1px solid var(--line);
      padding-top: 14px;
    }

    summary {
      cursor: pointer;
      color: var(--muted);
      font-weight: 600;
    }

    pre {
      overflow: auto;
      max-height: 360px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 12px;
      background: #0b1020;
      color: #e6edf7;
      font-size: 12px;
      line-height: 1.55;
    }

    .empty {
      min-height: 320px;
      display: grid;
      place-items: center;
      color: var(--muted);
      text-align: center;
      border: 1px dashed #c8d0dc;
      border-radius: 8px;
      background: #fff;
      padding: 24px;
    }

    @media (max-width: 840px) {
      main {
        width: min(100% - 20px, 720px);
        padding-top: 18px;
      }

      header,
      .layout,
      .grid {
        grid-template-columns: 1fr;
      }

      header {
        display: grid;
        align-items: start;
      }

      .status {
        white-space: normal;
      }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <h1>netkeiba 客観情報サマリー</h1>
      <div class="status" id="envStatus"></div>
    </header>

    <div class="layout">
      <section class="panel">
        <form id="summaryForm">
          <label>
            掲示板URL
            <input id="url" name="url" type="url" required placeholder="https://db.netkeiba.com/?pid=horse_board&id=...">
          </label>

          <label>
            APIキー
            <input id="apiKey" name="apiKey" type="password" autocomplete="off" placeholder="OPENAI_API_KEYを使う場合は空欄">
            <span class="hint">入力したキーはこのリクエストだけで使います。</span>
          </label>

          <div class="grid">
            <label>
              並び順
              <select id="sort" name="sort">
                <option value="">ページ既定</option>
                <option value="recent">新着順</option>
                <option value="like">いいね順</option>
              </select>
            </label>

            <label>
              ページ数
              <input id="pages" name="pages" type="number" min="1" max="5" value="1">
            </label>
          </div>

          <div class="grid">
            <label>
              最大コメント数
              <input id="maxComments" name="maxComments" type="number" min="1" max="120" value="60">
            </label>

            <label>
              モデル
              <input id="model" name="model" value="__MODEL__">
            </label>
          </div>

          <label>
            API Base URL
            <input id="baseUrl" name="baseUrl" value="__BASE_URL__">
          </label>

          <div class="actions">
            <button id="submitButton" type="submit">要約する</button>
            <span class="hint" id="requestMeta"></span>
          </div>

          <div id="message" class="message" hidden></div>
        </form>
      </section>

      <section id="resultRoot">
        <div class="empty">掲示板URLを入力して要約を実行してください。</div>
      </section>
    </div>
  </main>

  <script>
    const config = __CONFIG__;
    const form = document.getElementById("summaryForm");
    const button = document.getElementById("submitButton");
    const message = document.getElementById("message");
    const resultRoot = document.getElementById("resultRoot");
    const requestMeta = document.getElementById("requestMeta");
    const envStatus = document.getElementById("envStatus");

    envStatus.textContent = config.envKeyAvailable
      ? "OPENAI_API_KEY: 設定済み"
      : "OPENAI_API_KEY: 未設定";

    function setMessage(text, type = "") {
      message.hidden = !text;
      message.textContent = text;
      message.className = "message" + (type ? " " + type : "");
    }

    function escapeHtml(value) {
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }

    function renderIds(ids) {
      if (!Array.isArray(ids) || ids.length === 0) return "";
      return ids.map((id) => "#" + escapeHtml(id)).join(", ");
    }

    function renderSummary(data) {
      const summary = data.summary || {};
      const source = summary.source || {};
      const objective = Array.isArray(summary.objective_summary)
        ? summary.objective_summary
        : [];
      const uncertain = Array.isArray(summary.uncertain_or_subjective)
        ? summary.uncertain_or_subjective
        : [];
      const noise = Array.isArray(summary.excluded_noise)
        ? summary.excluded_noise
        : [];

      let html = `
        <div class="panel">
          <div class="result-header">
            <h2>結果</h2>
            <span class="hint">${escapeHtml(source.comments_used ?? data.commentsUsed ?? "")} comments</span>
          </div>
          <h3>採用した客観寄りの情報</h3>
      `;

      if (objective.length === 0) {
        html += `<p class="message">採用できる客観寄りの情報は見つかりませんでした。</p>`;
      } else {
        html += `<ul class="summary-list">`;
        for (const item of objective) {
          const evidence = renderIds(item.evidence_comment_ids);
          html += `
            <li class="summary-item">
              <strong>${escapeHtml(item.topic || "項目")}</strong>
              <div>${escapeHtml(item.summary || "")}</div>
              <div class="meta">
                ${item.objectivity ? `<span class="pill">客観性: ${escapeHtml(item.objectivity)}</span>` : ""}
                ${evidence ? `<span class="pill">根拠: ${evidence}</span>` : ""}
              </div>
              ${item.caveat ? `<div class="caveat">注意: ${escapeHtml(item.caveat)}</div>` : ""}
            </li>
          `;
        }
        html += `</ul>`;
      }

      if (uncertain.length > 0) {
        html += `<h3>未確認・主観寄りとして扱う情報</h3><ul class="summary-list">`;
        for (const item of uncertain) {
          const ids = renderIds(item.comment_ids);
          html += `
            <li class="summary-item">
              <strong>${escapeHtml(item.claim || "")}</strong>
              <div>${escapeHtml(item.reason || "")}</div>
              ${ids ? `<div class="meta"><span class="pill">${ids}</span></div>` : ""}
            </li>
          `;
        }
        html += `</ul>`;
      }

      if (noise.length > 0) {
        html += `<h3>除外した傾向</h3><ul class="plain-list">`;
        for (const item of noise) {
          html += `<li>${escapeHtml(item)}</li>`;
        }
        html += `</ul>`;
      }

      if (summary.overall_note) {
        html += `<h3>注意</h3><p>${escapeHtml(summary.overall_note)}</p>`;
      }

      html += `
          <details>
            <summary>JSON</summary>
            <pre>${escapeHtml(JSON.stringify(summary, null, 2))}</pre>
          </details>
        </div>
      `;
      resultRoot.innerHTML = html;
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      setMessage("取得と要約を実行中です。コメント数やモデルにより少し時間がかかります。", "loading");
      requestMeta.textContent = "";
      button.disabled = true;

      const payload = {
        url: document.getElementById("url").value.trim(),
        apiKey: document.getElementById("apiKey").value.trim(),
        sort: document.getElementById("sort").value,
        pages: Number(document.getElementById("pages").value),
        maxComments: Number(document.getElementById("maxComments").value),
        model: document.getElementById("model").value.trim(),
        baseUrl: document.getElementById("baseUrl").value.trim()
      };

      try {
        const startedAt = Date.now();
        const response = await fetch("/api/summarize", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.error || "Request failed");
        }
        const seconds = ((Date.now() - startedAt) / 1000).toFixed(1);
        requestMeta.textContent = `${seconds}s`;
        setMessage("");
        renderSummary(data);
      } catch (error) {
        setMessage(error.message || String(error), "error");
      } finally {
        button.disabled = false;
      }
    });
  </script>
</body>
</html>
"""


def int_between(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def clean_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def validate_netkeiba_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("http または https の netkeiba URL を指定してください。")
    if not parsed.netloc.endswith("netkeiba.com"):
        raise ValueError("netkeiba.com の掲示板URLを指定してください。")
    return value


def summarize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    url = validate_netkeiba_url(clean_text(payload.get("url")))
    api_key = clean_text(payload.get("apiKey")) or os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError("APIキーを入力するか、サーバー起動前に OPENAI_API_KEY を設定してください。")

    sort = clean_text(payload.get("sort")) or None
    if sort not in {None, "recent", "like"}:
        raise ValueError("sort は recent / like / 空欄のいずれかにしてください。")

    pages = int_between(payload.get("pages"), default=1, minimum=1, maximum=5)
    max_comments = int_between(payload.get("maxComments"), default=60, minimum=1, maximum=120)
    model = clean_text(payload.get("model"), core.DEFAULT_MODEL) or core.DEFAULT_MODEL
    base_url = clean_text(payload.get("baseUrl"), core.DEFAULT_BASE_URL) or core.DEFAULT_BASE_URL

    comments = core.fetch_board_comments(
        url,
        pages=pages,
        max_comments=max_comments,
        sort=sort,
        delay=0.7,
    )
    if not comments:
        raise ValueError("利用できるコメントが見つかりませんでした。")

    model_comments, serialized_size = core.prepare_model_comments(
        comments,
        max_comments=max_comments,
        max_input_chars=24000,
    )
    if not model_comments:
        raise ValueError("コメントが長すぎてモデル入力に収まりませんでした。")

    summary = core.request_objective_summary(
        api_key=api_key,
        base_url=base_url,
        model=model,
        source_url=url,
        comments=model_comments,
        max_output_tokens=1400,
    )
    summary.setdefault("source", {})
    summary["source"]["url"] = url
    summary["source"]["comments_used"] = len(model_comments)
    summary["source"]["fetched_comments"] = len(comments)
    summary["source"]["serialized_comment_chars"] = serialized_size

    return {
        "summary": summary,
        "markdown": core.render_markdown(summary),
        "commentsUsed": len(model_comments),
    }


class AppHandler(BaseHTTPRequestHandler):
    server_version = "NetkeibaObjectiveSummary/0.1"

    def send_index(self, *, include_body: bool) -> None:
        html = INDEX_HTML.replace("__MODEL__", core.DEFAULT_MODEL)
        html = html.replace("__BASE_URL__", core.DEFAULT_BASE_URL)
        config = {"envKeyAvailable": bool(os.environ.get("OPENAI_API_KEY"))}
        html = html.replace("__CONFIG__", json.dumps(config, ensure_ascii=False))
        body = html.encode("utf-8")

        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if include_body:
            self.wfile.write(body)

    def send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path not in {"/", "/index.html"}:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            return

        self.send_index(include_body=True)

    def do_HEAD(self) -> None:
        if self.path not in {"/", "/index.html"}:
            self.send_response(HTTPStatus.NOT_FOUND.value)
            self.end_headers()
            return

        self.send_index(include_body=False)

    def do_POST(self) -> None:
        if self.path != "/api/summarize":
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            return

        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_REQUEST_BYTES:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "リクエストサイズが不正です。"})
            return

        stderr = io.StringIO()
        try:
            with contextlib.redirect_stderr(stderr):
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("JSON オブジェクトを送信してください。")
                result = summarize_payload(payload)
        except SystemExit:
            detail = stderr.getvalue().strip() or "処理中にエラーが発生しました。"
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": detail})
            return
        except Exception as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return

        self.send_json(HTTPStatus.OK, result)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local web UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), AppHandler)
    print(f"Serving on http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
