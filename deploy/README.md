# Protected Docker deployment

This repository contains reusable deployment examples, not configuration for a particular installation. The application provides named logins into one shared workspace, not separate tenants.

Copy `.env.example` to the ignored `.env` file on your own host. Set `AGENTSIM_PUBLIC_URL` to your actual HTTPS origin and choose `AGENTSIM_HTTP_PORT` for the host loopback binding. Compose fails if the public origin is unset. Never commit real hostnames, addresses, usernames, passwords, SSH details, certificate paths or operational data.

The image contains Python 3.12, pinned Python dependencies, Pango, Chromium and the official Codex CLI. `docker compose up -d --build` publishes the application only on the configured loopback port. A reverse proxy handles public HTTPS. `deploy/nginx.conf.example` uses a reserved example hostname: copy it to an untracked configuration and adapt it for your own domain, certificate and upstream. Configure the example's login rate-limit zone in your proxy's HTTP context. Use Certbot or your certificate manager to issue and renew certificates; never store their private keys in Git. Keep proxy access logs disabled for OAuth callback URLs.

`data/` (container UID 10001) is mounted at `/app/.local` and holds the dynamically created database, artifacts, plugins and independent provider sessions. Keep and back up this folder across releases. It is ignored and never baked into the image. No desktop or other application's credentials are copied.

Create the server-only `secrets/site-login.json` with a `users` array. Each account has `username`, a random hex `salt` (at least 16 random bytes), and `password_hash` computed by `hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()`. Mount this read-only, with permissions allowing container UID/group 10001 to read it. Keep any initial password handoff in a separate protected file outside Git. Legacy single-account configuration remains supported.

To change accounts or passwords, update that protected file and recreate the container (`docker compose up -d --force-recreate`) to remount it and invalidate sessions. Check for active executions first. Each login receives an independent random 12-hour session. Sign out invalidates only that session. Public startup fails without valid login configuration; API, event streams and generated files all require authentication.

Connect your own OpenAI account inside the application. For remote independent ChatGPT OAuth, the protected callback-completion form accepts the exact loopback return URL after the browser sign-in. Native image login uses the official CLI device-code flow on public deployments. [Official authentication guidance](https://learn.chatgpt.com/docs/auth).

Connection → Disconnect OpenAI clears only this application's OAuth, API/image keys and native image auth file. It terminates pending login and refuses during active executions. Saved conversations and artifacts remain. This removes local credentials; it does not promise global revocation on the provider's systems.

Before publishing an installation, verify proxy syntax, HTTPS, redirects, login failure/success, unauthenticated data denial, session invalidation, persistent volumes and container health. Preserve unrelated services. Rollback should affect only this application's container and proxy configuration; keep its data and protected settings.
