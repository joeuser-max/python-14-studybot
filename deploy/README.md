# ClassPulse private cloud staging (Step 17.7)

This is an isolated **private test deployment**, not production.
Do not connect the existing LINE Messaging API webhook to this service.
Do not copy local .env, real data, attachments, or the old demo folder.
Deploy only the reviewed feature/line-friend-demo commit, not main.

## Railway

1. Create a project and one service from the GitHub repository. Select the feature/line-friend-demo branch and repository root. Disable automatic deployments if available; use reviewed commits only.
2. Set RAILWAY_DOCKERFILE_PATH=deploy/Dockerfile. Leave Start Command unset so the image CMD runs.
3. Attach a persistent volume at /data. Use one replica only; do not enable serverless sleeping for sustained staging tests.
4. Generate the service's Railway HTTPS domain. Set the platform health check path to /readyz and target port to 8080 if asked.
5. Configure variables in Railway's private Variables UI (not GitHub, screenshots, chat or build args):

| Variable | Value |
| --- | --- |
| RAILWAY_DOCKERFILE_PATH | deploy/Dockerfile |
| PORT | 8080 |
| CLASSPULSE_WEB_ORIGIN | https://YOUR-SERVICE.up.railway.app |
| LINE_LOGIN_CHANNEL_ID | LINE Login channel ID |
| LINE_LOGIN_CHANNEL_SECRET | LINE Login channel secret |
| CLASSPULSE_STAGING_TEST_USERS | One tester LINE user ID (comma-separated, max five) |
| CLASSPULSE_STAGING_PASSWORD_HASH | Fresh bcrypt output from local caddy hash-password --algorithm bcrypt |

The platform provides RAILWAY_PUBLIC_DOMAIN and RAILWAY_VOLUME_MOUNT_PATH.
Do not set these manually. The launcher refuses to start without a real /data mount, matching HTTPS origin, valid tester list, and bcrypt hash. Use a fresh strong password; do not share the hash or password. The password is not the LINE secret.

6. Add the exact cloud origin + /auth/line/callback to the LINE Login channel Callback URL list, preserving the existing Mac staging callback where supported. Keep the channel Developing; same Provider as Messaging API.
7. Deploy. Check Railway's healthcheck and logs without revealing credentials.

## Verification

- /readyz returns a static 200 once backends have started; no data is exposed.
- /health, /_stcore/health and UI without Basic Auth return 401; with tester credentials return 200 (UI also requires LINE Login).
- /webhook always returns 404.
- Correct LINE account logs in; unlisted account cannot log in; removal from tester list invalidates its session at next resolution.
- Test refresh, drag/drop, real logout and a new browser without LINE session. Restart/redeploy; verify edits survive. Do not assume local sessions/data migrate.
- The launcher starts Flask through Gunicorn, Streamlit, then Caddy. Only Caddy listens externally, with Basic Auth on UI/auth paths. No access log by default; never enable verbose OAuth logging. CORS/XSRF stay enabled.
- The startup seed is idempotent and only creates synthetic data for explicitly listed testers. Existing seeded edits should survive redeployment. The application does not yet automatically register new LINE friends in this cloud deployment. Both friend flags, push credentials, live AI credentials and reminder worker remain disabled.

Railway terminates HTTPS; Caddy receives the internal HTTP hop. This is not intended for a direct unencrypted Internet listener. Static readiness is a startup check, not a continuous service-level health monitor. A container process exit terminates the launcher so the platform can restart it. Actual image build, volume ownership, external OAuth callback, WebSocket and restart persistence need live verification. Basic Auth is only a private testing guard, not the eventual public authentication architecture. Do not merge or expose the public product until full signed follow/seed and two-account E2E checks pass.
