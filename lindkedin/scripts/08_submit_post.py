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


def main() -> None:
    parser = common_parser("Submit post (guarded by --confirm-submit)")
    parser.add_argument("--confirm-submit", action="store_true")
    parser.add_argument("--post-submit-wait-ms", type=int, default=3000)
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
            before_markers = session.eval(js_composer_markers()) or {}
            click = session.eval(JS_CLICK_POST) or {"clicked": False, "reason": "No click result"}
            maybe_sleep_ms(args.post_submit_wait_ms)
            after_markers = session.eval(js_composer_markers()) or {}
            toast = session.eval(r'''
(() => {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden';
  };
  return [...document.querySelectorAll('[role="alert"],.artdeco-toast-item,.artdeco-toast-item__message')]
    .filter(visible)
    .map((el) => (el.innerText || '').replace(/\s+/g, ' ').trim())
    .filter(Boolean)
    .slice(0, 8);
})()
''') or []

            evidence = {
                "cdp_url": cdp_url,
                "cdp_source": source,
                "confirm_submit": True,
                "click": click,
                "before_markers": before_markers,
                "after_markers": after_markers,
                "toast": toast,
            }
            artifact = write_artifact(args.artifacts_dir, "08-submit-post", evidence)
            evidence["artifact"] = artifact
            update_state(args.state_file, STEP, evidence)
            if args.cdp_url:
                update_profile_fields(args.stores_dir, cdp_url=cdp_url)

            if not click.get("clicked"):
                emit_and_exit(step_result(
                    step=STEP,
                    status="retryable",
                    evidence=evidence,
                    next_action="07_check_post_ready.py",
                    error=click.get("reason", "Click failed"),
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
