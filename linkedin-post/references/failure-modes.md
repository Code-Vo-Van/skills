# Failure modes and handling

## 0) Missing profile config (`cdp_url` / `post_style`)
Symptoms:
- script trả `status=retryable`
- `next_action=ask_user_for_cdp_url` hoặc `ask_user_for_missing_profile`

Handling:
1. Hỏi user bổ sung field còn thiếu.
2. Lưu lại:
   ```bash
   python3 linkedin-post/scripts/00_store_profile.py --cdp-url http://HOST:9222 --post-style "..."
   ```
3. Chạy lại step vừa fail.

## 1) Trusted click but composer not opening
Symptoms:
- click events `isTrusted=true`
- `userActivationActive=true`
- no visible composer editor afterwards

Handling:
1. Run `04_open_composer.py`
2. If still retryable, run `04b_wait_or_manual_open.py`
3. If still retryable, run `04c_diagnose_open_failure.py --simulate-click`
4. Switch to Assisted mode (manual open composer once), continue `05..09`

## 2) Editor not found
Symptoms:
- `05_find_composer_editor.py` returns retryable

Handling:
- Re-open composer (auto or manual)
- Re-run `05_find_composer_editor.py`

## 3) Post button not found / disabled
Symptoms:
- `07_check_post_ready.py` no preferred post button
- or button exists but disabled

Handling:
- ensure editor has content (`06_fill_post_text.py --apply`)
- verify account/post permissions in UI
- re-run `07_check_post_ready.py`

## 4) Accidental publish risk
Mitigation built-in:
- `08_submit_post.py` requires `--confirm-submit`
- Without confirm flag script fails safely

## 5) Endpoint / tab issues
Symptoms:
- CDP unreachable
- no LinkedIn page tab

Handling:
- run `00_cdp_connect.py`
- run `01_pick_linkedin_tab.py`
- ensure Chrome CDP port and logged-in LinkedIn tab are open
