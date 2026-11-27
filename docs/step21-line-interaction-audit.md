# Step 21 — Real LINE learning interaction: reference audit and acceptance plan

2026-11-28 (Asia/Taipei). Read-only comparison; no implementation merged or runtime switched.

## Reference

- @joeuser-max commit [1ef63c8e7d98d344bc7297ac744706f2a59608ec](https://github.com/joeuser-max/python-14-studybot/commit/1ef63c8e7d98d344bc7297ac744706f2a59608ec), author timestamp 2026-11-28 01:10:01 +0800. Commit timestamp is not independently verified push time.
- Commit subject: 確認設定課表和可用時段和讀書時段line提醒可用和若無達成讀書重新安排讀書進度和下課後line主動提醒補筆記和補完筆記後自動根據內容安排讀書計畫.
- Our accepted code baseline [0e0c0bd](https://github.com/joeuser-max/python-14-studybot/commit/0e0c0bde73e149c63f4266e6c12a9575484f1fc6). GitHub compare reported diverged, 222 ahead/1 behind relative to that teammate commit, merge base a7ff113. Counts describe Git ancestry, not contribution value. Do not merge/cherry-pick wholesale: both branches modify app.py, line_bot.py, scheduler.py, storage.py, reminder_worker.py, tests and docs, and have different product flows. Reference commit also removes nested old files/data/tests. Do not apply those deletions to our baseline.

## 1. What the teammate commit actually implements

Based on the commit diff, README and relevant source/test files. Commit subject and docs are not independent proof of a live device pass.

| Interaction | Reference code / behavior |
|---|---|
| Class end reminder | scheduler.py: catch up for 60 min after due time; changed class end time gets a new reminder identity. Worker sends 補筆記 prompt. |
| Guided note state machine | line_bot.py: 補筆記 → weekday → course number → self-rated understanding 1–5 → course progress (Ch.3 / p.42 / 略過) → note text or file. Course date based on recent ended course; cancel/timeout. |
| File note | LINE download, DOCX/PDF/UTF-8 TXT extraction; preserve PDF original; invalid formats rejected. storage.py attachment APIs and app.py download/delete controls. |
| Reading task | Derive review range from course progress, otherwise ask range. User specifies minutes and deadline. Preview feasible slots, pick one; only then create task and scheduled plan. No feasible slot: adjust minutes/deadline/availability, do not create phantom task or silently split. 先不用 retains note. |
| AI | reminder_worker._study_session_message: consented task-linked note organized at actual study start; AI output summary/key points/questions/review advice, not autonomous scheduling. AI failure preserves note/task. |
| Study reminders | scheduler._session_reminder_id includes scheduled start; a replan in same slot can trigger a new reminder. 15-minute study-start catch-up; check-in on completion time. |
| Progress feedback | 完成 or 未完成 + task code; unfinished requests remaining minutes and replans; no reply is not completion. |
| Regression evidence | tests/test_integration.py guided note, dedup, no feasible slot, chosen slot, DOCX/PDF and course reminder catch-up; tests/test_scheduler.py new start/check-in in same slot after replan; tests/test_ab_integration.py AI deferred until study start; tests/test_storage_editing.py owner-scoped attachment and clear-data behavior. These use mocks/temp files; actual API/live delivery not independently confirmed in this review. |

## 2. Existing Final 2.0 versus reference: preserve our workflow

Our baseline already contains signed LINE and file paths, note question candidates/confirmation via note_tasks, synthetic purple tasks, 30-minute task workflow, owner-scoped scheduler, calendar, mock chat, and line_study_ai study-start summary with consent. Tests/test_line_signed_api_contract.py mocks LINE/OpenAI; tests/test_line_final_integration.py covers study AI opt-in/caching and selected-task replanning/completion. Do not replace these with a different UI or assume teammate's manual duration/slot selection should supersede purple question-candidate workflow.

Two differences require product decision:
- Reference asks the user to select review range, duration, deadline, then a feasible slot. Our Final 1.1/V2 flow uses independently selectable AI question candidates (with confirmed 30-min tasks) and draggable web scheduling; prefer preserve this as default and selectively use explicit minutes/deadline and feasible-slot feedback if useful.
- Reference defers AI until study start; ours has note analysis/question extraction as well as study-start organization. Separate two purposes: early candidate extraction versus review-time note summary. Do not double-call paid AI unnecessarily or infer consent.

## 3. Root blocker: same identity, different data

Currently official bridge routes follow / 開啟網頁 into friend-e2e, while other messages go to legacy Flask 5000; web reads friend-e2e. Legacy and demo use different owner IDs/data directories. The demo UI disables reminders and uses mock AI; seeded_pending_auth is excluded from live legacy handlers and worker. User's Step 20 test proves original bot note handling remains functional, not that new user's note lands in their authenticated website.

Required invariant for Step 21:
LINE verified subject -> unique seeded owner -> same owner-scoped records for web and LINE -> scheduler reads same owner -> consented worker pushes to same subject -> signed reply updates same task.

Recommend a new explicit internal-interaction mode and an isolated worker/data root, with owner resolution before routing (not shared demo_user_001); preserve existing legacy behavior and both bots. No credential copying into Git, no migration/reset of original data, no live model calls or pushes without specific opt-in. Keep two-seat limit and OAuth, do not treat internal mode as public. The current official bridge dispatch logic may need modification; avoid routing the same note event to two handlers. If using existing legacy handlers, re-evaluate gated seeded status narrowly rather than remove checks globally. Worker must not send synthetic pre-seeded events/tasks accidentally: use intentional test data and explicit per-user reminder preferences; define opt-in and test gating. One writer per reminder stream and idempotent sends.

## 4. Sequential acceptance plan (one existing account, actual phone)

| Step | User action | Evidence required |
|---|---|---|
| 21.1 Read-only reality check | In authenticated website add a uniquely named synthetic course/availability/task, send 補筆記 to official OA | Compare owner-scoped counts/marker, which course list is returned; distinguish existing legacy data from authenticated demo. No destructive operation. |
| 21.2 Same-store note | Follow guided LINE steps for the test course, submit synthetic text note (then optional small PDF) | Web refresh shows exact marker in same owner feedback; correct course/progress; replay doesn't duplicate; no other store changed. |
| 21.3 AI candidates and planning | Explicitly opt into selected AI mode; generate candidate, confirm one question | New purple task appears in same website; distinct IDs; correct 30-min default, source note, deadline; no tasks created without confirmation. If AI mocked, label it; actual AI response only when authorized. |
| 21.4 Web -> LINE | Add future test slot, schedule task, enable only intended reminder and run isolated worker | Actual device receives study start once; same task ID/owner and reminder status sent; optional authorized AI summary, not mock presented as real. |
| 21.5 LINE -> Web | Respond 未完成 + task identifier and remaining minutes, then confirm replan; later 完成 | Updated remaining_minutes/plan in authenticated web; correct replan with feasible slot; completed task not scheduled; no duplicate reminder on replay. |
| 21.6 Class-end loop | Set one test course to end a few minutes later, offset 0, explicit reminder opt-in | Real push asks for 補筆記; note links to correct class reminder and same feedback store; successful response counted. |
| 21.7 Freeze | Run full tests and record actual phone acceptance plus isolated counts | No existing V2/Final 1.1 regressions; no main merge; record limitations and rollback. |

Next practical action is 21.1; not a feature implementation or acceptance result yet. The user's request explicitly deferred cloud and further two-account live security acceptance. Do not expand scope beyond real interaction demonstration unless requested. Keep previously confirmed Final 2.0 SHA unchanged as reference.
