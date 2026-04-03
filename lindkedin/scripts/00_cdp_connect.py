#!/usr/bin/env python3
from __future__ import annotations

from _shared import (
    MissingUserInput,
    common_parser,
    cdp_version,
    dump_exception,
    emit_and_exit,
    load_state,
    resolve_cdp_url,
    state_set,
    step_result,
    update_profile_fields,
    update_state,
)

STEP = "00_cdp_connect"


def main() -> None:
    parser = common_parser("Validate CDP endpoint connectivity")
    args = parser.parse_args()
    state = load_state(args.state_file)

    try:
        cdp_url, source, _profile = resolve_cdp_url(args.cdp_url, state, args.stores_dir)
        version = cdp_version(cdp_url)
        evidence = {
            "cdp_url": cdp_url,
            "cdp_source": source,
            "browser": version.get("Browser"),
            "protocol_version": version.get("Protocol-Version"),
            "websocket_browser": version.get("webSocketDebuggerUrl"),
            "user_agent": version.get("User-Agent"),
        }

        state_set(
            args.state_file,
            cdp_url=cdp_url,
        )
        if args.cdp_url:
            update_profile_fields(args.stores_dir, cdp_url=cdp_url)
        update_state(args.state_file, STEP, evidence)

        result = step_result(
            step=STEP,
            status="ok",
            evidence=evidence,
            next_action="01_pick_linkedin_tab.py",
        )
        emit_and_exit(result)
    except MissingUserInput as e:
        result = step_result(
            step=STEP,
            status="retryable",
            evidence={"stores_dir": args.stores_dir},
            next_action="ask_user_for_cdp_url",
            error=str(e),
        )
        emit_and_exit(result)
    except Exception as e:
        result = step_result(
            step=STEP,
            status="fail",
            evidence={"stores_dir": args.stores_dir},
            next_action=None,
            error=dump_exception(e),
        )
        emit_and_exit(result)


if __name__ == "__main__":
    main()
