#!/usr/bin/env python3
from __future__ import annotations

from _shared import (
    MissingUserInput,
    common_parser,
    cdp_targets,
    dump_exception,
    emit_and_exit,
    load_state,
    pick_linkedin_tab,
    resolve_cdp_url,
    state_set,
    step_result,
    update_profile_fields,
    update_state,
)

STEP = "01_pick_linkedin_tab"


def main() -> None:
    parser = common_parser("Pick LinkedIn page tab from CDP targets")
    args = parser.parse_args()

    state = load_state(args.state_file)

    try:
        cdp_url, source, _profile = resolve_cdp_url(args.cdp_url, state, args.stores_dir)
        targets = cdp_targets(cdp_url)
        tab = pick_linkedin_tab(targets)
        if not tab:
            result = step_result(
                step=STEP,
                status="fail",
                evidence={"cdp_url": cdp_url, "target_count": len(targets)},
                next_action=None,
                error="No LinkedIn page tab found",
            )
            emit_and_exit(result)

        tab_info = {
            "id": tab.get("id"),
            "type": tab.get("type"),
            "title": tab.get("title"),
            "url": tab.get("url"),
            "ws_url": tab.get("webSocketDebuggerUrl"),
        }
        evidence = {
            "cdp_url": cdp_url,
            "cdp_source": source,
            "target_count": len(targets),
            "linkedin_page_count": len([
                t for t in targets if t.get("type") == "page" and "linkedin.com" in (t.get("url") or "")
            ]),
            "selected_tab": tab_info,
        }

        state_set(args.state_file, cdp_url=cdp_url, tab=tab_info)
        if args.cdp_url:
            update_profile_fields(args.stores_dir, cdp_url=cdp_url)
        update_state(args.state_file, STEP, evidence)

        emit_and_exit(
            step_result(
                step=STEP,
                status="ok",
                evidence=evidence,
                next_action="02_ensure_feed.py",
            )
        )
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
