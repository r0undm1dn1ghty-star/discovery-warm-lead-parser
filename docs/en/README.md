# Discovery Warm Lead Parser — English Summary

**Find buyers for your services in public sources. Score them by readiness to pay. Contact the right ones first.**

## What it is

An open-source Python tool (one file, stdlib-only, no API keys, no logins) that:

1. **Collects** fresh "looking for a contractor" posts from public feeds (FL.ru chatbot orders, Telegram job boards).
2. **Scores** each post 0–100 by readiness-to-pay: exact niche match (+40), budget mentioned (+25), urgency (+15), scope ready (+10), budget in the 1K–600K ₽ corridor (+10), freshness bonus.
3. **Prioritizes**: score 60+ = contact today; 40–59 = soft approach; below = skip.
4. **Counts the money**: every report includes run economics — your time × your rate ÷ warm leads = cost per warm lead, compared to your average deal size.

## Why it's different

| Others | This tool |
|---|---|
| Prompt-only "paste into Claude" (unreproducible) | Script + editable config: same input → same output, every score explained |
| Telethon login-scraping (account risk) | Public pages only: zero logins, zero bans by design |
| SaaS subscriptions, vendor lock | One Python file, MIT license, runs anywhere |
| No economics | Cost per warm lead in every report |

## Quick start

```bash
python warm_lead_parser.py
```

Report lands as `warm-lead-report-<date>.md` with links, scores and reasoning. No dependencies, no keys.

## Safety rails (non-negotiable)

- Reads public pages only; never logs in; never scrapes private groups.
- No mass contact collection (anti-spam, personal-data law compliant).
- Never sends messages — a human writes every reply.
- Honest empty reports: zero warm leads is a valid result, never padded.

See `SAFETY_RAILS.md` (Russian, authoritative) for the full policy.

## License

MIT. Russian is the authoritative operating language; this file is a summary, not a substitute for the Russian docs.
