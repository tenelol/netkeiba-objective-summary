#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from html import unescape
from html.parser import HTMLParser
from typing import Any, NoReturn
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.iniad.org/api/v1")
DEFAULT_MODEL = os.environ.get("INIAD_OPENAI_MODEL", os.environ.get("OPENAI_MODEL", "gpt-5.4"))
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; netkeiba-objective-summary/0.1; "
    "+https://github.com/tenelol)"
)

SHOW_COMMENT_LIST_NAMES = [
    "show_id",
    "sort",
    "key",
    "repry_comment_url",
    "update_form_id",
    "max_length",
    "notify_title",
    "notify_url",
    "link_type",
    "link_url",
    "post_function",
    "report_url",
    "limit",
    "page",
    "like_comment_url",
    "category_cd",
    "version",
]


@dataclass(frozen=True)
class BoardComment:
    comment_id: str
    datetime: str
    text: str
    like_count: int


@dataclass(frozen=True)
class CommentListConfig:
    api_url: str
    params: dict[str, str]


class HtmlTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.ignored_stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self.ignored_stack.append(tag)
            return
        if tag in {"br", "p", "div", "li"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self.ignored_stack and self.ignored_stack[-1] == tag:
            self.ignored_stack.pop()
            return
        if tag in {"p", "div", "li"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.ignored_stack:
            self.parts.append(data)

    def text(self) -> str:
        return normalize_text("".join(self.parts))


def die(message: str, exit_code: int = 1) -> NoReturn:
    print(message, file=sys.stderr)
    raise SystemExit(exit_code)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch public netkeiba board comments and summarize only objective "
            "information with an AI-MOP/OpenAI-compatible API."
        )
    )
    parser.add_argument("url", nargs="?", help="Public netkeiba board URL to inspect.")
    parser.add_argument(
        "--comments-json",
        help="Read comments from a JSON file instead of fetching netkeiba.",
    )
    parser.add_argument(
        "--dump-comments",
        help="Write fetched comments as JSON and exit before calling the AI API.",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=1,
        help="Number of board pages to fetch (default: 1).",
    )
    parser.add_argument(
        "--max-comments",
        type=int,
        default=60,
        help="Maximum comments to send to the model (default: 60).",
    )
    parser.add_argument(
        "--sort",
        choices=["recent", "like"],
        default=None,
        help="Override netkeiba board sort: recent or like.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.7,
        help="Delay seconds between comment-list page requests (default: 0.7).",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("OPENAI_API_KEY"),
        help="API key. Defaults to OPENAI_API_KEY.",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"OpenAI-compatible API base URL (default: {DEFAULT_BASE_URL}).",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Model name (default: {DEFAULT_MODEL}).",
    )
    parser.add_argument(
        "--max-input-chars",
        type=int,
        default=24000,
        help="Maximum serialized comment characters to send (default: 24000).",
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=1400,
        help="Maximum model output tokens (default: 1400).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the validated JSON summary instead of Markdown.",
    )
    args = parser.parse_args()

    if bool(args.url) == bool(args.comments_json):
        die("Specify exactly one of URL or --comments-json.")
    if args.pages < 1:
        die("--pages must be 1 or greater.")
    if args.max_comments < 1:
        die("--max-comments must be 1 or greater.")
    if args.delay < 0:
        die("--delay must be 0 or greater.")
    return args


def normalize_text(value: str) -> str:
    value = unescape(value)
    value = re.sub(r"\r\n?", "\n", value)
    value = re.sub(r"[ \t\u3000]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def strip_html(value: str) -> str:
    parser = HtmlTextExtractor()
    parser.feed(value)
    parser.close()
    return parser.text()


def detect_charset(headers: Any, body: bytes) -> str:
    content_type = ""
    if headers is not None:
        content_type = headers.get("content-type") or headers.get("Content-Type") or ""
    match = re.search(r"charset=([A-Za-z0-9._-]+)", content_type, re.I)
    if match:
        return match.group(1)

    head = body[:4096].decode("ascii", errors="ignore")
    match = re.search(r"<meta[^>]+charset=['\"]?([A-Za-z0-9._-]+)", head, re.I)
    if match:
        return match.group(1)
    match = re.search(r"charset=([A-Za-z0-9._-]+)", head, re.I)
    if match:
        return match.group(1)
    return "utf-8"


def fetch_bytes(url: str, *, data: dict[str, str] | None = None, referer: str | None = None) -> tuple[bytes, Any]:
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
    }
    encoded_data: bytes | None = None
    method = "GET"
    if data is not None:
        encoded_data = urlencode(data).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
        method = "POST"
    if referer:
        headers["Referer"] = referer

    request = Request(url, data=encoded_data, method=method, headers=headers)
    with urlopen(request, timeout=30) as response:
        return response.read(), response.headers


def fetch_text(url: str) -> str:
    body, headers = fetch_bytes(url)
    charset = detect_charset(headers, body)
    return body.decode(charset, errors="replace")


def decode_js_string(token: str) -> str:
    token = token.strip()
    if len(token) < 2 or token[0] not in {"'", '"'} or token[-1] != token[0]:
        return token

    quote = token[0]
    result: list[str] = []
    index = 1
    while index < len(token) - 1:
        char = token[index]
        if char != "\\":
            result.append(char)
            index += 1
            continue

        index += 1
        if index >= len(token) - 1:
            result.append("\\")
            break
        escaped = token[index]
        if escaped == "n":
            result.append("\n")
        elif escaped == "r":
            result.append("\r")
        elif escaped == "t":
            result.append("\t")
        elif escaped == quote:
            result.append(quote)
        elif escaped == "\\":
            result.append("\\")
        elif escaped == "u" and index + 4 < len(token):
            hex_value = token[index + 1 : index + 5]
            try:
                result.append(chr(int(hex_value, 16)))
                index += 4
            except ValueError:
                result.append("\\u")
        else:
            result.append(escaped)
        index += 1

    return "".join(result)


def split_js_args(argument_text: str) -> list[str]:
    args: list[str] = []
    current: list[str] = []
    quote: str | None = None
    escaped = False
    depth = 0

    for char in argument_text:
        current.append(char)
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue

        if char in {"'", '"'}:
            quote = char
        elif char in {"(", "[", "{"}:
            depth += 1
        elif char in {")", "]", "}"} and depth:
            depth -= 1
        elif char == "," and depth == 0:
            current.pop()
            args.append(decode_js_string("".join(current).strip()))
            current = []

    tail = "".join(current).strip()
    if tail:
        args.append(decode_js_string(tail))
    return args


def iter_js_function_call_args(source: str, function_name: str) -> list[str]:
    results: list[str] = []
    pattern = re.compile(rf"\b{re.escape(function_name)}\s*\(")

    for match in pattern.finditer(source):
        prefix = source[max(0, match.start() - 32) : match.start()]
        if re.search(r"function\s*$", prefix):
            continue

        index = match.end()
        start = index
        depth = 1
        quote: str | None = None
        escaped = False
        while index < len(source):
            char = source[index]
            if quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None
            elif char in {"'", '"'}:
                quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    results.append(source[start:index])
                    break
            index += 1

    return results


def extract_comment_list_config(html: str) -> CommentListConfig:
    api_url_match = re.search(
        r"_bbs_action_api_url\s*=\s*['\"]([^'\"]+)['\"]", html
    )
    api_url = api_url_match.group(1) if api_url_match else "https://bbs.netkeiba.com/"

    for call_args in iter_js_function_call_args(html, "showCommentList"):
        args = split_js_args(call_args)
        if len(args) < 3 or args[0] != "Comment_List":
            continue

        params = {
            "pid": "api_get_comment_list",
            "input": "UTF-8",
            "output": "json",
        }
        for name, value in zip(SHOW_COMMENT_LIST_NAMES[1:], args[1:]):
            if value and value not in {"null", "undefined"}:
                params[name] = value
        return CommentListConfig(api_url=api_url, params=params)

    die("Could not find netkeiba showCommentList configuration in the page.")


def fetch_comment_api(config: CommentListConfig, *, referer: str, page: int) -> dict[str, Any]:
    params = dict(config.params)
    params["page"] = str(page)

    body, headers = fetch_bytes(config.api_url, data=params, referer=referer)
    text = body.decode(detect_charset(headers, body), errors="replace")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"^[^(]+\((.*)\)\s*;?\s*$", text, re.S)
        if not match:
            die(f"netkeiba comment API did not return JSON:\n{text[:500]}")
        data = json.loads(match.group(1))

    if not isinstance(data, dict):
        die("netkeiba comment API returned an unexpected payload.")
    return data


def comments_from_api_payload(payload: dict[str, Any]) -> list[BoardComment]:
    data = payload.get("data", payload)
    if not isinstance(data, dict):
        return []
    items = data.get("list", [])
    if not isinstance(items, list):
        return []

    comments: list[BoardComment] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("is_hidden_comment", "0")) == "1":
            continue
        text = strip_html(str(item.get("comment", "")))
        if not text:
            continue
        try:
            like_count = int(str(item.get("like_count", "0")))
        except ValueError:
            like_count = 0
        comments.append(
            BoardComment(
                comment_id=str(item.get("comment_id", "")),
                datetime=str(item.get("datetime", "")),
                text=text,
                like_count=like_count,
            )
        )
    return comments


def fetch_board_comments(
    url: str,
    *,
    pages: int,
    max_comments: int,
    sort: str | None,
    delay: float,
) -> list[BoardComment]:
    html = fetch_text(url)
    config = extract_comment_list_config(html)
    if sort == "recent":
        config.params["sort"] = "1"
    elif sort == "like":
        config.params["sort"] = "2"

    comments: list[BoardComment] = []
    seen_ids: set[str] = set()
    for page in range(1, pages + 1):
        payload = fetch_comment_api(config, referer=url, page=page)
        page_comments = comments_from_api_payload(payload)
        if not page_comments:
            break
        for comment in page_comments:
            if comment.comment_id in seen_ids:
                continue
            seen_ids.add(comment.comment_id)
            comments.append(comment)
            if len(comments) >= max_comments:
                return comments
        if page < pages and delay:
            time.sleep(delay)
    return comments


def load_comments_json(path: str) -> list[BoardComment]:
    with open(path, encoding="utf-8") as file:
        data = json.load(file)
    if isinstance(data, dict):
        data = data.get("comments", [])
    if not isinstance(data, list):
        die("--comments-json must contain a list or an object with a comments list.")

    comments: list[BoardComment] = []
    for index, item in enumerate(data, start=1):
        if isinstance(item, str):
            comments.append(
                BoardComment(
                    comment_id=str(index),
                    datetime="",
                    text=normalize_text(item),
                    like_count=0,
                )
            )
            continue
        if not isinstance(item, dict):
            continue
        text = normalize_text(str(item.get("text") or item.get("comment") or ""))
        if not text:
            continue
        try:
            like_count = int(str(item.get("like_count", "0")))
        except ValueError:
            like_count = 0
        comments.append(
            BoardComment(
                comment_id=str(item.get("comment_id") or item.get("id") or index),
                datetime=str(item.get("datetime", "")),
                text=text,
                like_count=like_count,
            )
        )
    return comments


def dump_comments(path: str, comments: list[BoardComment]) -> None:
    data = {"comments": [asdict(comment) for comment in comments]}
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")


def prepare_model_comments(
    comments: list[BoardComment],
    *,
    max_comments: int,
    max_input_chars: int,
) -> tuple[list[dict[str, Any]], int]:
    entries = [
        {
            "id": comment.comment_id,
            "datetime": comment.datetime,
            "like_count": comment.like_count,
            "text": comment.text[:700],
        }
        for comment in comments[:max_comments]
    ]

    while entries:
        serialized = json.dumps(entries, ensure_ascii=False)
        if len(serialized) <= max_input_chars:
            return entries, len(serialized)
        entries.pop()
    return [], 0


def build_summary_messages(
    *,
    source_url: str,
    comments: list[dict[str, Any]],
) -> list[dict[str, str]]:
    system_prompt = """\
あなたは競馬掲示板の投稿から、客観性の高い情報だけを抽出するアナリストです。

採用してよい情報:
- 投稿本文に具体的な日付、レース名、馬場、枠順、騎手、調教、馬体、出走予定、過去成績などの観察可能な根拠があるもの。
- 複数投稿で共通して言及されているもの。
- 断定ではなく「掲示板上ではそう言及されている」と表現できるもの。

除外または別枠にする情報:
- 馬券購入の推奨、順位予想、願望、煽り、感情的評価、根拠のない断言。
- 誹謗中傷、個人攻撃、ユーザー個人の属性情報。
- 単独投稿だけで確認できず、事実と断定できない噂。

出力は必ず JSON オブジェクトのみ。Markdown、説明文、コードフェンスは不要です。
各 summary には根拠 comment id を入れてください。
"""
    schema_hint = {
        "source": {
            "url": source_url,
            "comments_used": len(comments),
        },
        "objective_summary": [
            {
                "topic": "string",
                "summary": "string",
                "evidence_comment_ids": ["string"],
                "objectivity": "high or medium",
                "caveat": "string",
            }
        ],
        "uncertain_or_subjective": [
            {
                "claim": "string",
                "reason": "string",
                "comment_ids": ["string"],
            }
        ],
        "excluded_noise": ["string"],
        "overall_note": "string",
    }
    user_prompt = {
        "task": "netkeiba掲示板コメントから客観性の高い情報だけを要約する",
        "source_url": source_url,
        "output_schema": schema_hint,
        "comments": comments,
    }
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
    ]


def chat_completion(
    *,
    api_key: str,
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    max_output_tokens: int,
) -> str:
    endpoint = f"{base_url.rstrip('/')}/chat/completions"
    token_field = "max_completion_tokens" if model.startswith("gpt-5") else "max_tokens"
    use_response_format = True
    use_temperature = True
    last_error: str | None = None

    for _ in range(5):
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            token_field: max_output_tokens,
        }
        if use_temperature:
            payload["temperature"] = 0.1
        if use_response_format:
            payload["response_format"] = {"type": "json_object"}

        request = Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=90) as response:
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            last_error = f"HTTP {error.code}\n{detail}"
            if error.code == 400 and use_response_format and (
                "response_format" in detail or "json_object" in detail
            ):
                use_response_format = False
                continue
            if error.code == 400 and use_temperature and "temperature" in detail:
                use_temperature = False
                continue
            if error.code == 400 and token_field == "max_tokens" and "max_completion_tokens" in detail:
                token_field = "max_completion_tokens"
                continue
            if (
                error.code == 400
                and token_field == "max_completion_tokens"
                and "max_tokens" in detail
                and "unsupported_parameter" in detail
            ):
                token_field = "max_tokens"
                continue
            die(f"AI-MOP API request failed: {last_error}")
        except URLError as error:
            die(f"AI-MOP API request failed: {error.reason}")

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            die(f"Unexpected AI-MOP API response:\n{json.dumps(data, ensure_ascii=False, indent=2)}")
        if not isinstance(content, str):
            die("AI-MOP API response content was not text.")
        return content.strip()

    die(f"AI-MOP API request failed: {last_error or 'unknown error'}")


def extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    decoder = json.JSONDecoder()

    for index, char in enumerate(cleaned):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(cleaned[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError(f"Model did not return a JSON object:\n{text[:800]}")


def validate_summary(summary: dict[str, Any]) -> dict[str, Any]:
    summary.setdefault("source", {})
    summary.setdefault("objective_summary", [])
    summary.setdefault("uncertain_or_subjective", [])
    summary.setdefault("excluded_noise", [])
    summary.setdefault("overall_note", "")

    if not isinstance(summary["source"], dict):
        summary["source"] = {}
    for key in ["objective_summary", "uncertain_or_subjective", "excluded_noise"]:
        if not isinstance(summary[key], list):
            summary[key] = []
    if not isinstance(summary["overall_note"], str):
        summary["overall_note"] = str(summary["overall_note"])
    return summary


def request_objective_summary(
    *,
    api_key: str,
    base_url: str,
    model: str,
    source_url: str,
    comments: list[dict[str, Any]],
    max_output_tokens: int,
) -> dict[str, Any]:
    messages = build_summary_messages(source_url=source_url, comments=comments)
    content = chat_completion(
        api_key=api_key,
        base_url=base_url,
        model=model,
        messages=messages,
        max_output_tokens=max_output_tokens,
    )
    try:
        return validate_summary(extract_json_object(content))
    except ValueError:
        repair_messages = [
            *messages,
            {"role": "assistant", "content": content},
            {
                "role": "user",
                "content": (
                    "前回の出力は JSON として解釈できません。"
                    "指定スキーマの JSON オブジェクトだけを返してください。"
                ),
            },
        ]
        repaired = chat_completion(
            api_key=api_key,
            base_url=base_url,
            model=model,
            messages=repair_messages,
            max_output_tokens=max_output_tokens,
        )
        try:
            return validate_summary(extract_json_object(repaired))
        except ValueError as error:
            die(str(error))


def render_markdown(summary: dict[str, Any]) -> str:
    source = summary.get("source", {})
    lines = ["# 客観情報サマリー", ""]
    if source:
        url = source.get("url", "")
        comments_used = source.get("comments_used", "")
        if url:
            lines.append(f"- 対象: {url}")
        if comments_used != "":
            lines.append(f"- 使用コメント数: {comments_used}")
        if len(lines) > 2:
            lines.append("")

    objective_items = summary.get("objective_summary", [])
    lines.append("## 採用した客観寄りの情報")
    if objective_items:
        for item in objective_items:
            if not isinstance(item, dict):
                continue
            topic = item.get("topic", "項目")
            body = item.get("summary", "")
            evidence = item.get("evidence_comment_ids", [])
            objectivity = item.get("objectivity", "")
            caveat = item.get("caveat", "")
            evidence_text = ", ".join(f"#{value}" for value in evidence) if isinstance(evidence, list) else ""
            suffix_parts = []
            if objectivity:
                suffix_parts.append(f"客観性: {objectivity}")
            if evidence_text:
                suffix_parts.append(f"根拠: {evidence_text}")
            suffix = f" ({'; '.join(suffix_parts)})" if suffix_parts else ""
            lines.append(f"- {topic}: {body}{suffix}")
            if caveat:
                lines.append(f"  注意: {caveat}")
    else:
        lines.append("- 採用できる客観寄りの情報は見つかりませんでした。")

    uncertain_items = summary.get("uncertain_or_subjective", [])
    if uncertain_items:
        lines.extend(["", "## 未確認・主観寄りとして扱う情報"])
        for item in uncertain_items:
            if not isinstance(item, dict):
                continue
            claim = item.get("claim", "")
            reason = item.get("reason", "")
            ids = item.get("comment_ids", [])
            id_text = ", ".join(f"#{value}" for value in ids) if isinstance(ids, list) else ""
            tail = f" ({id_text})" if id_text else ""
            lines.append(f"- {claim}: {reason}{tail}")

    noise = summary.get("excluded_noise", [])
    if noise:
        lines.extend(["", "## 除外した傾向"])
        for value in noise:
            lines.append(f"- {value}")

    note = summary.get("overall_note")
    if note:
        lines.extend(["", "## 注意", str(note)])
    return "\n".join(lines)


def main() -> None:
    args = parse_args()

    if args.comments_json:
        comments = load_comments_json(args.comments_json)
        source_url = args.comments_json
    else:
        comments = fetch_board_comments(
            args.url,
            pages=args.pages,
            max_comments=args.max_comments,
            sort=args.sort,
            delay=args.delay,
        )
        source_url = args.url

    if not comments:
        die("No usable comments were found.")

    if args.dump_comments:
        dump_comments(args.dump_comments, comments)
        return

    if not args.api_key:
        die("OPENAI_API_KEY is required, or pass --api-key.")

    model_comments, serialized_size = prepare_model_comments(
        comments,
        max_comments=args.max_comments,
        max_input_chars=args.max_input_chars,
    )
    if not model_comments:
        die("No comments fit within --max-input-chars.")

    summary = request_objective_summary(
        api_key=args.api_key,
        base_url=args.base_url,
        model=args.model,
        source_url=source_url,
        comments=model_comments,
        max_output_tokens=args.max_output_tokens,
    )
    summary.setdefault("source", {})
    summary["source"]["url"] = source_url
    summary["source"]["comments_used"] = len(model_comments)
    summary["source"]["serialized_comment_chars"] = serialized_size

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(summary))


if __name__ == "__main__":
    main()
