# [MEMO-TIME] — Optional time on memos

> Status: **VALIDATED & LOCKED** (reviewer score 100/100, 2026-06-26). Immutable contract — changes require a new spec revision. Tag: `[MEMO-TIME]`.

## Target

A memo with a due date may optionally carry a time of day, which is captured, stored, displayed alongside the date, used to order same-day memos, preserved across export/import, and visible to both owner and approved guests.

## Hard constraints

- **Time is optional and depends on a date.** A memo can have a date with no time (current behavior, must keep working). A time without a date is not a valid state.
- **Time format is `"HH:mm"` (24-hour) or empty** (empty = no time). Any other stored value is invalid.
- **Additive, non-destructive storage.** Adding or clearing a time never alters the existing due date or any other memo field. The current date-only behavior is unchanged for every memo that has no time.
- **Export/import stays backward-compatible (CLAUDE.md invariant 1 & 2).** Exports from every prior version (v1→v17) remain importable; a memo with no time field imports as "no time". Import is non-destructive and follows the existing newer-wins upsert: an import never overwrites a present time with an absent/older one. The export `version` is incremented and the new export remains importable.
- **No new authentication or route surface for guests beyond the existing share scope (invariant 5).** Approved guests with edit rights set/clear the time only through the already-scoped share update path; read-only guests see it. No new public capability.
- **No build step, no external runtime dependency (invariant 6).** Delivered pages stay self-contained HTML. The time input uses native browser capability already permitted by the project.
- **Both surfaces covered.** The owner dashboard and the shared guest page both let an editor set/clear the time and both display it wherever a memo's date is shown.
- **Recurrence semantics unchanged.** Recurring memos still reschedule on the date rhythm; if a time is present it is carried over verbatim to the next occurrence. No new recurrence rule is introduced.
- **No HTML/script injection.** A stored time that is not a strict `"HH:mm"` (or empty) is rejected/normalized to empty, consistent with the project's other validated fields.

## Non-goals

- **No standalone time picker, duration, or end-time.** Single optional start time per memo only.
- **No timezone handling for the time field.** The time is a wall-clock label tied to the memo's date; multi-timezone display of memo times is out of scope (distinct from the existing world-clock feature).
- **No reminders, notifications, or alarms** triggered by the time. Display and sort only.
- **No Agenda/calendar view.** [MEMO-TIME] only adds the field; `[AGENDA]` is a separate item that may later consume it.
- **No change to recurrence rhythms or `_next_due` logic** beyond carrying the time forward.
- **No time on projects, links, comments, or subtasks.** Memos only.
- **No retroactive backfill** of times onto existing memos.

## Done-when

- **Capture:** In the memo editor, next to the existing date field, an optional time field is present; setting it and saving persists the time; clearing it and saving removes the time. Verified by editing a memo, reloading, and observing the value round-trips (owner page).
- **Date-only preserved:** A memo saved with a date and no time shows and behaves exactly as before. Verified by saving date-only and confirming display reads "📅 <date>" with no time fragment.
- **Display:** A memo with a time shows date + time together in French wall-clock format with minutes always shown (e.g. "📅 6 nov · 14h30", "📅 6 nov · 14h00" on the hour); a memo without a time shows date only (e.g. "📅 6 nov"). The time appears only in this absolute "📅 … · …" badge, not in the relative-date helper. Verified by inspecting both cases on the card/detail.
- **Same-day ordering:** Within a day's grouping (e.g. Today / Upcoming sections), **untimed (all-day) memos sort before timed memos**, then timed memos ascending by time. Verified by placing ≥2 same-day memos (one untimed, two timed at different hours) and confirming the untimed one is first, timed ones in ascending order.
- **Export round-trip:** Exporting then re-importing a full backup that includes timed and untimed memos yields zero spurious changes (all "skipped") and preserves every time value. Verified by export → import on a copy of the DB and checking the import report.
- **Backward-compat import:** Importing any pre-v17 export (no time field) succeeds with every affected memo treated as "no time" and no other field altered. Verified by importing a v15/older sample.
- **Non-destructive upsert:** Re-importing an older export that lacks the time field does not erase a time already set on a matching memo. Verified by setting a time, importing an older backup of the same memo, and confirming the time survives.
- **Guest parity:** On the shared page, an approved editor guest can set/clear the time within scope and any approved guest sees it rendered. Verified on a share link (edit and read-only).
- **Recurrence carry-over:** Completing a recurring memo that has a time produces the next occurrence with the same time and a rescheduled date. Verified by checking a recurring timed memo, confirming next due date advances and time is identical.
- **No invalid value persists:** Submitting a malformed time value results in an empty (no-time) memo, never a stored malformed string or markup. Verified by attempting a non-`HH:mm` value.

## Resolved decisions

- Same-day ordering: untimed (all-day) memos sort **before** timed memos, then timed ascending.
- Time format: French wall-clock, minutes always shown ("14h30", "14h00" on the hour).
- Time appears only in the absolute "📅 … · …" badge, not the relative-date helper.

## Stakeholders

- Decider / Owner: Fabien (sole owner of the dashboard).
- Consumer: Fabien (owner UI) and approved share guests (read, and edit where granted).

## Context

- Backlog source: `IDEAS.md` → Quick wins → `[MEMO-TIME]`. Flagged a priority and a prerequisite for `[AGENDA]`.
- Governing invariants: `CLAUDE.md` — invariant 1 (export backward-compat, current latest v17), invariant 2 (import never destructive), invariant 5 (guest scope), invariant 6 (no build / self-contained HTML), invariant 8 (animation rules — only if any UI animation is touched).
- Memory bank: `.claude/memory/MEMORY.md` lists `[MEMO-TIME]` under the priority backlog.
- This spec is a behavioral contract. Column names, export version number, exact file edits, and validation helpers belong to the **plan**, not here.
