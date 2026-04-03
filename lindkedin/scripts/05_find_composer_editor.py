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


def main() -> None:
    parser = common_parser("Find visible composer editor")
    args = parser.parse_args()

    state = load_state(args.state_file)

    try:
        cdp_url, source, _profile = resolve_cdp_url(args.cdp_url, state, args.stores_dir)
        session, tab = open_cdp_from_state(cdp_url, state)
        try:
            markers = session.eval(js_composer_markers()) or {}
            editors = session.eval(JS_FIND_EDITORS) or {}
            selected = (editors.get("visibleEditors") or [None])[0]

            evidence = {
                "cdp_url": cdp_url,
                "cdp_source": source,
                "markers": markers,
                "editor_scan": {
                    "total": editors.get("total", 0),
                    "visibleCount": editors.get("visibleCount", 0),
                    "visibleEditors": editors.get("visibleEditors", []),
                },
                "selected_editor": selected,
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
                    next_action="04b_wait_or_manual_open.py",
                    error="No visible composer editor found",
                ))

            state_set(args.state_file, selected_editor=selected)
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
