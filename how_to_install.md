# How to install skills

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

## Install using local repo script

If you already cloned this repo:

```bash
bin/install linkedin
```

## List installable skills

```bash
bin/install --list
```

## Create a new starter scaffold

Use `--scaffold` when you want a blank template instead of downloading an existing skill:

```bash
bin/install --scaffold my-new-skill
```

## Available skill(s) in this repo

- `linkedin` (source folder: `linkedin-post/`)
