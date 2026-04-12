# Apex Domain Redirect — tradingwithai.ai → www

**Priority**: Low (polish, not blocking launch)
**Created**: 2026-04-12

## Problem

`tradingwithai.ai` (apex/root) does not resolve — only `www.tradingwithai.ai` works.

Railway hosting requires a CNAME target for custom domains, but standard DNS doesn't allow CNAME at apex. Wix (registrar + DNS host) removed URL Forwarding from the current plan.

## Impact

- Users typing `tradingwithai.ai` see "site can't be reached"
- SEO: if anyone links without www, link fails
- Launch-survivable: all social bios and shared links use www version

## Solution: Cloudflare In Front

Put Cloudflare as DNS provider. Cloudflare supports "CNAME flattening" at apex.

Bonus perks: free CDN, DDoS protection, HTTPS.

## Steps

1. Sign up at https://dash.cloudflare.com/sign-up (free tier is fine)
2. Add site `tradingwithai.ai`, pick Free plan
3. Verify auto-imported DNS records:
   - CNAME `www` → `vjvu50e.up.railway.app`
   - TXT `_railway-verify...`
4. Add new record:
   - Type: CNAME
   - Name: `@`
   - Target: `qfpr0iyr.up.railway.app` (from Railway apex domain dialog)
   - Proxy: ON (orange cloud — enables CNAME flattening)
5. Copy the 2 nameservers Cloudflare provides (e.g. `adam.ns.cloudflare.com`)
6. Wix → Domains → `tradingwithai.ai` → Name Servers section → replace `ns1.wixdns.net`/`ns2.wixdns.net` with the 2 Cloudflare nameservers
7. Wait 15-60 min for propagation
8. Verify: `dig tradingwithai.ai` and `dig www.tradingwithai.ai` both return Railway's IP; opening both in browser loads site

## Acceptance

- [ ] `https://tradingwithai.ai` loads the site
- [ ] `https://www.tradingwithai.ai` still loads the site
- [ ] Short links work on both hosts: `tradingwithai.ai/tw` → UTM redirect
- [ ] SSL valid on both
- [ ] Pick canonical version (www recommended since bios already use it) and add 301 redirect from apex → www at Railway or via Cloudflare Page Rules

## Notes

- Don't do this mid-launch — DNS changes can cause brief downtime (usually seconds, but up to 15 min if things misconfigure)
- Best done during low-traffic window (weekend or evening)
- Keep Wix TXT records intact during migration (email verification, domain ownership)
