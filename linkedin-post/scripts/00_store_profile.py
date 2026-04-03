#!/usr/bin/env python3
from __future__ import annotations

from _shared import (
    common_parser,
    emit_and_exit,
    normalize_cdp_url,
    normalize_post_style,
    step_result,
    update_profile_fields,
)

STEP = "00_store_profile"


def main() -> None:
    parser = common_parser("Store user profile preferences (cdp_url, post_style)")
    parser.add_argument("--post-style", default=None)
    args = parser.parse_args()

    cdp_url = normalize_cdp_url(args.cdp_url) if args.cdp_url else None
    post_style = normalize_post_style(args.post_style) if args.post_style else None

    if not cdp_url and not post_style:
        emit_and_exit(step_result(
            step=STEP,
            status="retryable",
            evidence={"stores_dir": args.stores_dir},
            next_action="ask_user_for_profile_fields",
            error="Provide at least one field: --cdp-url and/or --post-style",
        ))

    profile = update_profile_fields(
        args.stores_dir,
        cdp_url=cdp_url,
        post_style=post_style,
    )

    emit_and_exit(step_result(
        step=STEP,
        status="ok",
        evidence={
            "stores_dir": args.stores_dir,
            "profile": profile,
        },
        next_action="00_cdp_connect.py",
    ))


if __name__ == "__main__":
    main()
