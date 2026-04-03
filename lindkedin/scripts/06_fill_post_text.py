#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from _shared import (
    MissingUserInput,
    common_parser,
    dump_exception,
    emit_and_exit,
    js_composer_markers,
    load_state,
    open_cdp_from_state,
    resolve_cdp_url,
    resolve_post_style,
    state_set,
    step_result,
    update_profile_fields,
    update_state,
    write_artifact,
)

STEP = "06_fill_post_text"


JS_VISIBLE_EDITORS = r'''
(() => {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden';
  };
  const editors = [...document.querySelectorAll('div[role="textbox"],[contenteditable="true"],textarea')].filter(visible);
  return editors.map((el, idx) => ({
    idx,
    tag: el.tagName.toLowerCase(),
    role: el.getAttribute('role'),
    aria: el.getAttribute('aria-label'),
    placeholder: el.getAttribute('placeholder'),
    dataPlaceholder: el.getAttribute('data-placeholder'),
  }));
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
      tag: titleEditor.tagName.toLowerCase(),
      placeholder: titleEditor.getAttribute('placeholder'),
      className: (titleEditor.className || '').toString().slice(0, 180),
      visible: visible(titleEditor),
      valueLength: (titleEditor.value || '').length,
    } : null,
    bodyEditor: bodyEditor ? {
      tag: bodyEditor.tagName.toLowerCase(),
      role: bodyEditor.getAttribute('role'),
      aria: bodyEditor.getAttribute('aria-label'),
      className: (bodyEditor.className || '').toString().slice(0, 180),
      visible: visible(bodyEditor),
      textLength: (bodyEditor.innerText || '').length,
    } : null,
  };
})()
'''


def derive_article_title(text: str) -> str:
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if not first_line:
        first_line = "Automated LinkedIn article update"
    return first_line[:120]


def main() -> None:
    parser = common_parser("Fill text into composer editor (dry-run by default)")
    parser.add_argument("--text", default=None)
    parser.add_argument("--text-file", default=None)
    parser.add_argument("--post-style", default=None)
    parser.add_argument("--editor-index", type=int, default=0)
    parser.add_argument("--apply", action="store_true", help="Actually type text into editor")
    args = parser.parse_args()

    state = load_state(args.state_file)

    text = args.text
    if args.text_file:
        text = Path(args.text_file).read_text(encoding="utf-8")
    if text is None:
        emit_and_exit(step_result(
            step=STEP,
            status="fail",
            evidence={"stores_dir": args.stores_dir},
            next_action=None,
            error="Missing text input. Provide --text or --text-file",
        ))

    try:
        cdp_url, cdp_source, _profile = resolve_cdp_url(args.cdp_url, state, args.stores_dir)
        post_style, style_source, _profile2 = resolve_post_style(args.post_style, args.stores_dir)
        session, tab = open_cdp_from_state(cdp_url, state)
        try:
            editors = session.eval(JS_VISIBLE_EDITORS) or []
            article_scan = session.eval(JS_ARTICLE_EDITOR_SCAN) or {}

            post_mode = str(state.get("post_mode") or "").strip()
            has_article_editors = bool(article_scan.get("titleEditor")) and bool(article_scan.get("bodyEditor"))
            if has_article_editors and article_scan.get("isArticlePage"):
                post_mode = "article_post"
            elif post_mode not in {"feed_post", "article_post"}:
                post_mode = "feed_post"

            selected_index = args.editor_index if 0 <= args.editor_index < len(editors) else 0
            selected_editor = editors[selected_index] if editors else None
            article_title = derive_article_title(text)

            if post_mode == "feed_post" and not editors:
                emit_and_exit(step_result(
                    step=STEP,
                    status="retryable",
                    evidence={"cdp_url": cdp_url, "post_mode": post_mode, "editor_count": 0, "article_scan": article_scan},
                    next_action="05_find_composer_editor.py",
                    error="No visible feed composer editor available for fill",
                ))

            if post_mode == "article_post" and (not article_scan.get("titleEditor") or not article_scan.get("bodyEditor")):
                emit_and_exit(step_result(
                    step=STEP,
                    status="retryable",
                    evidence={"cdp_url": cdp_url, "post_mode": post_mode, "article_scan": article_scan},
                    next_action="05_find_composer_editor.py",
                    error="Article editors not detected for fill",
                ))

            apply_result = {
                "applied": False,
                "reason": "dry-run (use --apply to type text)",
                "selected_index": selected_index,
                "post_mode": post_mode,
            }

            if args.apply:
                if post_mode == "article_post":
                    js = f"""
(() => {{
  const articleTitle = {json.dumps(article_title)};
  const titleEl = document.querySelector('textarea[placeholder="Title"],textarea.article-editor-headline__textarea');
  const bodyEl = document.querySelector('div[role="textbox"][aria-label="Article editor content"],div.ProseMirror[contenteditable="true"]');
  if (!titleEl || !bodyEl) {{
    return {{ applied: false, postMode: 'article_post', error: 'Missing title/body editor' }};
  }}

  titleEl.focus();
  titleEl.value = articleTitle;
  titleEl.dispatchEvent(new Event('input', {{ bubbles: true }}));
  titleEl.dispatchEvent(new Event('change', {{ bubbles: true }}));

  bodyEl.focus();
  bodyEl.innerHTML = '';
  bodyEl.dispatchEvent(new Event('input', {{ bubbles: true }}));
  try {{
    const sel = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(bodyEl);
    range.collapse(false);
    sel.removeAllRanges();
    sel.addRange(range);
  }} catch (e) {{}}

  return {{
    applied: true,
    postMode: 'article_post',
    titleLength: articleTitle.length,
    readyForTyping: true,
    bodyTextLengthAfter: (bodyEl.innerText || '').length,
  }};
}})()
"""
                else:
                    js = f"""
(() => {{
  const visible = (el) => {{
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden';
  }};
  const editors = [...document.querySelectorAll('div[role=\\"textbox\\"],[contenteditable=\\"true\\"],textarea')].filter(visible);
  const idx = {selected_index};
  const target = editors[idx] || editors[0] || null;
  if (!target) return {{ applied: false, error: 'No target editor' }};

  const text = {json.dumps(text)};
  target.focus();

  if (target.tagName.toLowerCase() === 'textarea') {{
    target.value = text;
    target.dispatchEvent(new Event('input', {{ bubbles: true }}));
    target.dispatchEvent(new Event('change', {{ bubbles: true }}));
  }} else {{
    target.innerText = text;
    target.textContent = text;
    target.dispatchEvent(new Event('input', {{ bubbles: true }}));
    target.dispatchEvent(new InputEvent('input', {{ bubbles: true, data: text, inputType: 'insertText' }}));
  }}

  return {{
    applied: true,
    postMode: 'feed_post',
    tag: target.tagName.toLowerCase(),
    role: target.getAttribute('role'),
    aria: target.getAttribute('aria-label'),
    textLength: text.length,
  }};
}})()
"""
                apply_result = session.eval(js) or {"applied": False, "error": "Unknown fill error"}
                if post_mode == "article_post" and apply_result.get("applied") and apply_result.get("readyForTyping"):
                    try:
                        session.send("Input.insertText", {"text": text})
                        after_insert = session.eval(r'''
(() => {
  const bodyEl = document.querySelector('div[role="textbox"][aria-label="Article editor content"],div.ProseMirror[contenteditable="true"]');
  const bodyText = (bodyEl?.innerText || '').replace(/\s+/g, ' ').trim();
  return {
    bodyTextLengthAfter: bodyText.length,
    bodyTextPreview: bodyText.slice(0, 160),
  };
})()
''') or {}
                        apply_result["inputInsertText"] = True
                        apply_result["bodyTextLengthAfter"] = after_insert.get("bodyTextLengthAfter")
                        apply_result["bodyTextPreview"] = after_insert.get("bodyTextPreview")
                    except Exception as _e:
                        apply_result["inputInsertText"] = False

            markers = session.eval(js_composer_markers()) or {}
            evidence = {
                "cdp_url": cdp_url,
                "cdp_source": cdp_source,
                "post_mode": post_mode,
                "post_style": post_style,
                "post_style_source": style_source,
                "apply_mode": args.apply,
                "text_length": len(text),
                "text_preview": text[:120],
                "editor_count": len(editors),
                "selected_editor": selected_editor,
                "article_title": article_title,
                "article_scan": article_scan,
                "apply_result": apply_result,
                "markers_after": markers,
            }
            artifact = write_artifact(args.artifacts_dir, "06-fill-post-text", evidence)
            evidence["artifact"] = artifact

            update_state(args.state_file, STEP, evidence)
            state_set(
                args.state_file,
                draft_text=text,
                post_style=post_style,
                post_mode=post_mode,
                article_title=article_title if post_mode == "article_post" else None,
            )
            if args.cdp_url or args.post_style:
                update_profile_fields(
                    args.stores_dir,
                    cdp_url=cdp_url if args.cdp_url else None,
                    post_style=post_style if args.post_style else None,
                )

            emit_and_exit(step_result(
                step=STEP,
                status="ok",
                evidence=evidence,
                next_action="07_check_post_ready.py",
            ))
        finally:
            session.close()
    except MissingUserInput as e:
        emit_and_exit(step_result(
            step=STEP,
            status="retryable",
            evidence={"stores_dir": args.stores_dir},
            next_action="ask_user_for_missing_profile",
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
