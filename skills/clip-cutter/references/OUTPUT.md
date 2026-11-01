# Plan JSON (`--plan-only`)

## Single game
| Field | Meaning |
|---|---|
| `clips[]` | In game order (at-bat, pitch). One clip per pitch. |
| `clips[].key` | MLB guid (= feed playId) or content id; cache filename |
| `clips[].headline` / `inning` / `dur` | MLB headline; e.g. `bot 9`; seconds from MLB metadata (reel trims to this) |
| `clips[].anchor` / `how` | feed playId it's tied to; `guid` (exact), `abs-review` (ABS clip → review event), `publish-time` (only with `--keep-unmapped`) |
| `clips[].atBatIndex` / `eventIndex` | position in play-by-play |
| `clips[].abs` | ABS challenge clip |
| `clips[].pre` / `away` / `home` / `half` / `inningNum` | score BEFORE the at-bat and context used for the burned-in label |
| `clips[].wpa` / `home_wpa` / `score` | ranked plans only: raw at-bat \|WPA\|, signed home-perspective WPA, ranking score after ABS/team weights |
| `clips[].for_team` | team plans only: did the at-bat help the team |
| `dropped[]` | `{headline, why}`, e.g. `taxonomy:interview`, `too-long:92s`, `alt-angle`, `unmapped`, `abs-off` (ABS challenge; off by default), `dup-anchor`, `below-cut` |
| `missed_hot[]` | top-\|WPA\| at-bats with no clip (ranked plans) |
| `seconds` | sum of clip durations |

## Slate (`--date`) and team (`--team`) extras
| Field | Meaning |
|---|---|
| `games[]` | `{gamePk, label, card[2], clips[], seconds, best, missed_hot}`, in start order (earlier game first; doubleheader G1 before G2) |
| `skipped[]` | `{gamePk, why}` (`no-data`, `status:<state>`, `below-cut`) or `{team, why}` (`no-game`, `no-playable-game`) |
| `card_seconds` / `total_seconds` | 2.5 s per game block; clips + cards (what the budget checks) |
| `team` | team plans: `{id, abbr, name}` |
