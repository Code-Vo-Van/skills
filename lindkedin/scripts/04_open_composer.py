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
    write_artifact,
)

STEP = "04_open_composer"


JS_SETUP_TARGET_AND_LOG = r'''
(() => {
  window.__lindkedinClickLog = [];
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden';
  };
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();

  const pool = [...document.querySelectorAll('div[role="button"],button,[role="button"],a,div')].filter(visible);
  const candidates = pool.filter((el) => {
    const text = norm(el.innerText);
    const aria = norm(el.getAttribute('aria-label'));
    return text === 'start a post' || aria === 'start a post' || aria.includes('start a post');
  });

  const pick = candidates.find((el) => el.getAttribute('role') === 'button')
            || candidates.find((el) => typeof el.onclick === 'function')
            || candidates[0]
            || null;

  if (!pick) return { ok: false, candidateCount: candidates.length };

  const record = (name, e) => window.__lindkedinClickLog.push({
    name,
    type: e.type,
    ts: Date.now(),
    isTrusted: !!e.isTrusted,
    userActivationActive: navigator.userActivation ? navigator.userActivation.isActive : null,
    targetTag: e.target?.tagName?.toLowerCase() || null,
    currentTag: e.currentTarget?.tagName?.toLowerCase() || null,
  });

  for (const t of ['pointerdown','mousedown','mouseup','click']) {
    pick.addEventListener(t, (e) => record('target', e), true);
    document.addEventListener(t, (e) => { if ((e.target === pick) || pick.contains(e.target)) record('document', e); }, true);
  }

  const r = pick.getBoundingClientRect();
  let onclickSource = null;
  try { onclickSource = pick.onclick ? String(pick.onclick).slice(0, 120) : null; } catch (e) {}

  return {
    ok: true,
    candidateCount: candidates.length,
    target: {
      tag: pick.tagName.toLowerCase(),
      role: pick.getAttribute('role'),
      aria: pick.getAttribute('aria-label'),
      text: (pick.innerText || '').replace(/\s+/g, ' ').trim(),
      onclickType: typeof pick.onclick,
      onclickSource,
      rect: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) },
      x: Math.floor(r.left + r.width / 2),
      y: Math.floor(r.top + r.height / 2),
    },
  };
})()
'''


def main() -> None:
    parser = common_parser("Try opening LinkedIn post composer via trusted CDP click")
    parser.add_argument("--post-click-wait-ms", type=int, default=4000)
    args = parser.parse_args()

    state = load_state(args.state_file)

    try:
        cdp_url, source, _profile = resolve_cdp_url(args.cdp_url, state, args.stores_dir)
        session, tab = open_cdp_from_state(cdp_url, state)
        try:
            setup = session.eval(JS_SETUP_TARGET_AND_LOG)
            if not setup or not setup.get("ok"):
                evidence = {
                    "cdp_url": cdp_url,
                    "setup": setup,
                }
                update_state(args.state_file, STEP, evidence)
                emit_and_exit(step_result(
                    step=STEP,
                    status="retryable",
                    evidence=evidence,
                    next_action="03_find_start_post.py",
                    error="Cannot find Start a post target",
                ))

            x = int(setup["target"]["x"])
            y = int(setup["target"]["y"])

            session.send("Input.dispatchMouseEvent", {
                "type": "mouseMoved",
                "x": x,
                "y": y,
                "button": "none",
            })
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

            maybe_sleep_ms(args.post_click_wait_ms)

            click_log = session.eval("window.__lindkedinClickLog || []") or []
            markers = session.eval(js_composer_markers()) or {}

            auto_opened = bool(
                markers.get("visibleEditorCount", 0) > 0
                or markers.get("createPostText")
                or markers.get("whatTalkText")
            )

            evidence = {
                "cdp_url": cdp_url,
                "cdp_source": source,
                "target_setup": setup,
                "event_log_sample": click_log[:12],
                "markers": markers,
                "auto_opened": auto_opened,
            }
            artifact = write_artifact(args.artifacts_dir, "04-open-composer", evidence)
            evidence["artifact"] = artifact

            state_set(
                args.state_file,
                open_composer_last=evidence,
                post_mode="feed_post" if auto_opened else state.get("post_mode"),
            )
            if args.cdp_url:
                update_profile_fields(args.stores_dir, cdp_url=cdp_url)
            update_state(args.state_file, STEP, evidence)

            if auto_opened:
                emit_and_exit(step_result(
                    step=STEP,
                    status="ok",
                    evidence=evidence,
                    next_action="05_find_composer_editor.py",
                ))

            emit_and_exit(step_result(
                step=STEP,
                status="retryable",
                evidence=evidence,
                next_action="04b_wait_or_manual_open.py",
                error="Composer markers not detected after trusted click",
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
