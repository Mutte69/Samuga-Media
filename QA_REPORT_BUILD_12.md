# Build 12 QA Report

## Automated checks completed

- Compiled all 15 Python files.
- Syntax-checked all 10 website and Cloudflare Function JavaScript files.
- Validated all 10 HTML pages for duplicate IDs and missing local assets.
- Checked CSS brace balance and removed references to undefined legacy theme variables.
- Scanned 51 Flask routes for duplicate method/path registrations.
- Verified the browser tracker uses same-origin `/api/track`, `credentials: omit`, and a unique event ID.
- Verified homepage, article, story and policy renderers include the Build 12 tracker.
- Mock-tested DeepSeek JSON output parsing, validation and cache reuse.
- Mock-tested Cloudflare GraphQL daily aggregation and totals.
- Confirmed retired Gemini 2.0/1.5 model IDs are absent from the production chain.
- Confirmed the active English card, English article and Dhivehi caption paths call the structured fact-pack layer.

## Production checks still required

External credentials were unavailable in the build environment. After deployment, verify:

1. Visit the homepage, then open an article. Samuga tracked pageviews should increase by two after refresh.
2. Reopen the same article. It should count as a new pageview, not be suppressed for an hour.
3. Set the Cloudflare Zone ID/token and confirm the separate Cloudflare panel loads.
4. Submit one disposable English story and inspect the DeepSeek health block in `/api/health`.
5. Submit one disposable Dhivehi story and verify the final output is clean Thaana with no invented facts.
6. Temporarily remove `DEEPSEEK_API_KEY` in a staging environment and confirm the legacy fallback still completes.

## Important metric rule

Do not compare Cloudflare total edge requests directly with Samuga browser pageviews. They are different measurements and intentionally remain separate in the dashboard.
