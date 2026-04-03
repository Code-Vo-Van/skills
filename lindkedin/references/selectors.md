# Selectors / markers notes (LinkedIn post flow)

## Start a post target
Observed reliable candidate shape in current environment:
- `tag`: `div`
- `role`: `button`
- visible text: `Start a post`
- `onclick`: function (observed source preview: `function hv(){}`)

Primary query used in scripts:
```css
div[role="button"], button, [role="button"], a
```
then filter by normalized `innerText`/`aria-label` = `start a post`.

## Composer markers
Composer is considered open when at least one condition is true:
- page text contains `Create a post`
- page text contains `What do you want to talk about`
- visible editor exists:
  - `div[role="textbox"]`
  - `[contenteditable="true"]`
  - `textarea`

## Post button scan
Scan visible:
```css
button, [role="button"], a
```
then filter text/aria containing whole word `post`.
Preferred choice:
1. text exactly `Post`
2. aria exactly `Post`
3. first `post-like` candidate
