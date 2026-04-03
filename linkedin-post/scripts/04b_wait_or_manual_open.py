#!/usr/bin/env python3
from __future__ import annotations

import time

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

STEP = "04b_wait_or_manual_open"

JS_ARTICLE_SCAN = r'''
(() => {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden';
  };
  const titleEditor = document.querySelector('textarea[placeholder="Title"],textarea.article-editor-headline__textarea');
  const bodyEditor = document.querySelector('div[role="textbox"][aria-label="Article editor content"],div.ProseMirror[contenteditable="true"]');
  return {
    url: location.href,
    title: document.title,
    isArticlePage: /\/article\//.test(location.pathname),
    titleEditorVisible: !!(titleEditor && visible(titleEditor)),
    bodyEditorVisible: !!(bodyEditor && visible(bodyEditor)),
  };
})()
'''


def main() -> None:
    parser = common_parser("Wait for composer markers; fallback to manual-open required")
    parser.add_argument("--poll-interval-ms", type=int, default=1000)
    parser.add_argument("--max-wait-ms", type=int, default=15000)
    parser.add_argument("--article-fallback-url", default="https://www.linkedin.com/article/new/")
    parser.add_argument("--article-fallback-wait-ms", type=int, default=5000)
    parser.add_argument("--no-article-fallback", action="store_true")
    args = parser.parse_args()

    state = load_state(args.state_file)

    try:
        cdp_url, source, _profile = resolve_cdp_url(args.cdp_url, state, args.stores_dir)
        session, tab = open_cdp_from_state(cdp_url, state)
        try:
            start = time.time()
            snapshots = []
            opened = False
            last = None
            while (time.time() - start) * 1000 <= args.max_wait_ms:
                last = session.eval(js_composer_markers()) or {}
                snapshots.append(last)
                opened = bool(
                    last.get("visibleEditorCount", 0) > 0
                    or last.get("createPostText")
                    or last.get("whatTalkText")
                )
                if opened:
                    break
                time.sleep(max(0.1, args.poll_interval_ms / 1000.0))

            evidence = {
                "cdp_url": cdp_url,
                "cdp_source": source,
                "max_wait_ms": args.max_wait_ms,
                "poll_interval_ms": args.poll_interval_ms,
                "opened": opened,
                "last_markers": last,
                "snapshot_count": len(snapshots),
            }
            artifact = write_artifact(args.artifacts_dir, "04b-wait-manual-open", {
                "snapshots": snapshots,
                "opened": opened,
            })
            evidence["artifact"] = artifact

            update_state(args.state_file, STEP, evidence)
            if args.cdp_url:
                update_profile_fields(args.stores_dir, cdp_url=cdp_url)

            if opened:
                state_set(args.state_file, post_mode="feed_post", manual_open_required=False)
                emit_and_exit(step_result(
                    step=STEP,
                    status="ok",
                    evidence=evidence,
                    next_action="05_find_composer_editor.py",
                ))

            article_fallback = {"attempted": False, "ok": False}
            if not args.no_article_fallback:
                article_fallback["attempted"] = True
                session.navigate(args.article_fallback_url)
                time.sleep(max(0.1, args.article_fallback_wait_ms / 1000.0))
                article_scan = session.eval(JS_ARTICLE_SCAN) or {}
                article_ok = bool(article_scan.get("isArticlePage")) and bool(article_scan.get("titleEditorVisible")) and bool(article_scan.get("bodyEditorVisible"))
                article_fallback.update({
                    "ok": article_ok,
                    "scan": article_scan,
                    "url": args.article_fallback_url,
                })
                evidence["article_fallback"] = article_fallback
                if article_ok:
                    state_set(args.state_file, post_mode="article_post", manual_open_required=False)
                    update_state(args.state_file, STEP, evidence)
                    emit_and_exit(step_result(
                        step=STEP,
                        status="ok",
                        evidence=evidence,
                        next_action="05_find_composer_editor.py",
                    ))

            manual_hint = (
                "Composer not detected. Manually click 'Start a post' in browser, "
                "wait until editor appears, then rerun 05_find_composer_editor.py"
            )
            evidence["manual_hint"] = manual_hint
            state_set(args.state_file, manual_open_required=True)

            emit_and_exit(step_result(
                step=STEP,
                status="retryable",
                evidence=evidence,
                next_action="manual_open_required",
                error=manual_hint,
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
