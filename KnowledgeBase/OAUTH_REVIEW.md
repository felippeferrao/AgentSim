# OAuth configuration review — 2026-10-20

Compared `auth.py` against the current official [open-source sign-in guide](https://developers.openai.com/siwc/token-sharing-open-source/sign-in).

The initial request uses dynamic_agent_client, actual app name WABIX AgentSim, a stable app-specific host id, fresh state and nonce, S256 PKCE, exact 127.0.0.1 loopback callback, resource=https://api.openai.com/v1 and the documented identity/plan scopes. Exchange uses the issued client id rather than dynamic_agent_client. Signature/JWKS, issuer, audience, expiry, nonce, subject continuity and granted plan scope are checked. The inference adapter uses the public Responses endpoint with stream=true and store=false.

A recoverable edge case was corrected: after a token exchange returns invalid_grant, the issued client id is retained separately as an incomplete registration for a fresh authorization attempt. This does not mark the account connected. Signing out removes that incomplete registration too.

No request-configuration defect was identified that establishes the cause of the previously observed 403 browser challenge. The 403 was before human consent. Do not claim this change fixes that challenge or that OAuth has succeeded.

The UI now opens Connection setup automatically when Home loads without any provider-verified connection. It offers the official sign-in flow plus a reviewable sign-in link, preserves the app/callback listener, explains the browser-check boundary and provides Check connection again. A saved token or API key alone is insufficient: backend connection checks validate account access against the provider model endpoint. Real runs check every selected agent's connection and model before starting. No failed real request switches to Demo.

Human verification still required:
1. Open AgentSim in the regular browser; keep the Python server running.
2. Continue with ChatGPT; complete any provider browser check and the actual consent screen.
3. After the loopback callback, Check connection again.
4. In each agent Profile choose its connection and load/select an eligible model.
5. Run one helper and then a team. Verify actual outputs, tool events and provider-reported usage.

No consent, live code exchange, refresh or external inference has been completed in the automated environment. Contract tests and local fixture SSE responses are explicitly labeled as tests.
