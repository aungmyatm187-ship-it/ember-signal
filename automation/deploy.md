# Deploying the Ember Fusion Heartbeat automation

The automation is a **prompt-preset** automation (it needs judgment: comparing
symbols, deciding whether a failure is drift, writing a report), on a
twice-daily cron.

- Name: `Ember Fusion Heartbeat`
- Schedule: `0 7,19 * * *` UTC (07:00 and 19:00 UTC)
- Trigger: cron
- Repos cloned: ember-lite + ember-signal

## Create it

Replace `<PROMPT>` with the body of `ember-fusion-heartbeat.md` (everything after
the `---`).

```bash
OPENHANDS_HOST="https://app.all-hands.dev"

PROMPT=$(awk 'f;/^---$/{f=1}' automation/ember-fusion-heartbeat.md)

python3 - "$PROMPT" <<'PY'
import json, os, sys, urllib.request
prompt = sys.argv[1]
body = json.dumps({
    "name": "Ember Fusion Heartbeat",
    "prompt": prompt,
    "trigger": {"type": "cron", "schedule": "0 7,19 * * *", "timezone": "UTC"},
    "repos": [
        "https://github.com/aungmyatm187-ship-it/ember-lite",
        "https://github.com/aungmyatm187-ship-it/ember-signal",
    ],
}).encode()
req = urllib.request.Request(
    "https://app.all-hands.dev/api/automation/v1/preset/prompt",
    data=body, method="POST",
    headers={"Authorization": f"Bearer {os.environ['OPENHANDS_API_KEY']}",
             "Content-Type": "application/json"})
print(urllib.request.urlopen(req).read().decode())
PY
```

## Verify

```bash
curl -s "https://app.all-hands.dev/api/automation/v1?limit=20" \
  -H "Authorization: Bearer ${OPENHANDS_API_KEY}" | \
  python3 -c "import sys,json;[print(a['name'],a['trigger']) for a in json.load(sys.stdin)['automations']]"
```

## Trigger a run on demand

```bash
curl -X POST "https://app.all-hands.dev/api/automation/v1/<id>/dispatch" \
  -H "Authorization: Bearer ${OPENHANDS_API_KEY}"
```

## Peer pairing

The engine operator can deploy the same automation from its own conversation
with the same name and schedule, so the two stacks are visibly paired. Send it
the body of `ember-fusion-heartbeat.md` and the `curl` in *Create it* above.
