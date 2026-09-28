# kbw-luma

A tool that registers you for Korea Blockchain Week 2026 side events on Luma.

It gets events from the Luma calendars `koreablockchainweek` ("Korea Blockchain Week 2026 Side
Events Calendar") and `kbw2026`. For each event it fills in the registration form from your
profile and submits it. If you register for many events at once, you are likely to be
accepted for more of the approval-only ones.

## Setup

```bash
cd kbw-luma
pip install -r requirements.txt
cp profile.example.yaml profile.yaml   # then edit it
```

**Luma login:** log in at https://luma.com. Open DevTools → Application → Cookies and copy
the value of `luma.auth-session-key`. Then run:

```bash
export LUMA_SESSION='usr-...'           # the cookie value
python kbw_luma.py whoami               # checks the cookie works
```

**Optional (recommended):** many events ask custom questions, for example "what are you
building?", "monthly trading volume" or "why do you want to attend?". Set an Anthropic API
key and Claude answers these from your profile. It answers in the question's language and
only uses facts from your profile. Without a key, these events are put on a
"register by hand" list.

```bash
export ANTHROPIC_API_KEY='sk-ant-...'
```

## Usage

```bash
# Browse events (Seoul time)
python kbw_luma.py list
python kbw_luma.py list --date 2026-09-30 --match 'solana|ethereum'

# Dry run: shows the answers it would send, submits nothing
python kbw_luma.py apply --date 2026-09-30

# Submit for real
python kbw_luma.py apply --date 2026-09-30 --go
python kbw_luma.py apply --go --exclude 'pickleball|hyrox' --limit 20
```

Filters: `--date YYYY-MM-DD`, `--match REGEX`, `--exclude REGEX` (you can repeat each),
`--free-only`, `--limit N`, `--calendar SLUG` to add or replace calendars. `--delay` sets the
number of seconds between submissions (default 4).

## Behavior

- It skips events you're already registered for, so you can re-run it safely.
- It skips events that are paid or token-gated, or that require a verified ETH or Solana
  wallet. It also skips events with required questions it can't answer. These are printed at
  the end with their links so you can register by hand.
- For sold-out events that have a waitlist, it joins the waitlist.
- Answers are chosen in this order: your profile's `answers` regex map, then built-in
  matching for common fields (phone, email, company, X handle, etc.), then Claude.
- Each run writes a log to `out/results-*.json`.

**Always do a dry run first** and check the answers before you use `--go`. Most events
require host approval, so hosts will read what you submit.

## Caveats

This uses Luma's internal web API (the same calls luma.com makes), not an official public
API, so it may stop working if Luma changes that API. If submissions fail with 4xx errors,
open one event in the browser and compare the request to `/event/register`. Automated
registration may also be against Luma's terms. Use it at a reasonable pace for your own
account only.
