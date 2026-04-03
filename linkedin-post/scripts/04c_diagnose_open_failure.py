#!/usr/bin/env python3
from __future__ import annotations

from _shared import (
    MissingUserInput,
    common_parser,
    dump_exception,
    emit_and_exit,
    js_composer_markers,
    js_scan_start_post_candidates,
    load_state,
    maybe_sleep_ms,
    open_cdp_from_state,
    resolve_cdp_url,
    step_result,
    update_profile_fields,
    update_state,
    write_artifact,
)

STEP = "04c_diagnose_open_failure"


def main() -> None:
    parser = common_parser("Collect diagnostics for composer open failure")
    parser.add_argument("--simulate-click", action="store_true")
    parser.add_argument("--wait-after-click-ms", type=int, default=4000)
    args = parser.parse_args()

    state = load_state(args.state_file)

    try:
        cdp_url, source, _profile = resolve_cdp_url(args.cdp_url, state, args.stores_dir)
        session, tab = open_cdp_from_state(cdp_url, state)
        try:
            before_page = session.eval(r'''(() => ({url: location.href, title: document.title}))()''')
            before_res = session.eval('performance.getEntriesByType("resource").map(x => x.name)') or []
            candidates = session.eval(js_scan_start_post_candidates()) or []

            selected = None
            for c in candidates:
                if (c.get("role") or "").lower() == "button":
                    selected = c
                    break
            if not selected and candidates:
                selected = candidates[0]

            click_info = {"clicked": False}
            if args.simulate_click and selected:
                x = int(selected.get("rect", {}).get("x", 0) + selected.get("rect", {}).get("w", 0) / 2)
                y = int(selected.get("rect", {}).get("y", 0) + selected.get("rect", {}).get("h", 0) / 2)
                session.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y, "button": "none"})
                session.send("Input.dispatchMouseEvent", {
                    "type": "mousePressed",
                    "x": x,
                    "y": y,
                    "button": "left",
                    "buttons": 1,
                    "clickCount": 1,
                })
                session.send("Input.dispatchMouseEvent", {
                    "type": "mouseReleased",
                    "x": x,
                    "y": y,
                    "button": "left",
                    "buttons": 0,
                    "clickCount": 1,
                })
                click_info = {"clicked": True, "x": x, "y": y}
                maybe_sleep_ms(args.wait_after_click_ms)

            after_res = session.eval('performance.getEntriesByType("resource").map(x => x.name)') or []
            markers = session.eval(js_composer_markers()) or {}
            frame_info = session.eval(r'''
(() => {
  const frames = [...document.querySelectorAll('iframe')];
  return frames.map((fr) => {
    let sameOrigin = false;
    let href = null;
    let title = null;
    let editorCount = null;
    let dialogCount = null;
    try {
      const doc = fr.contentDocument;
      if (doc) {
        sameOrigin = true;
        href = fr.contentWindow.location.href;
        title = doc.title;
        editorCount = doc.querySelectorAll('div[role="textbox"],[contenteditable="true"],textarea').length;
        dialogCount = doc.querySelectorAll('[role="dialog"]').length;
      }
    } catch (e) {}
    return {
      src: fr.getAttribute('src'),
      id: fr.id || null,
      name: fr.name || null,
      sameOrigin,
      href,
      title,
      editorCount,
      dialogCount,
    };
  });
})()
''') or []

            new_res = [u for u in after_res if u not in set(before_res)]
            interesting = [
                u for u in new_res
                if any(k in u.lower() for k in ["share", "preload", "voyager", "graphql", "demdex", "analytics"])
            ]

            evidence = {
                "cdp_url": cdp_url,
                "cdp_source": source,
                "before_page": before_page,
                "candidate_count": len(candidates),
                "selected_candidate": selected,
                "click_info": click_info,
                "markers": markers,
                "new_resource_count": len(new_res),
                "interesting_resources": interesting[:60],
                "iframe_inventory": frame_info,
            }
            artifact = write_artifact(args.artifacts_dir, "04c-diagnose-open-failure", {
                "before_resources": before_res,
                "after_resources": after_res,
                **evidence,
            })
            evidence["artifact"] = artifact

            update_state(args.state_file, STEP, evidence)
            if args.cdp_url:
                update_profile_fields(args.stores_dir, cdp_url=cdp_url)

            emit_and_exit(step_result(
                step=STEP,
                status="retryable",
                evidence=evidence,
                next_action="04b_wait_or_manual_open.py",
                error="Collected diagnostics for composer open failure",
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
