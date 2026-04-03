#!/usr/bin/env python3
from __future__ import annotations

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
    state_set,
    step_result,
    update_profile_fields,
    update_state,
    write_artifact,
)

STEP = "05_find_composer_editor"


JS_FIND_EDITORS = r'''
(() => {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden';
  };

  const all = [...document.querySelectorAll('div[role="textbox"],[contenteditable="true"],textarea')];
  const mapped = all.map((el, idx) => {
    const r = el.getBoundingClientRect();
    return {
      idx,
      visible: visible(el),
      tag: el.tagName.toLowerCase(),
      role: el.getAttribute('role'),
      aria: el.getAttribute('aria-label'),
      placeholder: el.getAttribute('placeholder'),
      dataPlaceholder: el.getAttribute('data-placeholder'),
      dataTest: el.getAttribute('data-test-ql-editor-contenteditable'),
      className: (el.className || '').toString().slice(0, 220),
      rect: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) },
    };
  });

  const visibleEditors = mapped.filter((m) => m.visible);
  return {
    total: mapped.length,
    visibleCount: visibleEditors.length,
    editors: mapped,
    visibleEditors,
  };
})()
'''

JS_ARTICLE_EDITOR_SCAN = r'''
(() => {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden';
  };
  const titleEditor = document.querySelector('textarea[placeholder="Title"],textarea.article-editor-headline__textarea');
  const bodyEditor = document.querySelector('div[role="textbox"][aria-label="Article editor content"],div.ProseMirror[contenteditable="true"]');
  return {
    url: location.href,
    title: document.title,
    isArticlePage: /\/article\//.test(location.pathname),
    titleEditor: titleEditor ? {
      visible: visible(titleEditor),
      tag: titleEditor.tagName.toLowerCase(),
      placeholder: titleEditor.getAttribute('placeholder'),
      className: (titleEditor.className || '').toString().slice(0, 180),
    } : null,
    bodyEditor: bodyEditor ? {
      visible: visible(bodyEditor),
      tag: bodyEditor.tagName.toLowerCase(),
      role: bodyEditor.getAttribute('role'),
      aria: bodyEditor.getAttribute('aria-label'),
      className: (bodyEditor.className || '').toString().slice(0, 180),
    } : null,
  };
})()
'''


def main() -> None:
    parser = common_parser("Find visible composer editor")
    parser.add_argument("--article-fallback-url", default="https://www.linkedin.com/article/new/")
    parser.add_argument("--article-fallback-wait-ms", type=int, default=5000)
    parser.add_argument("--no-article-fallback", action="store_true")
    args = parser.parse_args()

    state = load_state(args.state_file)

    try:
        cdp_url, source, _profile = resolve_cdp_url(args.cdp_url, state, args.stores_dir)
        session, tab = open_cdp_from_state(cdp_url, state)
        try:
            markers = session.eval(js_composer_markers()) or {}
            editors = session.eval(JS_FIND_EDITORS) or {}
            article_scan = session.eval(JS_ARTICLE_EDITOR_SCAN) or {}
            selected_feed_editor = (editors.get("visibleEditors") or [None])[0]

            selected = None
            post_mode = None
            if article_scan.get("titleEditor") and article_scan.get("bodyEditor") and article_scan.get("isArticlePage"):
                selected = article_scan.get("bodyEditor")
                post_mode = "article_post"
            elif selected_feed_editor:
                selected = selected_feed_editor
                post_mode = "feed_post"
            elif not args.no_article_fallback:
                session.navigate(args.article_fallback_url)
                maybe_sleep_ms(args.article_fallback_wait_ms)
                markers = session.eval(js_composer_markers()) or {}
                editors = session.eval(JS_FIND_EDITORS) or {}
                article_scan = session.eval(JS_ARTICLE_EDITOR_SCAN) or {}
                if article_scan.get("titleEditor") and article_scan.get("bodyEditor") and article_scan.get("isArticlePage"):
                    selected = article_scan.get("bodyEditor")
                    post_mode = "article_post"

            evidence = {
                "cdp_url": cdp_url,
                "cdp_source": source,
                "markers": markers,
                "post_mode": post_mode,
                "editor_scan": {
                    "total": editors.get("total", 0),
                    "visibleCount": editors.get("visibleCount", 0),
                    "visibleEditors": editors.get("visibleEditors", []),
                },
                "article_scan": article_scan,
                "selected_editor": selected,
                "article_fallback_attempted": bool(not selected_feed_editor and not args.no_article_fallback),
                "article_fallback_url": args.article_fallback_url,
            }
            artifact = write_artifact(args.artifacts_dir, "05-find-editor", evidence)
            evidence["artifact"] = artifact
            update_state(args.state_file, STEP, evidence)
            if args.cdp_url:
                update_profile_fields(args.stores_dir, cdp_url=cdp_url)

            if not selected:
                emit_and_exit(step_result(
                    step=STEP,
                    status="retryable",
                    evidence=evidence,
                    next_action="04b_wait_or_manual_open.py or manual_open_required",
                    error="No feed/article editor found",
                ))

            state_set(args.state_file, selected_editor=selected, post_mode=post_mode)
            emit_and_exit(step_result(
                step=STEP,
                status="ok",
                evidence=evidence,
                next_action="06_fill_post_text.py",
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
