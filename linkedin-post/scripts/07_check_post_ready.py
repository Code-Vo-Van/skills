#!/usr/bin/env python3
from __future__ import annotations

from _shared import (
    MissingUserInput,
    common_parser,
    dump_exception,
    emit_and_exit,
    js_composer_markers,
    load_state,
    open_cdp_from_state,
    resolve_cdp_url,
    state_set,
    step_result,
    update_profile_fields,
    update_state,
    write_artifact,
)

STEP = "07_check_post_ready"


JS_POST_BUTTON_SCAN = r'''
(() => {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden';
  };

  const buttons = [...document.querySelectorAll('button,[role="button"],a')]
    .filter(visible)
    .map((el, idx) => ({
      idx,
      tag: el.tagName.toLowerCase(),
      role: el.getAttribute('role'),
      text: (el.innerText || '').replace(/\s+/g, ' ').trim(),
      aria: el.getAttribute('aria-label'),
      disabled: !!el.disabled,
      className: (el.className || '').toString().slice(0, 180),
    }));

  const postLike = buttons.filter((b) => /\bpost\b/i.test((b.text || '') + ' ' + (b.aria || '')));

  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const preferred = postLike.find((b) => norm(b.text) === 'post')
    || postLike.find((b) => norm(b.aria) === 'post')
    || postLike[0]
    || null;

  return {
    postLikeCount: postLike.length,
    postLike,
    preferred,
  };
})()
'''

JS_ARTICLE_READY_SCAN = r'''
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
      tag: el.tagName.toLowerCase(),
      role: el.getAttribute('role'),
      text: (el.innerText || '').replace(/\s+/g, ' ').trim(),
      aria: el.getAttribute('aria-label'),
      disabled: !!el.disabled,
      className: (el.className || '').toString().slice(0, 180),
    }));

  const nextButton = buttons.find((b) => norm(b.text) === 'next')
    || buttons.find((b) => norm(b.aria) === 'next')
    || buttons.find((b) => norm(b.text).includes('next'))
    || null;

  const titleEditor = document.querySelector('textarea[placeholder="Title"],textarea.article-editor-headline__textarea');
  const bodyEditor = document.querySelector('div[role="textbox"][aria-label="Article editor content"],div.ProseMirror[contenteditable="true"]');
  const bodyText = (bodyEditor?.innerText || '').replace(/\s+/g, ' ').trim();

  return {
    page: {
      url: location.href,
      title: document.title,
      isArticlePage: /\/article\//.test(location.pathname),
    },
    titleLength: (titleEditor?.value || '').length,
    bodyLength: bodyText.length,
    nextButton,
    buttonCount: buttons.length,
  };
})()
'''


def main() -> None:
    parser = common_parser("Check whether Post button is detectable and enabled")
    args = parser.parse_args()

    state = load_state(args.state_file)

    try:
        cdp_url, source, _profile = resolve_cdp_url(args.cdp_url, state, args.stores_dir)
        session, tab = open_cdp_from_state(cdp_url, state)
        try:
            post_mode = str(state.get("post_mode") or "").strip()
            markers = session.eval(js_composer_markers()) or {}
            article_scan = session.eval(JS_ARTICLE_READY_SCAN) or {}

            if article_scan.get("page", {}).get("isArticlePage"):
                post_mode = "article_post"
            elif post_mode not in {"feed_post", "article_post"}:
                post_mode = "feed_post"

            scan = session.eval(JS_POST_BUTTON_SCAN) or {}
            preferred = scan.get("preferred")
            next_button = article_scan.get("nextButton")

            if post_mode == "article_post":
                post_button = {
                    "found": bool(next_button),
                    "disabled": bool(next_button.get("disabled")) if next_button else None,
                    "label": ((next_button.get("text") or next_button.get("aria") or "") if next_button else None),
                    "raw": next_button,
                }
                ready = bool(next_button) and not bool(next_button.get("disabled"))
            else:
                post_button = {
                    "found": bool(preferred),
                    "disabled": bool(preferred.get("disabled")) if preferred else None,
                    "label": ((preferred.get("text") or preferred.get("aria") or "") if preferred else None),
                    "raw": preferred,
                }
                ready = bool(preferred) and not bool(preferred.get("disabled"))

            evidence = {
                "cdp_url": cdp_url,
                "cdp_source": source,
                "post_mode": post_mode,
                "markers": markers,
                "scan": scan,
                "article_scan": article_scan,
                "post_button": post_button,
                "ready": ready,
            }
            artifact = write_artifact(args.artifacts_dir, "07-check-post-ready", evidence)
            evidence["artifact"] = artifact

            update_state(args.state_file, STEP, evidence)
            state_set(args.state_file, post_mode=post_mode, post_button=post_button, post_ready=ready)
            if args.cdp_url:
                update_profile_fields(args.stores_dir, cdp_url=cdp_url)

            if not ready:
                emit_and_exit(step_result(
                    step=STEP,
                    status="retryable",
                    evidence=evidence,
                    next_action="05_find_composer_editor.py or 06_fill_post_text.py",
                    error="Submit action is not ready yet",
                ))

            emit_and_exit(step_result(
                step=STEP,
                status="ok",
                evidence=evidence,
                next_action="08_submit_post.py",
            ))
        finally:
            session.close()
    except MissingUserInput as e:
        emit_and_exit(step_result(
            step=STEP,
            status="retryable",
            evidence={"stores_dir": args.stores_dir},
            next_action="ask_user_for_cdp_url",
            error=str(e),
        ))
    except Exception as e:
        emit_and_exit(step_result(
            step=STEP,
            status="fail",
            evidence={"stores_dir": args.stores_dir},
            next_action=None,
            error=dump_exception(e),
        ))


if __name__ == "__main__":
    main()
