# How to install a new skill scaffold

Script dùng để tạo khung skill:

```bash
bin/install <ten-skill>
```

Ví dụ:

```bash
bin/install my-skill
```

Sau khi chạy, cấu trúc được tạo:

```text
.agents/skill/my-skill/
  SKILL.md
  scripts/.gitkeep
  references/.gitkeep
```

## Quy tắc tên skill

- Không chứa dấu cách
- Không chứa `/`
- Chỉ nên dùng: chữ cái, số, `.`, `_`, `-`

## Lỗi thường gặp

- `destination already exists`: thư mục skill đã tồn tại → đổi tên khác hoặc xóa thư mục cũ.
- `invalid skill name`: tên chưa đúng format theo quy tắc phía trên.

## Available skill in this repo

- `lindkedin` (LinkedIn posting flow)  
  Path: `lindkedin/SKILL.md`

If you run:

```bash
bin/install linkedin
```

the installer will copy from local source `lindkedin/` into `.agents/skill/linkedin/`.
