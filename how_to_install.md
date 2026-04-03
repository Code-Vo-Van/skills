# How to install & use skills

## Quick install from GitHub (recommended)

Use this one-liner from any folder:

```bash
curl -fsSL https://raw.githubusercontent.com/Code-Vo-Van/skills/main/bin/install | bash -s -- linkedin
```

This creates:

```text
.agents/skill/linkedin/
  SKILL.md
  scripts/
  references/
```

## Install aliases

These skill names all map to the same LinkedIn posting skill source (`linkedin-post/`):

```bash
bin/install linkedin
bin/install linkedin-post
bin/install lindkedin   # legacy alias
```

## Install using local repo script

If you already cloned this repo:

```bash
bin/install linkedin
```

Tip: destination folder follows the skill name you pass:
- `bin/install linkedin` -> `.agents/skill/linkedin/`
- `bin/install linkedin-post` -> `.agents/skill/linkedin-post/`

## List installable skills

```bash
bin/install --list
```

## How to use after install

1. Open the installed guide:
   ```bash
   cat .agents/skill/linkedin/SKILL.md
   ```
2. Run the step scripts from the instructions (CDP URL + post style first):
   ```bash
   python3 .agents/skill/linkedin/scripts/00_store_profile.py --cdp-url http://HOST:9222 --post-style "short, clear, friendly"
   python3 .agents/skill/linkedin/scripts/00_cdp_connect.py
   ```
3. Continue step-by-step (`01` -> `09`) as documented in that SKILL.md.

## Create a new starter scaffold

Use `--scaffold` when you want a blank template instead of downloading an existing skill:

```bash
bin/install --scaffold my-new-skill
```

## Available skill(s) in this repo

- `linkedin` (source folder: `linkedin-post/`)
- `linkedin-post` (explicit alias)
- `lindkedin` (legacy alias)
