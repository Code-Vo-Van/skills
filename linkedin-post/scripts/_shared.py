#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from websocket import WebSocketTimeoutException, create_connection

DEFAULT_CDP_URL = (
    os.environ.get("LINKEDIN_POST_CDP_URL")
    or os.environ.get("LINDKEDIN_CDP_URL")
    or ""
).strip()
DEFAULT_STATE_FILE = (
    os.environ.get("LINKEDIN_POST_STATE_FILE")
    or os.environ.get("LINDKEDIN_STATE_FILE")
    or "linkedin-post/artifacts/state.json"
)
DEFAULT_ARTIFACTS_DIR = (
    os.environ.get("LINKEDIN_POST_ARTIFACTS_DIR")
    or os.environ.get("LINDKEDIN_ARTIFACTS_DIR")
    or "linkedin-post/artifacts"
)
DEFAULT_STORES_DIR = (
    os.environ.get("LINKEDIN_POST_STORES_DIR")
    or os.environ.get("LINDKEDIN_STORES_DIR")
    or "linkedin-post/stores"
)
PROFILE_FILE_NAME = "profile.json"


class MissingUserInput(ValueError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_cdp_url(cdp_url: str) -> str:
    cdp_url = cdp_url.strip()
    if not cdp_url:
        return DEFAULT_CDP_URL
    if not re.match(r"^https?://", cdp_url):
        cdp_url = f"http://{cdp_url}"
    return cdp_url.rstrip("/")


def profile_path(stores_dir: str) -> Path:
    return Path(stores_dir) / PROFILE_FILE_NAME


def load_profile(stores_dir: str) -> Dict[str, Any]:
    ensure_dir(stores_dir)
    path = profile_path(stores_dir)
    if not path.exists():
        return {
            "cdp_url": "",
            "post_style": "",
            "updated_at": None,
        }
    data = load_json(path, default={})
    if not isinstance(data, dict):
        data = {}
    data.setdefault("cdp_url", "")
    data.setdefault("post_style", "")
    data.setdefault("updated_at", None)
    return data


def save_profile(stores_dir: str, profile: Dict[str, Any]) -> Dict[str, Any]:
    ensure_dir(stores_dir)
    profile = dict(profile)
    profile["updated_at"] = utc_now()
    save_json(profile_path(stores_dir), profile)
    return profile


def update_profile_fields(stores_dir: str, **fields: Any) -> Dict[str, Any]:
    profile = load_profile(stores_dir)
    for k, v in fields.items():
        if v is not None:
            profile[k] = v
    return save_profile(stores_dir, profile)


def normalize_post_style(post_style: str) -> str:
    return re.sub(r"\s+", " ", (post_style or "")).strip()


def resolve_cdp_url(raw_cdp_url: Optional[str], state: Dict[str, Any], stores_dir: str) -> tuple[str, str, Dict[str, Any]]:
    profile = load_profile(stores_dir)
    if raw_cdp_url and raw_cdp_url.strip():
        cdp_url = normalize_cdp_url(raw_cdp_url)
        source = "cli"
    elif state.get("cdp_url"):
        cdp_url = normalize_cdp_url(str(state.get("cdp_url")))
        source = "state"
    elif profile.get("cdp_url"):
        cdp_url = normalize_cdp_url(str(profile.get("cdp_url")))
        source = "store"
    elif DEFAULT_CDP_URL:
        cdp_url = normalize_cdp_url(DEFAULT_CDP_URL)
        source = "env_default"
    else:
        raise MissingUserInput(
            "Missing CDP URL. Ask user for CDP endpoint and save it (example: "
            "python3 linkedin-post/scripts/00_store_profile.py --cdp-url http://HOST:9222)."
        )
    return cdp_url, source, profile


def resolve_post_style(raw_post_style: Optional[str], stores_dir: str) -> tuple[str, str, Dict[str, Any]]:
    profile = load_profile(stores_dir)
    if raw_post_style and normalize_post_style(raw_post_style):
        style = normalize_post_style(raw_post_style)
        source = "cli"
    elif normalize_post_style(str(profile.get("post_style") or "")):
        style = normalize_post_style(str(profile.get("post_style") or ""))
        source = "store"
    else:
        raise MissingUserInput(
            "Missing post_style. Ask user for desired post style and save it "
            "(example: python3 linkedin-post/scripts/00_store_profile.py --post-style \"short, clear, friendly\")."
        )
    return style, source, profile


def ensure_parent(path: str | Path) -> None:
    Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


def ensure_dir(path: str | Path) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)


def load_json(path: str | Path, default: Any) -> Any:
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: str | Path, data: Any) -> None:
    ensure_parent(path)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_state(path: str) -> Dict[str, Any]:
    state = load_json(path, default={})
    if not isinstance(state, dict):
        state = {}
    state.setdefault("meta", {})
    state.setdefault("steps", {})
    return state


def update_state(state_file: str, step: str, evidence: Dict[str, Any]) -> Dict[str, Any]:
    state = load_state(state_file)
    state["meta"]["updated_at"] = utc_now()
    state["steps"][step] = {
        "ts": utc_now(),
        "evidence": evidence,
    }
    save_json(state_file, state)
    return state


def state_set(state_file: str, **kwargs: Any) -> Dict[str, Any]:
    state = load_state(state_file)
    for k, v in kwargs.items():
        state[k] = v
    state["meta"]["updated_at"] = utc_now()
    save_json(state_file, state)
    return state


def write_artifact(artifacts_dir: str, name: str, payload: Any) -> str:
    ensure_dir(artifacts_dir)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "-", name).strip("-")
    out = Path(artifacts_dir) / f"{safe}-{ts}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(out)


def step_result(
    *,
    step: str,
    status: str,
    evidence: Dict[str, Any],
    next_action: Optional[str] = None,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "status": status,
        "step": step,
        "ts": utc_now(),
        "evidence": evidence,
        "next_action": next_action,
        "error": error,
    }


def emit_and_exit(result: Dict[str, Any]) -> None:
    print(json.dumps(result, ensure_ascii=False, indent=2))
    status = result.get("status")
    if status == "ok":
        raise SystemExit(0)
    if status == "retryable":
        raise SystemExit(10)
    raise SystemExit(20)


def common_parser(step_description: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=step_description)
    p.add_argument("--cdp-url", default=None)
    p.add_argument("--state-file", default=DEFAULT_STATE_FILE)
    p.add_argument("--artifacts-dir", default=DEFAULT_ARTIFACTS_DIR)
    p.add_argument("--stores-dir", default=DEFAULT_STORES_DIR)
    p.add_argument("--timeout-ms", type=int, default=12000)
    return p


def cdp_get(cdp_url: str, path: str, timeout_s: float = 8.0) -> Any:
    base = normalize_cdp_url(cdp_url)
    return requests.get(f"{base}{path}", timeout=timeout_s).json()


def cdp_version(cdp_url: str) -> Dict[str, Any]:
    return cdp_get(cdp_url, "/json/version")


def cdp_targets(cdp_url: str) -> List[Dict[str, Any]]:
    data = cdp_get(cdp_url, "/json/list")
    return data if isinstance(data, list) else []


def pick_linkedin_tab(targets: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    pages = [t for t in targets if t.get("type") == "page" and "linkedin.com" in (t.get("url") or "")]
    if not pages:
        return None

    def score(t: Dict[str, Any]) -> int:
        u = t.get("url") or ""
        s = 0
        if "linkedin.com/feed" in u:
            s += 100
        if "linkedin.com/in/" in u:
            s += 20
        if "linkedin.com" in u:
            s += 10
        return s

    pages.sort(key=score, reverse=True)
    return pages[0]


@dataclass
class CDPSession:
    ws_url: str
    timeout_s: float = 30.0

    def __post_init__(self) -> None:
        self.ws = create_connection(self.ws_url, timeout=self.timeout_s)
        self.ws.settimeout(3)
        self._id = 0

    def close(self) -> None:
        try:
            self.ws.close()
        except Exception:
            pass

    def send(self, method: str, params: Optional[Dict[str, Any]] = None, wait_s: float = 20.0) -> Dict[str, Any]:
        self._id += 1
        rid = self._id
        payload: Dict[str, Any] = {"id": rid, "method": method}
        if params is not None:
            payload["params"] = params
        self.ws.send(json.dumps(payload))

        deadline = time.time() + wait_s
        while time.time() < deadline:
            try:
                raw = self.ws.recv()
            except WebSocketTimeoutException:
                continue
            msg = json.loads(raw)
            if msg.get("id") == rid:
                return msg
        raise TimeoutError(f"Timeout waiting for CDP response: {method}")

    def eval(self, expression: str, return_by_value: bool = True) -> Any:
        resp = self.send("Runtime.evaluate", {"expression": expression, "returnByValue": return_by_value})
        return resp.get("result", {}).get("result", {}).get("value")

    def navigate(self, url: str) -> Dict[str, Any]:
        return self.send("Page.navigate", {"url": url}, wait_s=30)

    def enable_basics(self) -> None:
        self.send("Page.enable")
        self.send("Runtime.enable")


def resolve_linkedin_tab(cdp_url: str, state: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    targets = cdp_targets(cdp_url)
    state = state or {}

    wanted_id = (state.get("tab") or {}).get("id")
    if wanted_id:
        for t in targets:
            if t.get("id") == wanted_id:
                return t

    return pick_linkedin_tab(targets)


def js_scan_start_post_candidates() -> str:
    return r'''
(() => {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden';
  };
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const pool = [...document.querySelectorAll('div[role="button"],button,[role="button"],a,div')].filter(visible);

  const raw = pool.filter((el) => {
    const text = norm(el.innerText);
    const aria = norm(el.getAttribute('aria-label'));
    return text === 'start a post' || aria === 'start a post' || aria.includes('start a post');
  });

  return raw.slice(0, 40).map((el, idx) => {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    let onclickSrc = null;
    try { onclickSrc = el.onclick ? String(el.onclick).slice(0, 120) : null; } catch (e) {}
    return {
      idx,
      tag: el.tagName.toLowerCase(),
      role: el.getAttribute('role'),
      aria: el.getAttribute('aria-label'),
      text: (el.innerText || '').replace(/\s+/g, ' ').trim(),
      tabIndex: el.getAttribute('tabindex'),
      onclickType: typeof el.onclick,
      onclickSource: onclickSrc,
      cursor: cs.cursor,
      pointerEvents: cs.pointerEvents,
      rect: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) },
      className: (el.className || '').toString().slice(0, 220),
    };
  });
})()
'''


def choose_start_post_candidate(candidates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not candidates:
        return None

    def score(c: Dict[str, Any]) -> int:
        s = 0
        role = (c.get("role") or "").lower()
        text = (c.get("text") or "").strip().lower()
        aria = (c.get("aria") or "").strip().lower()
        onclick_type = (c.get("onclickType") or "").lower()
        cursor = (c.get("cursor") or "").lower()
        rect = c.get("rect") or {}
        area = int(rect.get("w", 0)) * int(rect.get("h", 0))

        if role == "button":
            s += 120
        if text == "start a post":
            s += 100
        if aria == "start a post":
            s += 100
        elif "start a post" in aria:
            s += 60
        if onclick_type == "function":
            s += 40
        if cursor == "pointer":
            s += 20
        if area > 10000:
            s += 10
        return s

    return sorted(candidates, key=score, reverse=True)[0]


def js_composer_markers() -> str:
    return r'''
(() => {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden';
  };
  const q = (s) => [...document.querySelectorAll(s)].filter(visible);

  const postButtons = q('button,[role="button"],a').map((el) => ({
    text: (el.innerText || '').replace(/\s+/g, ' ').trim(),
    aria: el.getAttribute('aria-label'),
    disabled: !!el.disabled,
  })).filter((b) => /\bpost\b/i.test((b.text || '') + ' ' + (b.aria || ''))).slice(0, 12);

  return {
    url: location.href,
    title: document.title,
    createPostText: (document.body.innerText || '').includes('Create a post'),
    whatTalkText: (document.body.innerText || '').includes('What do you want to talk about'),
    visibleDialogCount: q('[role="dialog"]').length,
    totalDialogCount: document.querySelectorAll('[role="dialog"]').length,
    visibleEditorCount: q('div[role="textbox"],[contenteditable="true"],textarea').length,
    totalEditorCount: document.querySelectorAll('div[role="textbox"],[contenteditable="true"],textarea').length,
    postButtons,
  };
})()
'''


def open_cdp_from_state(cdp_url: str, state: Dict[str, Any]) -> tuple[CDPSession, Dict[str, Any]]:
    tab = resolve_linkedin_tab(cdp_url, state)
    if not tab:
        raise RuntimeError("No LinkedIn page tab found in CDP targets")

    ws_url = tab.get("webSocketDebuggerUrl")
    if not ws_url:
        raise RuntimeError("Selected LinkedIn tab does not have webSocketDebuggerUrl")

    session = CDPSession(ws_url=ws_url)
    session.enable_basics()
    return session, tab


def dump_exception(e: BaseException) -> str:
    return f"{e.__class__.__name__}: {e}"


def maybe_sleep_ms(ms: int) -> None:
    if ms > 0:
        time.sleep(ms / 1000.0)
