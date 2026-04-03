#!/usr/bin/env python3
from __future__ import annotations

import json
import time

from _shared import (
    MissingUserInput,
    common_parser,
    dump_exception,
    emit_and_exit,
    js_composer_markers,
    load_state,
    maybe_sleep_ms,
    open_cdp_from_state,
    resolve_cdp_url,
    step_result,
    update_profile_fields,
    update_state,
    write_artifact,
)

STEP = "08_submit_post"


JS_CLICK_POST = r'''
(() => {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden';
  };
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();

  const buttons = [...document.querySelectorAll('button,[role="button"],a')]
    .filter(visible)
    .map((el, idx) => ({
      idx,
      el,
      tag: el.tagName.toLowerCase(),
      role: el.getAttribute('role'),
      text: (el.innerText || '').replace(/\s+/g, ' ').trim(),
      aria: el.getAttribute('aria-label'),
      disabled: !!el.disabled,
    }));

  const postLike = buttons.filter((b) => /\bpost\b/i.test((b.text || '') + ' ' + (b.aria || '')));
  const preferred = postLike.find((b) => norm(b.text) === 'post')
    || postLike.find((b) => norm(b.aria) === 'post')
    || postLike[0]
    || null;

  if (!preferred) {
    return { clicked: false, reason: 'Post button not found', postLikeCount: postLike.length };
  }
  if (preferred.disabled) {
    return { clicked: false, reason: 'Post button disabled', preferred: { text: preferred.text, aria: preferred.aria, disabled: true } };
  }

  preferred.el.click();
  return {
    clicked: true,
    preferred: {
      text: preferred.text,
      aria: preferred.aria,
      disabled: preferred.disabled,
      tag: preferred.tag,
      role: preferred.role,
    },
    postLikeCount: postLike.length,
  };
})()
'''

JS_CLICK_NEXT_ARTICLE = r'''
(() => {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden';
  };
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const buttons = [...document.querySelectorAll('button,[role="button"],a')]
    .filter(visible)
    .map((el) => ({
      el,
      text: (el.innerText || '').replace(/\s+/g, ' ').trim(),
      aria: el.getAttribute('aria-label'),
      disabled: !!el.disabled,
      className: (el.className || '').toString().slice(0, 180),
    }));
  const nextBtn = buttons.find((b) => norm(b.text) === 'next')
    || buttons.find((b) => norm(b.aria) === 'next')
    || buttons.find((b) => norm(b.text).includes('next'))
    || null;
  if (!nextBtn) return { clicked: false, reason: 'Next button not found' };
  if (nextBtn.disabled) return { clicked: false, reason: 'Next button disabled', target: nextBtn };
  nextBtn.el.click();
  return { clicked: true, target: { text: nextBtn.text, aria: nextBtn.aria, className: nextBtn.className } };
})()
'''

JS_CLICK_PUBLISH_ARTICLE = r'''
(() => {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden';
  };
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const buttons = [...document.querySelectorAll('button,[role="button"],a')]
    .filter(visible)
    .map((el) => ({
      el,
      text: (el.innerText || '').replace(/\s+/g, ' ').trim(),
      aria: el.getAttribute('aria-label'),
      disabled: !!el.disabled,
      className: (el.className || '').toString().slice(0, 180),
    }));
  const publishBtn = buttons.find((b) => norm(b.text) === 'publish')
    || buttons.find((b) => norm(b.aria) === 'publish')
    || buttons.find((b) => norm(b.text).includes('publish'))
    || null;
  if (!publishBtn) return { clicked: false, reason: 'Publish button not found' };
  if (publishBtn.disabled) return { clicked: false, reason: 'Publish button disabled', target: publishBtn };
  publishBtn.el.click();
  return { clicked: true, target: { text: publishBtn.text, aria: publishBtn.aria, className: publishBtn.className } };
})()
'''

JS_PAGE_SUMMARY = r'''
(() => {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden';
  };
  const toast = [...document.querySelectorAll('[role="alert"],.artdeco-toast-item,.artdeco-toast-item__message')]
    .filter(visible)
    .map((el) => (el.innerText || '').replace(/\s+/g, ' ').trim())
    .filter(Boolean)
    .slice(0, 8);
  const snippet = (document.body?.innerText || '').replace(/\s+/g, ' ').slice(0, 700);
  const actionButtons = [...document.querySelectorAll('button,[role="button"],a')]
    .filter(visible)
    .map((el) => ({
      text: (el.innerText || '').replace(/\s+/g, ' ').trim(),
      aria: el.getAttribute('aria-label'),
      disabled: !!el.disabled,
      className: (el.className || '').toString().slice(0, 180),
    }))
    .filter((b) => /\b(view post|edit article|publish|post)\b/i.test((b.text || '') + ' ' + (b.aria || '')))
    .slice(0, 20);
  return {
    url: location.href,
    title: document.title,
    ready: document.readyState,
    toast,
    snippet,
    actionButtons,
    isArticlePage: /\/article\//.test(location.pathname),
    isPulsePage: /\/pulse\//.test(location.pathname),
  };
})()
'''


def is_article_publish_success(page: dict) -> bool:
    url = str(page.get("url") or "")
    snippet = str(page.get("snippet") or "").lower()
    buttons = page.get("actionButtons") or []
    has_view_post = any("view post" in str((b.get("text") or "")).lower() for b in buttons if isinstance(b, dict))
    return (
        "/pulse/" in url
        or "published=t" in url
        or "congrats on publishing" in snippet
        or has_view_post
    )


def main() -> None:
    parser = common_parser("Submit post (guarded by --confirm-submit)")
    parser.add_argument("--confirm-submit", action="store_true")
    parser.add_argument("--post-submit-wait-ms", type=int, default=20000)
    parser.add_argument("--publish-wait-ms", type=int, default=20000)
    args = parser.parse_args()

    state = load_state(args.state_file)

    if not args.confirm_submit:
        emit_and_exit(step_result(
            step=STEP,
            status="fail",
            evidence={"confirm_submit": False},
            next_action=None,
            error="Safety block: add --confirm-submit to allow publishing",
        ))

    try:
        cdp_url, source, _profile = resolve_cdp_url(args.cdp_url, state, args.stores_dir)
        session, tab = open_cdp_from_state(cdp_url, state)
        try:
            post_mode = str(state.get("post_mode") or "").strip()
            before_markers = session.eval(js_composer_markers()) or {}
            before_page = session.eval(JS_PAGE_SUMMARY) or {}
            if before_page.get("isArticlePage"):
                post_mode = "article_post"
            elif post_mode not in {"feed_post", "article_post"}:
                post_mode = "feed_post"

            click = {"clicked": False, "reason": "No click result"}
            article_next = None
            article_publish = None
            if post_mode == "article_post":
                article_next = session.eval(JS_CLICK_NEXT_ARTICLE) or {"clicked": False, "reason": "No next result"}
                publish_attempts = []
                deadline = time.time() + max(1, args.publish_wait_ms) / 1000.0
                article_publish = {"clicked": False, "reason": "Publish button not found"}
                while True:
                    maybe_sleep_ms(1200)
                    article_publish = session.eval(JS_CLICK_PUBLISH_ARTICLE) or {"clicked": False, "reason": "No publish result"}
                    probe_page = session.eval(JS_PAGE_SUMMARY) or {}
                    publish_attempts.append({
                        "publish": article_publish,
                        "page_url": probe_page.get("url"),
                        "toast": probe_page.get("toast"),
                    })
                    if article_publish.get("clicked"):
                        break
                    if time.time() >= deadline:
                        break
                click = article_publish
            else:
                click = session.eval(JS_CLICK_POST) or {"clicked": False, "reason": "No click result"}
                publish_attempts = None

            recovery = None
            if post_mode == "article_post" and not click.get("clicked"):
                maybe_sleep_ms(800)
                interim_page = session.eval(JS_PAGE_SUMMARY) or {}
                interim_toast = " ".join(interim_page.get("toast") or []).lower()
                draft_text = str(state.get("draft_text") or "").strip()
                if ("body text is required" in interim_toast or "still saving" in interim_toast) and draft_text:
                    fill_js = f"""
(() => {{
  const articleBody = {json.dumps(draft_text)};
  const bodyEl = document.querySelector('div[role="textbox"][aria-label="Article editor content"],div.ProseMirror[contenteditable="true"]');
  if (!bodyEl) return {{ok:false, reason:'body-editor-missing'}};
  bodyEl.focus();
  let usedExecCommand = false;
  try {{
    const sel = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(bodyEl);
    range.collapse(false);
    sel.removeAllRanges();
    sel.addRange(range);
    usedExecCommand = !!document.execCommand('insertText', false, articleBody);
  }} catch (e) {{}}
  if (!usedExecCommand) {{
    bodyEl.textContent = articleBody;
  }}
  bodyEl.dispatchEvent(new Event('input', {{ bubbles: true }}));
  return {{
    ok: true,
    usedExecCommand,
    bodyLength: (bodyEl.innerText || '').replace(/\\s+/g, ' ').trim().length,
  }};
}})()
"""
                    recovery_fill = session.eval(fill_js) or {"ok": False, "reason": "Unknown fill recovery result"}
                    maybe_sleep_ms(1500)
                    recovery_next = session.eval(JS_CLICK_NEXT_ARTICLE) or {"clicked": False, "reason": "Recovery next missing"}
                    recovery_publish = {"clicked": False, "reason": "Recovery publish missing"}
                    recovery_attempts = []
                    deadline = time.time() + max(1, args.publish_wait_ms) / 1000.0
                    while True:
                        maybe_sleep_ms(1200)
                        recovery_publish = session.eval(JS_CLICK_PUBLISH_ARTICLE) or {"clicked": False, "reason": "Recovery publish missing"}
                        probe_page = session.eval(JS_PAGE_SUMMARY) or {}
                        recovery_attempts.append({
                            "publish": recovery_publish,
                            "page_url": probe_page.get("url"),
                            "toast": probe_page.get("toast"),
                        })
                        if recovery_publish.get("clicked"):
                            break
                        if time.time() >= deadline:
                            break
                    click = recovery_publish
                    article_publish = recovery_publish
                    recovery = {
                        "triggered": True,
                        "interim_page": interim_page,
                        "fill": recovery_fill,
                        "next": recovery_next,
                        "publish": recovery_publish,
                        "publish_attempts": recovery_attempts,
                    }

            wait_deadline = time.time() + max(1000, args.post_submit_wait_ms) / 1000.0
            published = False
            after_markers = {}
            after_page = {}
            toast = []
            post_submit_probes = []
            while True:
                after_markers = session.eval(js_composer_markers()) or {}
                after_page = session.eval(JS_PAGE_SUMMARY) or {}
                toast = after_page.get("toast") or []
                if post_mode == "article_post":
                    published = bool(click.get("clicked")) and is_article_publish_success(after_page)
                else:
                    published = bool(click.get("clicked"))

                post_submit_probes.append({
                    "ts": int(time.time() * 1000),
                    "url": after_page.get("url"),
                    "title": after_page.get("title"),
                    "toast": toast,
                    "isArticlePage": after_page.get("isArticlePage"),
                    "isPulsePage": after_page.get("isPulsePage"),
                    "published": published,
                })
                if published or time.time() >= wait_deadline:
                    break
                maybe_sleep_ms(1200)

            evidence = {
                "cdp_url": cdp_url,
                "cdp_source": source,
                "post_mode": post_mode or "feed_post",
                "confirm_submit": True,
                "before_page": before_page,
                "click": click,
                "article_next": article_next,
                "article_publish": article_publish,
                "article_publish_attempts": publish_attempts,
                "article_recovery": recovery,
                "before_markers": before_markers,
                "after_markers": after_markers,
                "after_page": after_page,
                "post_submit_probe_count": len(post_submit_probes),
                "post_submit_probes": post_submit_probes,
                "published": published,
                "toast": toast,
            }
            artifact = write_artifact(args.artifacts_dir, "08-submit-post", evidence)
            evidence["artifact"] = artifact
            update_state(args.state_file, STEP, evidence)
            if args.cdp_url:
                update_profile_fields(args.stores_dir, cdp_url=cdp_url)

            if not published:
                emit_and_exit(step_result(
                    step=STEP,
                    status="retryable",
                    evidence=evidence,
                    next_action="07_check_post_ready.py",
                    error=click.get("reason", "Publish action failed"),
                ))

            emit_and_exit(step_result(
                step=STEP,
                status="ok",
                evidence=evidence,
                next_action="09_capture_post_result.py",
            ))
        finally:
            session.close()
    except MissingUserInput as e:
        emit_and_exit(step_result(
            step=STEP,
            status="retryable",
            evidence={"stores_dir": args.stores_dir, "confirm_submit": True},
            next_action="ask_user_for_cdp_url",
            error=str(e),
        ))
    except Exception as e:
        emit_and_exit(step_result(
            step=STEP,
            status="fail",
            evidence={"stores_dir": args.stores_dir, "confirm_submit": True},
            next_action=None,
            error=dump_exception(e),
        ))


if __name__ == "__main__":
    main()
