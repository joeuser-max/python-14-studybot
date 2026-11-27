# ClassPulse LINE-friend Demo: setup / contribution log

**Recorded:** 2026-11-28 (Asia/Taipei)  
**Development branch:** `feature/line-friend-demo`  
**Starting point:** Final 1.1 (`feature/final-note-ai-loop-ui-line-e2e`, commit `10b5fc5`)  
**PR target:** `feature/rich-demo-fixtures` (already includes Final 1.1; existing PR CI workflow is configured on this base)  
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

## Step 12.2 — Local acceptance (2026-11-28, Asia/Taipei)

- @Onlynotonly synchronized Mac branch `feature/line-friend-demo` to
  `514d0f6` by saving the redundant local .gitignore edit in a stash,
  then fast-forwarding. Runtime data remains ignored.
- Python 3.12.2 confirmed. User reported registration test passed; exact
  pytest count and duration were not supplied.

## Step 13 — Signed follow registration (implementation; verification pending)

- `LINE_FRIEND_DEMO_ENABLED=1` opts into the new follow route;
  absent/other values retain the old binding flow.
- A signed personal follow registers or resolves exactly one account.
  Invalid IDs, group/room and standby follow events do not register.
  Storage failures are not marked processed.
- Existing legacy users retain their IDs and preferences. An atomic
  binding guard rejects a LINE ID already linked to a separate account.
- Pending users receive a truthful status response and cannot enter
  text/file/binding flows, even after the switch is disabled.
- Offline Webhook tests use fake HMAC credentials, temporary storage and
  mock reply calls. No real LINE credentials or runtime data are committed.
- Do not enable the switch on the public tunnel yet. CI and local tests,
  individual demo seeding, web authorization and two-phone E2E remain
  required. Flask/ngrok settings remain unchanged.

## Step 13 — Acceptance

- Mac local module + Webhook tests: user reported `20 passed` after resolving
  missing pypdf during collection; Step 12 had terminal evidence of 9 passed in 0.35s.
- CI run 46062648073 succeeded. No live friend follow verified.

## Step 14 — Personal synthetic seed

- Reuse only `demo_data.sample_records` (pure fictional templates), never copy
  another user's runtime data or call the shared demo reset function.
- Per-user seed lock, persisted time anchor, stable globally distinct identifiers,
  insert-only per-file updates and final status marker allow a failed seed to
  resume without duplicating existing rows. This is not a cross-file transaction.
- Six datasets: 14 courses, 15 tasks (including one illustrative confirmed
  purple 30-minute task), 7 availability slots, 3 plan entries, 5 notes
  with mock analyses on three, 3 external events. Other unresolved questions
  remain candidates. No actual model calls, fake sent reminders, or shared
  webhook replay IDs. All seeded rows are marked with demo_seed_version.
- Successful seed changes pending_seed to seeded_pending_auth; both states
  deny LINE note/task/file/AI flows. New opt-in LINE_FRIEND_DEMO_SEED_ENABLED=1
  only has effect with LINE_FRIEND_DEMO_ENABLED=1. Keep both off on live tunnel.
- Existing pending users can seed on a subsequent distinct follow event or
  trusted internal seed call; replay of an already processed event is ignored.
- No public access, ownership audit or web authentication yet. Shared storage
  and legacy UI remain unmodified; Step 15 must verify all read/write paths.

## Step 14 — Acceptance

- @Onlynotonly reported local tests passed after Step 14 instructions
  (full local pytest output/count was not supplied).
- CI run 46063100830 passed on commit 4315736.

## Step 15 — Ownership audit and targeted fixes (verification pending)

- Storage: course updates match owner plus resource ID; status writes require
  user_id, and new availability IDs cannot collide with another owner's slot.
- Board/calendar: owner-scoped slot/task lookups and write guards; calendar
  imports cannot overwrite another owner's external event by ID.
- Scheduler: separate owners' time budgets; reminder joins use owner and ID.
  Legacy ownerless scheduler rows resolve only when the task owner is unique.
  Plan bridge rejects explicit foreign owner rather than rewriting it.
- Worker: reminder reservation rejects ambiguous/foreign IDs, status changes
  and plan lookups match owner, gated accounts cannot send even if preference
  flags are set. This does not implement transactional consent revocation.
- LINE: explicit group/room and standby events cannot enter private handlers.
  Legacy signed payloads without source.type still supported for regression
  compatibility. Existing pending/seeded accounts remain blocked.
- Web: legacy read_all filters by the fixed server-side MVP ID. A configured
  CLASSPULSE_PUBLIC_WEB=1 fails closed before data reads; default mode remains
  local-only and unauthenticated. Never publish default mode. No public URL
  query ID accepted as identity.
- Reviewed notes candidate confirmation, source ownership, attachments naming,
  exports, AI input filtering and metrics. They still rely on trusted caller
  identity; no full authenticated session boundary has been implemented.
- Added 10 adversarial ownership tests plus a signed group-message regression.
  Shared JSON writes remain non-transactional across files. Raw storage APIs,
  direct file access, identity/session switching and deployment need further
  review at Step 16. This is targeted hardening, not a security certification.

### Step 15 — Regression follow-up
- @Onlynotonly reported all 40 targeted tests passed locally.
- Full CI run 46063573670 on a6aaabc failed: 143 passed, 1 failed. The check-in scheduler built owner-qualified maps but still looked up bare IDs, returning zero valid due check-ins. Fixed both task and slot lookups; unambiguous legacy ownerless plan compatibility retained. Added two positive regression cases covering valid start and check-in reminders (explicit and legacy owner).
- Full CI must pass before public identity integration is accepted. No deployment or feature flag changes.

## Step 15 — Acceptance

- @Onlynotonly reported full local `146 passed` after the check-in correction.
- GitHub Actions run 46063747162 passed at 60ce68b. Offline acceptance complete.

## Step 16 — LINE Login (private staging implementation; verification pending)

- Use the LINE Login web authorization-code flow, not LIFF SDK. OAuth
  state and browser cookie are bound to a one-time, ten-minute server-side
  login attempt; nonce and S256 PKCE are checked. Flask exchanges code for
  token and calls LINE's ID token verification endpoint (issuer, channel,
  expiry, nonce and real LINE subject checked). Do not trust client-decoded
  tokens or profile IDs. Only unique existing seeded independent users can
  sign in; legacy demo_user_001 and unknown or pending users are rejected.
- A random opaque session cookie (Secure, HttpOnly, SameSite=Lax, host-only)
  is returned, never included in redirect URL. Only its hash is stored.
  Session expires within one hour or token expiry, whichever comes first.
  Reruns resolve the owner from cookie and existing user record; logout
  revokes the session server-side. New verified owner clears UI session state.
- Staging UI uses personal seeded data with mock AI behavior and locked
  reminder settings; it cannot reset shared fixtures or enable LINE pushes.
  The LINE user status remains seeded_pending_auth until later rollout.
- Required private HTTPS reverse proxy: same origin for Streamlit and Flask;
  /auth/line/* to Flask, / and Streamlit websocket/static routes to Streamlit.
  Keep both backend ports private, preserve Host, use HTTPS, keep CSRF/CORS
  enabled, redact callback query strings/cookies from access logs, rate-limit
  auth routes, and prevent session/store access from web static paths.
  Both processes need the same persistent DATA_DIR and server environment.
- LINE Developers: create a LINE Login channel under the SAME provider as
  the existing Messaging API channel (otherwise user IDs differ).
  Register https://YOUR-STAGING-HOST/auth/line/callback as callback URL.
  Configure only on the server (not committed):
  CLASSPULSE_LINE_WEB_STAGING=1, CLASSPULSE_WEB_ORIGIN=https://YOUR-STAGING-HOST,
  LINE_LOGIN_CHANNEL_ID, LINE_LOGIN_CHANNEL_SECRET.
  Keep flags off until private staging setup is reviewed. Public mode still
  fails closed even if staging is enabled. Do not expose legacy default UI.
- Server runtime web_auth.json contains hashed session/browser/state IDs,
  short-lived nonce and PKCE verifier; restrict filesystem access. No
  LINE access token or ID token is persisted. No new dependencies.
- Official reference:
  https://developers.line.biz/en/docs/line-login/integrate-line-login/
  https://developers.line.biz/en/docs/line-login/verify-id-token/
  https://developers.line.biz/en/docs/messaging-api/getting-user-ids/
- LIFF in-app browser flow, real LINE callback, HTTPS reverse proxy,
  multi-device session behavior, rate limits and live end-to-end remain
  unverified. LINE web auth inside LIFF browser is not guaranteed by LINE;
  use an external browser for this first staging route.

## Step 17 — private staging

- Step 16 offline: user reports 161 passed; CI #250 succeeded.
- User reports local independent worktree, reverse-proxy health/404 checks, HTTPS and real LINE Login, own UI, drag/drop, refresh and no earlier CORS errors (6/6). Protected Quick Tunnel repeatedly asked for email even on Flask /health. A fresh Quick Tunnel with Caddy Basic Auth resolved reported symptoms; localhost/external 401/200 passed. No live credentials or tunnel URLs recorded. Real logout, second identity and signed follow/seed E2E still outstanding.
- Step 17.7: add private Railway deployment files and startup validation, persistent /data mount, one service/replica, Gunicorn/Streamlit/Caddy, tester allowlist and idempotent synthetic seed. Disable live webhook, reminder worker and AI. Explicit tester allowlist checked at each session resolution. No cloud account created, payment authorized, live deployment, image build or persistent-volume verification yet. See deploy/README.md.
