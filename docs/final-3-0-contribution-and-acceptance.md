# ClassPulse Final 3.0 — contribution and acceptance record

## Accepted source baseline (2026-11-28)

- Code commit: e835140e0658717e1fdda14ab7ec07c7d8554ed3
- Archive branch: archive/final-3.0, created from exactly that commit. The SHA, not the movable branch name, is the authoritative reproducibility anchor.
- Working branch: feature/line-friend-demo.
- Local result supplied by operator: 223 passed in 2.04s. Step 23 launcher reached Managed services running at existing Quick Tunnel origin. All ten Step 23 checks subsequently confirmed by operator.
- The archive stores source and documentation, not local secrets, user records, attachments, runtime logs, browser cookies, virtual environments or LINE Console settings. Not a backup of the user's live data.

## Contribution and evidence

Implementation/coordination on Onlynotonly's feature branch, with AI-assisted coding and operator testing. Do not infer sole authorship of the inherited project from this record. Earlier V2, Final 1.1 and Final 2.0 contributions are documented separately. The teammate's main changes are independent work and are not overwritten or claimed here.

| Stage | Increment | Evidence and scope |
| --- | --- | --- |
| 17–20 | Authenticated per-owner browser, isolated seeded demo, signed LINE follow/recovery, original OA bridge and legacy coexistence | Prior accepted single-account E2E; 186 regression tests at Step 20; PR 20 comment 7228880141 |
| 21.2 | Shared owner-specific LINE/web note store, note intake and search | 189 offline and operator 7/7; comment 7229108917 |
| 21.3 | Provider-selectable real Gemini API, per-note consent, question-level confirmation and purple tasks | 199 offline; CI run 46076031734; operator 8/8; comment 7229369179 |
| 21.4 | Real study-start push with cached AI summary, persisted retry key and dedup | 204 offline, operator 7/7; comment 7229429628 |
| 21.5 | Study-end check-in, explicit completion/remaining minutes, target-only replan | Initial CLI SyntaxError corrected at 8fdc36e; 209 offline and corrected operator 8/8; comment 7229568888 |
| 21.6 | Exact class occurrence reminder, direct rating, optional AI or save-only | Included in final regression suite; class push confirmed through Step 22; standalone full 8/8 course-note consent checklist not separately confirmed |
| 22 | Continuous dispatcher, signed owner reminder opt-in/out, ordinary scheduled tasks, cached-only AI, restart dedup | Operator 218 offline and 8/8; comment 7229779416 |
| 23 | Foreground service supervisor, readiness, signed empty webhook probes, status/logs, controlled shutdown and restart | Actual 223 passed in 2.04s transcript; operator 10/10; comments 7229865932, 7229889884 |

Evidence links: https://github.com/joeuser-max/python-14-studybot/pull/20 (comment anchors above). Latest CI on accepted code SHA has not been independently confirmed; local acceptance is not a substitute for CI or production validation.

## End-to-end product path

1. Original LINE OA follow or 開啟網頁 → own synthetic demo → external-browser LINE Login.
2. Create/edit course and schedule in the authenticated web UI.
3. Signed LINE 開啟提醒 opts the owner into automatic class and study push; 關閉提醒 revokes future automatic sends.
4. Non-seeded enabled course ends → exact course/date rating → optional external AI consent → note.
5. Gemini returns structured summary/questions; only confirmed questions become 30-minute purple pending tasks. Drag or schedule into a legal slot.
6. Study-start push uses existing cached summary if available; no new model call. Study-end check-in accepts completion or remaining minutes; replan only the target task.
7. Web and LINE share owner-scoped data. Existing legacy Flask continues to handle non-personal routes.

## Local operating instructions

See [local-launcher.md](local-launcher.md). In existing staging worktree:
- bash classpulse.sh start
- bash classpulse.sh status
- bash classpulse.sh logs worker
- bash classpulse.sh stop

Legacy Flask 5000 and existing Quick Tunnel remain external prerequisites in accepted default mode. Launcher owns five staging services. Optional --new-tunnel and activate mode requires LINE Console changes and remains unverified live. Never commit secrets or data. Do not start an extra manual worker alongside the dispatcher.

## Integration boundary at freeze

- main: 1ef63c8e7d98d344bc7297ac744706f2a59608ec.
- Main and accepted code were diverged: feature ahead 263 / behind 1, merge base a7ff1138133ba4485d8135ed15d8ce48154be845.
- PR 20 is already merged into feature/rich-demo-fixtures at 97fbba82fb7d5c83a8211e4724d293b1e640527b, with frozen head e236aae34b651becdd2ce8a1171c5db2cf4796d5. Later work is not included in that merge.
- Relative to feature/rich-demo-fixtures, accepted code was ahead 27 / behind 3. Review remaining changes against that integration branch, not by blindly merging to main. Archive branch is not a deployment or authorization to merge.
- Previous Golden Baselines: V2 PR 16 head be687f7b96019744bdf10b9e6a4ce (prefix); Final 2.0 0e0c0bde73e149c63f4266e6c12a9575484f1fc6.

## Unverified / deliberately deferred

Private internal demo (1–2 people); full real two-account E2E and public rollout deferred. No cloud deployment or permanent public domain. New Quick Tunnel mode not tested live; changing origin requires LINE Console changes and new browser login. Mac must remain online and awake. JSON files are individually locked/atomically replaced but cross-file updates are not transactional. Reminder catch-up window is 15 minutes; busy note interaction can miss class reminders; a missed study start does not trigger its check-in. Seeded examples are excluded from automatic pushes. Web AI is mock; live Gemini is only the consented LINE note flow. Live class-note checklist not separately attested. Operator's existing OA/legacy Flask remains independent. No claim of production readiness or full multi-user security verification.

No main modification, merge, process restart, secret rotation, or runtime data change was performed during archival.
