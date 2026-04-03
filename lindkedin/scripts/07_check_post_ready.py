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


def main() -> None:
    parser = common_parser("Check whether Post button is detectable and enabled")
    args = parser.parse_args()

    state = load_state(args.state_file)

    try:
        cdp_url, source, _profile = resolve_cdp_url(args.cdp_url, state, args.stores_dir)
        session, tab = open_cdp_from_state(cdp_url, state)
        try:
            markers = session.eval(js_composer_markers()) or {}
            scan = session.eval(JS_POST_BUTTON_SCAN) or {}
            preferred = scan.get("preferred")

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
                "markers": markers,
                "scan": scan,
                "post_button": post_button,
                "ready": ready,
            }
            artifact = write_artifact(args.artifacts_dir, "07-check-post-ready", evidence)
            evidence["artifact"] = artifact

            update_state(args.state_file, STEP, evidence)
            state_set(args.state_file, post_button=post_button, post_ready=ready)
            if args.cdp_url:
                update_profile_fields(args.stores_dir, cdp_url=cdp_url)

            if not preferred:
                emit_and_exit(step_result(
                    step=STEP,
                    status="retryable",
                    evidence=evidence,
                    next_action="05_find_composer_editor.py",
                    error="Post button not found",
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
