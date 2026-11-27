# ClassPulse LINE-friend Demo: setup / contribution log

**Recorded:** 2026-11-28 (Asia/Taipei)  
**Development branch:** `feature/line-friend-demo`  
**Starting point:** Final 1.1 (`feature/final-note-ai-loop-ui-line-e2e`, commit `10b5fc5`)  
**Owner of local setup and field debugging:** @Onlynotonly

This records the work and diagnostic observations made during the guided
ClassPulse LINE integration. It is an engineering contribution log, **not**
a dump of the conversation or of any secrets.

## Objective and acceptance criteria

A student adds the existing ClassPulse LINE Official Account as a friend;
the signed `follow` webhook creates **one isolated Demo identity**, assigns
independent fictional sample lessons/notes/tasks, and replies with useful
onboarding options. Subsequent LINE messages operate on that student's own
data. A **separately authenticated** web console shows the same student's
tasks. It must not share `demo_user_001` data across visitors.

## Completed setup / field observations (user-performed)

1. Enabled **Messaging API** for the existing ClassPulse Official Account,
   using the user's own LINE Developers Provider. No new OA was necessary.
2. Located LINE Channel Secret and Access Token; stored local values in a
   git-ignored `.env` (no credential is recorded here).
3. Cloned `joeuser-max/python-14-studybot` to macOS, selected the tested
   Final 1.1 feature branch, and activated a Python virtual environment.
   Corrected an initial `origin` error caused by running Git from the
   unrelated `Forjava` directory.
4. Started the Flask LINE Webhook service. The `/health` endpoint returned
   `{"ok":true}` on localhost.
5. Installed ngrok on Apple Silicon, created an HTTPS tunnel, and set the
   LINE Developers Webhook URL to `https://<active-tunnel>/webhook`.
6. Diagnosed initial LINE Verify failures: three `POST /webhook` requests
   produced **403** while ngrok forwarded to `http://localhost:5000`.
   Retargeting ngrok to explicit IPv4 `http://127.0.0.1:5000` resolved
   the issue and the user reported **Verify success**. This is consistent
   with a localhost/IPv4/IPv6 port-binding mismatch on macOS; it does not
   conclusively prove which process produced the 403.
7. A user-provided LINE screenshot showed a ClassPulse-generated
   `尚未綁定` reply, establishing real incoming webhook + outgoing bot
   reply reachability. Subsequent binding and note steps were acknowledged
   in chat, but full end-to-end evidence for each data write is not yet
   attached to a test run.

## Step 12.1 delivered on this branch

- `line_demo_registration.py`: atomic
  `get_or_create_line_user(line_user_id)` returns an existing row or creates
  an independent `lineuser_...` identity; marks `demo_status=pending_seed`.
  It does **not** automatically opt in to reminders or AI.
- `tests/test_line_demo_registration.py`: isolated two-user identity,
  retry/idempotence, concurrent registration, invalid ID and legacy-user
  preservation tests. Uses temporary storage; no real LINE calls.
- `.gitignore`: ignore `data/` entirely, including generated JSON,
  file locks and attachments. Existing tracked files, if any, require
  separate review before claiming they are protected by `.gitignore`.

## Deliberate limits / next phases

**This branch is NOT a public multiuser Demo yet.** The registration helper
is not called by `line_bot.py` at this step. The existing
`綁定 <code>` path and `demo_user_001` are unchanged, and the Streamlit
UI still uses a hardcoded user ID.

- **12.2 — Webhook integration:** only accept signed personal `follow`
  events, idempotently register, handle follow/unfollow/re-add, and reply
  without relying on a shared binding code; add signed webhook tests.
- **12.3 — Per-user sample seed:** use fictional records with unique IDs,
  preserve ownership in all collections, prevent duplicate seeding and
  accidental reminders.
- **12.4 — Authenticated web entry:** add LINE Login/LIFF or another
  verified session-to-LINE identity mechanism. A public URL with only
  `?user_id=` is **not** access control. Maintain end-to-end data isolation.
- **12.5 — Public hosting:** deploy persistent HTTPS webhook, scheduled
  worker, web frontend and durable shared database; a Mac/ngrok tunnel is
  only a development environment. Implement deletion/privacy controls.
- **12.6 — Acceptance:** test two distinct LINE accounts, independent
  note/task state, blocked cross-user access, duplicate delivery, failure
  handling, onboarding and actual device delivery.

## Attribution and scope

- **@Onlynotonly:** LINE OA/Provider activation; macOS local setup;
  Channel configuration; ngrok/IPv4 Webhook diagnosis; real-device
  integration feedback; proposal to build one-click, independent Demo
  onboarding and record those steps as project contributions.
- **Existing code:** ClassPulse V2/Final 1.1 frontend, signed Webhook,
  note intake and task workflows were already present; this log does not
  claim they were newly built in Step 12.1.
- **New branch implementation:** registration helper, tests, privacy
  ignore rules and this contribution log, created on @Onlynotonly's
  GitHub connection.

**Security:** never commit or post Channel Secret, Channel Access Token,
LINE User IDs from real devices, ngrok Authtoken, binding codes, or
raw private classroom notes in GitHub comments or screenshots.
