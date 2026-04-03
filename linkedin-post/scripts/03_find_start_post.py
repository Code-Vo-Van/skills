#!/usr/bin/env python3
from __future__ import annotations

from _shared import (
    MissingUserInput,
    choose_start_post_candidate,
    common_parser,
    dump_exception,
    emit_and_exit,
    js_scan_start_post_candidates,
    load_state,
    open_cdp_from_state,
    resolve_cdp_url,
    state_set,
    step_result,
    update_profile_fields,
    update_state,
    write_artifact,
)

STEP = "03_find_start_post"


def main() -> None:
    parser = common_parser("Find Start a post candidate and choose best target")
    args = parser.parse_args()

    state = load_state(args.state_file)

    try:
        cdp_url, source, _profile = resolve_cdp_url(args.cdp_url, state, args.stores_dir)
        session, tab = open_cdp_from_state(cdp_url, state)
        try:
            page_meta = session.eval(r'''(() => ({url: location.href, title: document.title}))()''')
            candidates = session.eval(js_scan_start_post_candidates()) or []
            best = choose_start_post_candidate(candidates)

            evidence = {
                "cdp_url": cdp_url,
                "cdp_source": source,
                "page": page_meta,
                "candidate_count": len(candidates),
                "selected": best,
            }
            artifact = write_artifact(args.artifacts_dir, "03-find-start-post-candidates", {
                "page": page_meta,
                "candidates": candidates,
                "selected": best,
            })
            evidence["artifact"] = artifact

            if not best:
                update_state(args.state_file, STEP, evidence)
                emit_and_exit(
                    step_result(
                        step=STEP,
                        status="retryable",
                        evidence=evidence,
                        next_action="02_ensure_feed.py",
                        error="Start a post candidate not found",
                    )
                )

            state_set(args.state_file, start_post_target=best)
            if args.cdp_url:
                update_profile_fields(args.stores_dir, cdp_url=cdp_url)
            update_state(args.state_file, STEP, evidence)

            emit_and_exit(
                step_result(
                    step=STEP,
                    status="ok",
                    evidence=evidence,
                    next_action="04_open_composer.py",
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
