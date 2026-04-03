---
name: lindkedin-post
description: Điều khiển LinkedIn post flow qua CDP browser đã mở sẵn, theo từng script nhỏ (step-by-step) với fallback manual-open khi auto không ổn định.
---

# Lindkedin Post Skill (CDP, step-by-step)

## Khi nào dùng
- Cần cho agent đăng bài LinkedIn bằng browser đã mở sẵn qua CDP.
- Muốn chạy **từng script nhỏ** để có thời gian đánh giá giữa các bước.
- Muốn ưu tiên an toàn: mặc định không submit thật nếu chưa xác nhận.

## Điều kiện bắt buộc
1. Chrome đã mở với remote debugging CDP.
2. LinkedIn đã đăng nhập sẵn.
3. CDP endpoint truy cập được.

## Nguyên tắc vận hành
- Không dùng 1 script lớn. Chạy theo chuỗi `00 -> 09`.
- Mỗi script trả JSON chuẩn (`status`, `evidence`, `next_action`, `error`).
- Mặc định ưu tiên an toàn:
  - `06_fill_post_text.py` là dry-run nếu chưa có `--apply`
  - `08_submit_post.py` bắt buộc `--confirm-submit`
- Không hardcode `cdp_url`/`post_style` trong script.
- Dùng store tại `lindkedin/stores/profile.json`.
- Nếu thiếu `cdp_url` hoặc `post_style`, **agent phải hỏi lại user** rồi lưu vào store trước khi chạy tiếp.

## Store (bắt buộc)
- File: `lindkedin/stores/profile.json`
  - `cdp_url`
  - `post_style`
- Set/update nhanh:
```bash
python3 lindkedin/scripts/00_store_profile.py --cdp-url http://HOST:9222 --post-style "short, clear, friendly"
```

## Luồng chuẩn

### A) Auto mode (experimental)
```bash
python3 lindkedin/scripts/00_store_profile.py --cdp-url http://HOST:9222 --post-style "..."
python3 lindkedin/scripts/00_cdp_connect.py
python3 lindkedin/scripts/01_pick_linkedin_tab.py
python3 lindkedin/scripts/02_ensure_feed.py
python3 lindkedin/scripts/03_find_start_post.py
python3 lindkedin/scripts/04_open_composer.py
python3 lindkedin/scripts/04b_wait_or_manual_open.py
```

Nếu `04/04b` vẫn `retryable` → chuyển mode B.

### B) Assisted mode (ổn định hơn)
1. Mở composer thủ công trên tab LinkedIn ("Start a post").
2. Tiếp tục:
```bash
python3 lindkedin/scripts/05_find_composer_editor.py
python3 lindkedin/scripts/06_fill_post_text.py --text "Hello from agent" --post-style "..." --apply
python3 lindkedin/scripts/07_check_post_ready.py
```
3. Submit thật (chỉ khi chắc chắn):
```bash
python3 lindkedin/scripts/08_submit_post.py --confirm-submit
python3 lindkedin/scripts/09_capture_post_result.py
```

## Script map
- `00_store_profile.py`: lưu `cdp_url` + `post_style` vào store
- `00_cdp_connect.py`: check `/json/version`
- `01_pick_linkedin_tab.py`: chọn tab LinkedIn
- `02_ensure_feed.py`: đảm bảo ở feed
- `03_find_start_post.py`: scan và chọn target "Start a post"
- `04_open_composer.py`: trusted click + marker check
- `04b_wait_or_manual_open.py`: poll marker, timeout thì yêu cầu mở tay
- `04c_diagnose_open_failure.py`: dump telemetry khi open fail
- `05_find_composer_editor.py`: tìm editor
- `06_fill_post_text.py`: điền text (dry-run mặc định)
- `07_check_post_ready.py`: check Post button
- `08_submit_post.py`: submit thật (gated)
- `09_capture_post_result.py`: chụp evidence sau submit

## Tham số dùng chung
- `--cdp-url`
- `--stores-dir` (default: `lindkedin/stores`)
- `--state-file` (default: `lindkedin/artifacts/state.json`)
- `--artifacts-dir` (default: `lindkedin/artifacts`)
- `--timeout-ms`

## Khi thất bại
- Chạy `04c_diagnose_open_failure.py --simulate-click`
- Đọc thêm:
  - `references/selectors.md`
  - `references/failure-modes.md`

## Output & artifacts
- Mỗi step in JSON result ra stdout.
- Mỗi step ghi artifact JSON timestamped trong `lindkedin/artifacts/`.
