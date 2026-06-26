# Implementation Plan — [MEMO-TIME] (optional time on memos)

> Companion to the locked spec [MEMO-TIME-optional-time-on-memos.md](MEMO-TIME-optional-time-on-memos.md). Plan = how; spec = what. Anchors are `file:line` at time of writing (2026-06-26); re-confirm before editing.

Column: **`due_time`**, `"HH:mm"` (24h) or `""`. Export bumps **v17 → v18**. All additive, non-destructive.

## Ordering constraint (hard)
Migration (Step 1) must land before any endpoint reads/writes `due_time`. `init_db()` runs at import, so one deploy is safe, but commit Step 1 first. Backend (1-12) precedes frontend (13-19).

## Backend — app.py

1. **Migration** — `init_db()` after the `map_groups` block (~`app.py:265`): `if "due_time" not in mcols: ALTER TABLE memos ADD COLUMN due_time TEXT DEFAULT ''`. `DEFAULT ''` backfills all rows to untimed. Memos only, no `projects` column.
2. **Validator** — module-level `DUE_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")` near `SAFE_IMG_NAME` (~`app.py:35`); helper `_clean_due_time(value)` near other `_clean_*` (~`app.py:1064`): strip, return value if regex matches else `""`. Malformed/markup → `""`.
3. **Version** — `APP_VERSION = "17"` → `"18"` (`app.py:29`).
4. **create_memo** (`app.py:1112-1136`) — add `due_time` to columns/VALUES; `due_time = _clean_due_time(data.get("due_time")) if due_date else ""` (time-without-date rejected at source).
5. **_perform_memo_update** (`app.py:1194-1295`, shared owner+guest) — compute `due_time` from payload-or-existing; enforce `if not due_date: due_time = ""` **after** the recurrence reschedule (`app.py:1242`) so recurring timed memos keep their time and clearing the date clears the time; add `due_time=?` to the UPDATE. `_next_due` needs no change (time is independent, carried verbatim).
6. **_memo_snapshot** (`1142-1161`) + **_log_revision** (`1171-1176`) — add `due_time` so revision/activity diffs track time changes. Both call sites.
7. **Duplicate** (`1382-1393`) — carry `due_time` in the duplicate INSERT.
8. **_share_memo_dict** (read DTO, `1593-1611`) — add `"due_time"` → read-only guests see it.
9. **_share_memo_dict_from_payload** (write DTO, `2541-2558`) — add `"due_time"`.
10. **share_update_memo** whitelist (`2400-2405`) — add `"due_time"` to the tuple (`2403`); route already enforces can_edit + approved + scope, delegates to Step 5. No new route (invariant 5).
11. **Export** `_build_export` (`2839-2906`) — `_memo_dict` is `dict(row)` → `due_time` emitted automatically; just change `"version": 17` → `18` (`2897`).
12. **Import** `api_import` memo loop (`3302-3375`) — parse `memo_time = _clean_due_time(memo.get("due_time"))` (dict branch) / `""` (legacy branch); UPDATE branch merge `merged_time = memo_time or _row_get(existing, "due_time")` + `due_time=?` (newer-wins never erases a present time); INSERT branch add column+value. Missing field = `""` (compat v1→v17).

## Frontend

13. **Shared helper** (invariant 6 / ADR-001) — `fmtMemoTime(t)` in `templates/partials/_shared.js.html`: regex-guard, `t.replace(':','h')` → `"14h30"`/`"14h00"` (minutes always). Only extract if byte-identical both pages, else inline.

### index.html
14. **Editor time input** (`3903-3914`, after `dateIn`) — native `<input type="time">`, value `memo.due_time||''`, `change` → `patchMemo(id,{due_time})`; ignore when no date; `× date` clear cascades server-side.
15. **Card badge** (`3635-3636`) — keep `dueInfo()` time-free; append `' · ' + fmtMemoTime(memo.due_time)` only when present.
16. **Tree/Plan meta col** (`2780-2781`) — append time fragment when `m.due_time`.
17. **Same-day sort** (`4312-4317`) — comparator: `due_date` asc, then **untimed before timed**, then `due_time` asc. `.slice().sort(byTime)` per section.
18. **(Optional) quick-add bar** (`4280-4291`) — add time input + `due_time` in POST. Not required by any done-when.

### share.html — guest parity
19a. **Editor input** (`1660-1667`, `canEditNow()`-gated) — `<input type="time">` → `put(id,{due_time})`.
19b. **Card badge** (`1514`) — append fragment when present → read-only guests see it.
19c. **Tree meta** (`1320-1324`) — append to `dueTxt`.
19d. **Same-day sort** (sections `1199-1201` + list builder) — mirror Step 17 `byTime`.

## Commit sequencing (atomic)
1) Steps 1+2+3 · 2) 4-7 · 3) 8-10 · 4) 11-12 · 5) 13-18 · 6) 19a-d.

## Test checklist (CLAUDE.md DB-copy procedure → maps to spec Done-when)
`python3 -m py_compile app.py`; `cp data/dashboard.db /tmp/test.db && DB_PATH=/tmp/test.db flask --app app run -p 8099`. Never touch `data/dashboard.db`.
- Migration on existing DB: app starts, `/api/memos` OK, existing `due_time:""`.
- Capture round-trip (owner): set/clear persists.
- Date-only preserved: `📅 <date>`, no fragment.
- Display: `📅 6 nov · 14h30`, on-hour `· 14h00`; relative helper unchanged.
- Same-day ordering: untimed first, timed ascending (AUJOURD'HUI).
- Export round-trip: re-import → all skipped, times preserved, `version` 18.
- Backward-compat import: v15/older → no-time, nothing else altered.
- Non-destructive upsert: set time, import older backup → time survives.
- Guest parity: editor sets/clears, read-only sees.
- Recurrence carry-over: next due advances, time identical.
- No invalid value: `99:99`/`<script>` → stored `""`.
- Re-import full export → 0 add; v1-no-uid → no dup.

## Risks / call-outs
- Migration before any read/write of `due_time` — commit Step 1 first.
- `if not due_date: due_time = ""` guard must run **after** recurrence reschedule (`app.py:1242`) — the one subtle sequencing point.
- Import merge (`merged_time`) mirrors `marker_color`: a newer export with intentionally-emptied time won't clear via import; UI clearing still works through `_perform_memo_update`. Matches spec's non-destructive priority.
- Append time only at badge/meta assembly sites, never inside `dueInfo()` (resolved decision: not in relative helper).
- No animation touched (invariant 8 idle); no new route/auth (invariant 5 intact); native input (invariant 6 intact).

## Critical files
- app.py · templates/index.html · templates/share.html · templates/partials/_shared.js.html
