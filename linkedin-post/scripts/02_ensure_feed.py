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
)

STEP = "02_ensure_feed"


def main() -> None:
    parser = common_parser("Navigate selected LinkedIn tab to feed and verify page")
    parser.add_argument("--feed-url", default="https://www.linkedin.com/feed/")
    parser.add_argument("--post-navigate-wait-ms", type=int, default=3000)
    args = parser.parse_args()

    state = load_state(args.state_file)

    try:
        cdp_url, source, _profile = resolve_cdp_url(args.cdp_url, state, args.stores_dir)
        session, tab = open_cdp_from_state(cdp_url, state)
        try:
            before = session.eval(r'''(() => ({url: location.href, title: document.title, ready: document.readyState}))()''')

            needs_nav = "linkedin.com/feed" not in (before.get("url") or "")
            if needs_nav:
                session.navigate(args.feed_url)
                maybe_sleep_ms(args.post_navigate_wait_ms)

            after = session.eval(r'''(() => ({url: location.href, title: document.title, ready: document.readyState}))()''')
            markers = session.eval(js_composer_markers())

            tab_info = {
                "id": tab.get("id"),
                "type": tab.get("type"),
                "title": after.get("title") or tab.get("title"),
                "url": after.get("url") or tab.get("url"),
                "ws_url": tab.get("webSocketDebuggerUrl"),
            }
            evidence = {
                "cdp_url": cdp_url,
                "cdp_source": source,
                "before": before,
                "after": after,
                "navigated": needs_nav,
                "markers": markers,
            }

            state_set(args.state_file, cdp_url=cdp_url, tab=tab_info, feed_url=after.get("url"))
            if args.cdp_url:
                update_profile_fields(args.stores_dir, cdp_url=cdp_url)
            update_state(args.state_file, STEP, evidence)

            emit_and_exit(
                step_result(
                    step=STEP,
                    status="ok",
                    evidence=evidence,
                    next_action="03_find_start_post.py",
                )
            )
        finally:
            session.close()
    except MissingUserInput as e:
        emit_and_exit(
            step_result(
                step=STEP,
                status="retryable",
                evidence={"stores_dir": args.stores_dir},
                next_action="ask_user_for_cdp_url",
                error=str(e),
            )
        )
    except Exception as e:
        emit_and_exit(
            step_result(
                step=STEP,
                status="fail",
                evidence={"stores_dir": args.stores_dir},
                next_action=None,
                error=dump_exception(e),
            )
        )


if __name__ == "__main__":
    main()
