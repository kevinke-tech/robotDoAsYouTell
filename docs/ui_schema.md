# UI Schema Contract

This document defines the normalized `ui` payload contract returned by skills.

## Entry Rules

- `ui` is optional.
- If present, `ui` must be an object.
- `ui.type` is required and normalized to lowercase trimmed string.
- Invalid payloads are converted into:
  - `{"type":"info_card","title":"UI payload invalid","message":"..."}`.

## Supported Types

### `music_player`

Required:
- `audio_url` (non-empty string)

Optional:
- `title`
- `cover`
- `artist`

### `video_player`

Required:
- `video_url` (non-empty string)

Accepted aliases (normalized to `video_url`):
- `videoUrl`
- `url`

Optional:
- `title`
- `poster`

### `awaiting_slot`

Required:
- `slot` (non-empty string)
- `question` (non-empty string)

Optional:
- `title`
- `can_cancel` (boolean)

### `info_card`

Open schema for generic explanatory cards.

### `key_value`

Open schema for generic key/value presentations.

### `html_card`

Purpose:
- One-shot ephemeral custom UI rendered in an isolated iframe.

Required:
- At least one of:
  - `html` (string)
  - `srcdoc` (string)
  - `js` (string)

Optional:
- `title`
- `css`
- `height` (number; frontend clamps to safe range)
- `source`
- `source_url`

## Extensibility

Unknown `ui.type` values are currently accepted and passed through after
`type` normalization, to keep dynamic generation flexible.
