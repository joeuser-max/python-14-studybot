# Step 23 — local service manager

Run in the existing classpulse-staging worktree; no new environment or data initialization.

## Migrate once from manual terminals

1. Keep original Flask 5000, original ngrok (if still running), and the current external Cloudflare quick tunnel pointing to 127.0.0.1:18080 running.
2. Stop only the previous manually launched tester Flask 5001, Streamlit 8502, Caddy 18080, official bridge 5002, and automatic worker. Do not kill processes by port or stop unrelated terminals.
3. Confirm data/friend-e2e.env and data/official-bridge.env are mode 600, select the same existing isolated data directory and HTTPS origin, and have different OA credentials but the same LINE Login channel. The launcher reads these files without rewriting them.
4. Run:

    bash classpulse.sh start

Keep this terminal open. The launcher verifies the original 5000 webhook with an empty signed event, validates Caddy, starts five owned staging services and verifies local HTTP readiness, the public run-specific readiness marker and both public signed empty webhook routes. If any managed child exits, the supervisor stops its other children. Existing legacy Flask and external tunnel are never terminated.

In a second terminal, from the same worktree:

    bash classpulse.sh status
    bash classpulse.sh logs
    bash classpulse.sh logs worker
    bash classpulse.sh stop

Ctrl+C or stop shuts down owned children only. No PID taken from disk is signalled. Logs and run state stay in ignored data/local-launcher; do not upload logs or environment files. Status is local HTTP/process readiness, not proof of phone delivery or OAuth success.

## When the old tunnel no longer exists

    bash classpulse.sh start --new-tunnel

The launcher owns this new tunnel and discovers its generated origin. It supplies the same origin to all managed services in memory, without modifying dotenv files. It prints the exact tester webhook, original official webhook and LINE Login callback. Update the appropriate LINE Developers settings, verify both webhooks, and test login with the new URL. Then, in a second terminal:

    bash classpulse.sh activate

This enables the automatic worker only after operator confirmation. The launcher cannot change LINE Console settings or independently verify that the operator did. Old URLs and host-only browser sessions cannot be reused at a new origin. A managed quick tunnel stops with its supervisor; a subsequent new-tunnel launch will require new Console settings again.

## Limits

This manages local internal staging only. Existing legacy Flask 5000 is an external prerequisite, because its exact source directory, credentials, storage and launch command are not part of staging. The default mode also depends on an externally running quick tunnel. No permanent domain, cloud deployment, public rollout or always-online guarantee. Flask remains the existing local development server; Mac sleep/network loss interrupts reminders. Forced OS termination may leave orphaned processes; the launcher refuses occupied ports instead of killing them. JSON remains nontransactional across files. Per-owner opt-in is preserved; seeded fixtures are excluded by the existing worker. The launcher does not rotate keys, alter data, or merge main.

## Acceptance

Run syntax checks and full pytest first. Verify existing LINE login, official note/AI flow, tester route, worker, status and logs. Stop and restart in default reuse mode; verify the original Flask and external tunnel stay running, the original public URL stays unchanged, edits and reminder opt-in persist, and no reminders duplicate. A new-tunnel test is optional and changes LINE Console configuration; do not invalidate a working tunnel just to test it.
