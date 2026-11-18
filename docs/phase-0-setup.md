# Phase 0 setup: manual steps

These steps need your accounts, so they can't be automated. Do them in order. Each step says how to check that it worked.

## 1. Lock down accounts

1. **GitHub:** turn on 2FA (Settings → Password and authentication), with a passkey or hardware key if you can.
2. **GitHub verified domain:** this is in your **account** settings, not the repository's. Profile picture → Settings → Pages (under "Code, planning, and automation") → Add a domain → `vasnik.net`. GitHub gives you a TXT record named `_github-pages-challenge-<username>` to add at GoDaddy (step 3), then you click Verify. This stops anyone else's GitHub Pages site from claiming a `*.vasnik.net` subdomain.
3. **Cloudflare:** create a free account at dash.cloudflare.com and turn on 2FA (My Profile → Authentication).
4. **GoDaddy:** check that 2FA is on. Whoever controls DNS controls what code the site's users run.

## 2. Create the Cloudflare Pages project

1. Workers & Pages → Create → Pages → **Direct Upload** (not "Connect to Git"; deploys come from GitHub Actions).
2. Project name: `within-reach`. Production branch: `main`.
3. Upload any placeholder file to finish creating the project. CI replaces it.
4. **Turn off script-injecting features** for the project and the account:
   - Web Analytics: project → Metrics → make sure Web Analytics is **off**
   - If they're listed anywhere: Rocket Loader, Email Obfuscation, Zaraz → **off**

## 3. DNS at GoDaddy (vasnik.net)

Add these records. Don't change the existing GitHub Pages A/AAAA records or `www`.

| Type | Name | Value | Why |
|---|---|---|---|
| CAA | `@` | `0 issue "pki.goog"` | Lets Cloudflare issue certificates (keep the existing `letsencrypt.org` CAA) |
| TXT | `_github-pages-challenge-<username>` (GoDaddy adds `.vasnik.net` itself) | The code GitHub shows in step 1.2 | GitHub domain verification |
| CNAME | `withinreach` | `within-reach.pages.dev` | Points the tool's subdomain at Cloudflare Pages. Add this in step 5, not before |

Check: `dig +short CAA vasnik.net` shows both `letsencrypt.org` and `pki.goog`.

## 4. Deploy credentials

1. Cloudflare → My Profile → API Tokens → Create Token → **Custom token**:
   - Name: `within-reach-github-deploy`
   - Permissions: **Account → Cloudflare Pages → Edit** (nothing else)
   - Account resources: your account only
   - Optional: a TTL of a year, with a calendar reminder to rotate it
2. Copy your Account ID (Workers & Pages overview, right-hand side).
3. GitHub repo → Settings → Secrets and variables → Actions:
   - Secrets: `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`
   - Variables: `DEPLOY_ENABLED` = `true`
4. Re-run the **Deploy** workflow (Actions → Deploy → Run workflow). Check: `https://preview.within-reach.pages.dev` shows the placeholder.

## 5. Custom domain

1. Cloudflare Pages → `within-reach` → Custom domains → Set up → `withinreach.vasnik.net`.
2. Add the CNAME from step 3 at GoDaddy.
3. Wait for the status to show **Active** (usually minutes, sometimes up to a day).
4. Deploy to production by tagging: `git tag v0.0.1 && git push origin v0.0.1`.
5. Set the repository variable `LIVE_CHECK_ENABLED` = `true`. The **Live site check** workflow then runs after every deploy and daily.

Check: `curl -sI https://withinreach.vasnik.net` shows `content-security-policy`, `strict-transport-security` and `referrer-policy: no-referrer`, and no `set-cookie`.

## 6. Branch protection (once the repo is public, or on a paid plan)

Settings → Branches → add a rule for `main`: require pull requests and require the **CI** checks to pass. Free private repositories don't enforce branch protection, so this waits until the repo goes public at the Phase 0 gate.

## 7. Paperwork (alongside the above)

- [ ] Start the DPIA, using spec section 10 (data flows) and section 11
- [ ] Ask a pilot service to open `https://preview.within-reach.pages.dev` on a work device (R1)
