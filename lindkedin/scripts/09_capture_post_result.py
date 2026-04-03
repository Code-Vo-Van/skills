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
    step_result,
    update_profile_fields,
    update_state,
    write_artifact,
)

STEP = "09_capture_post_result"


def main() -> None:
    parser = common_parser("Capture post-submit evidence snapshot")
    args = parser.parse_args()

    state = load_state(args.state_file)

    try:
        cdp_url, source, _profile = resolve_cdp_url(args.cdp_url, state, args.stores_dir)
        session, tab = open_cdp_from_state(cdp_url, state)
        try:
            post_mode = str(state.get("post_mode") or "").strip() or "feed_post"
            page = session.eval(r'''(() => ({url: location.href, title: document.title, ready: document.readyState}))()''') or {}
            markers = session.eval(js_composer_markers()) or {}
            snippet = session.eval(r'''(() => ((document.body?.innerText || '').replace(/\s+/g, ' ').slice(0, 500)))()''') or ""
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
    .slice(0, 10);
})()
''') or []

            evidence = {
                "cdp_url": cdp_url,
                "cdp_source": source,
                "post_mode": post_mode,
                "page": page,
                "markers": markers,
                "toast": toast,
                "snippet": snippet,
                "published_guess": bool(
                    "/pulse/" in str(page.get("url") or "")
                    or "published=t" in str(page.get("url") or "")
                    or "congrats on publishing" in snippet.lower()
                ),
            }
            artifact = write_artifact(args.artifacts_dir, "09-capture-post-result", evidence)
            evidence["artifact"] = artifact
            update_state(args.state_file, STEP, evidence)
            if args.cdp_url:
                update_profile_fields(args.stores_dir, cdp_url=cdp_url)

            emit_and_exit(step_result(
                step=STEP,
                status="ok",
                evidence=evidence,
                next_action=None,
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
