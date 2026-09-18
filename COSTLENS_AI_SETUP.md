# CostLens AI setup

The public portfolio remains a static GitHub Pages site. The AI investigation layer runs separately in a Cloudflare Worker so the LLM API key is never exposed in browser code.

The current prototype is intentionally small: structured manufacturing records live in the Worker, deterministic analysis is exposed as tools, and the model handles question interpretation, tool selection and grounded explanation.

## One-time backend setup

1. Create a Cloudflare Worker from `costlens-api/`.
2. Deploy `costlens-api/worker.js` with `costlens-api/wrangler.jsonc`.
3. Add `OPENAI_API_KEY` as a Worker secret.
4. Copy the Worker URL into `costlens-config.js`.
5. Commit the portfolio and backend source together.

The frontend will still work without the backend, but will use the local deterministic demo mode until `API_URL` is populated.
