# vOidnet

A website version of the `github.py` lookup tool: enter a GitHub handle and vOidnet
renders the public profile (name, bio, company, location, links, orgs), every public
repository, and the author emails found in that account's public commits.

No build step, no dependencies, no backend. Everything is fetched from the public
GitHub REST API in the browser, so the page also works from any static host.

## Run it

Double-click `start.bat`. It asks for administrator rights, starts `server.py` in a window
titled **vOidnet log**, waits until the port answers, then opens the browser. `stop.bat`
shuts it down again.

From a terminal:

```bash
python server.py
# then open http://127.0.0.1:4173
```

Opening `index.html` directly still renders the site, but nothing is logged and the page
cannot record searches.

## Search log

`server.py` prints one coloured line per lookup to its console:

```
♥ 14:32:07  @torvalds             live           12 repos   3 emails   dirk@hohndel.org, jefdriesen@users.sourceforge.net, torvalds@linux-foundation.org
♥ 14:33:40  @gregkh               public pages   85 repos   5 emails   gregkh@linuxfoundation.org, patches@lists.linux.dev, stable@vger.kernel.org
♥ 14:35:02  @torvalds             cached          12 repos   3 emails   dirk@hohndel.org, jefdriesen@users.sourceforge.net, torvalds@linux-foundation.org
```

Each line records the local time, the handle, how the answer was produced (`live`, `cached`
or `public pages`), the repository count and every email the page surfaced. The mode is
tinted mint, lilac or amber so a glance down the window separates fresh scans from cached
ones and from the public-page fallback. The log lives in that window only;
nothing is written to disk.

## How the emails are found

1. `email` on the public profile (rarely set).
2. `/user/emails` — only when the saved token belongs to the account being scanned.
3. The 12 most recently pushed repos, 20 commits each, read via
   `/repos/{owner}/{repo}/commits?author={login}`; both the author and committer
   addresses are collected. `noreply.github.com` and `noreply@github.com` addresses
   are hidden unless you tick the toggle.

## Rate limits

GitHub enforces 60 requests an hour for anonymous callers, and no web page can bypass
that server-side rule. vOidnet is built so it rarely has to spend them:

- Every scan is cached in `localStorage` together with its ETags. Re-opening a handle
  inside the 15-minute fresh window costs **zero** requests.
- After that, endpoints are revalidated with `If-None-Match`. GitHub does not count a
  `304 Not Modified` against the quota, so unchanged data stays free.
- If the quota is spent, or a refresh fails, the last cached scan opens with no network
  calls at all and the badge next to the handle reads `cached · <age>`.
- When the quota is spent and the handle is not cached yet, the page asks the local server
  for `/api/scan?login=…`. The server reads `github.com/{login}` and its repositories tab
  directly — those pages are not part of the API quota — and takes addresses from
  `/search/commits?q=author:{login}`, which has its own separate 10-requests-a-minute
  allowance. The badge reads `public pages`, the result is cached like any other scan, and
  the server keeps it in memory for 10 minutes so a reload does not scrape again.
- The commit sweep caches per repository, so a re-scan only revalidates what changed.

The badge shows `live`, `cached` or `public pages`, and **refresh** forces a revalidation. A personal
access token (no scopes needed, kept in `localStorage`) raises the limit to 5,000/hour and
enables the account-email check.

## Files

`index.html` is the entire site — markup, styles and script inlined — so the page itself
is a single file with nothing else alongside it.

`server.py` serves that file on port 4173, writes the console search log, and provides the
`/api/scan` public-page fallback used when the API quota is spent.

## Notes

Only public data is read; private repos appear only if your token can see them. All
GitHub text (bio, repo names/descriptions) is rendered through `textContent`, never
`innerHTML`, so profile content cannot inject markup.
