# Render recovery runbook — restore the live dashboard

## What is broken (verified 2026-10-13)

`lumafoundry.live/api/signals` returns HTTP 200 but with `"source":"local-file"`
and `"top_brands":[]`. The Express bridge in the SPA fetches an **upstream**,
`https://ember-signal-web.onrender.com/api/signals`, and that upstream returns
**HTTP 503 "Service Suspended"**. So the dashboard is empty because the Render
service is suspended — not because of a code bug.

## The service (from `A1__ember-signal-web-service.json`)

| Field | Value |
|---|---|
| name | `ember-signal-web` |
| id | `srv-dap9srff3r2c73ehf7g0` |
| repo | `https://github.com/highfive251677-wq/ember-signal` |
| branch | `fix/dedicated-health-endpoint` |
| runtime | python (build: `pip install -r requirements.txt`) |
| start | `gunicorn --bind 0.0.0.0:$PORT app:app` |
| healthCheckPath | `/api/health` |
| plan / region | free / oregon |

## The exact prompt (copy-paste into Termux/Ubuntu)

```bash
#!/usr/bin/env bash
# Render recovery: un-suspend ember-signal-web and restore the live dashboard.
# Requires RENDER_API_KEY in the environment.
set -u
API="https://api.render.com/v1"
SVC="srv-dap9srff3r2c73ehf7g0"   # ember-signal-web
: "${RENDER_API_KEY:?set RENDER_API_KEY first}"
auth=(-H "Authorization: Bearer $RENDER_API_KEY" -H "Accept: application/json")

echo "== 1. Confirm access + current suspended state =="
curl -s "${auth[@]}" "$API/services/$SVC" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('name:',d.get('name'),'| suspended:',d.get('suspended'),'| type:',d.get('type'))"

echo "== 2. Resume the service (no-op if already running) =="
curl -s -o /dev/null -w "  resume HTTP %{http_code}\n" -X POST "${auth[@]}" "$API/services/$SVC/resume"

echo "== 3. Trigger a fresh deploy from the connected branch =="
curl -s "${auth[@]}" -X POST "$API/services/$SVC/deploys" \
  -H "Content-Type: application/json" -d '{"clearCache":"do_not_clear"}' \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('  deploy id:',d.get('id'),'| status:',d.get('status'))"

echo "== 4. Wait for the upstream to come up =="
for i in $(seq 1 30); do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "https://ember-signal-web.onrender.com/api/health")
  echo "  try $i: /api/health -> $code"
  [ "$code" = "200" ] && break
  sleep 10
done

echo "== 5. Confirm the upstream serves the real contract =="
curl -s --max-time 20 "https://ember-signal-web.onrender.com/api/signals" | head -c 300; echo

echo "== 6. Confirm the live site stopped falling back to local-file =="
curl -s --max-time 20 "https://lumafoundry.live/api/signals" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('  source:',d.get('source'),'| top_brands:',len(d.get('top_brands') or []))"
```

## Success looks like

- step 1 prints `suspended: not_suspended`
- step 4 reaches `/api/health -> 200`
- step 5 returns the signals JSON (not the 503 HTML page)
- step 6 prints `source: upstream` (or anything other than `local-file`) with a
  non-empty `top_brands`

## If resume does not help

- **Redeploy instead:** push any commit to `highfive251677-wq/ember-signal`
  branch `fix/dedicated-health-endpoint`, or hit the deploy hook, or POST the
  deploy endpoint above with a specific `commitId`.
- **Free-tier reality:** Render free services suspend after inactivity and on
  account/billing issues; `resume` only works if the account is in good standing.
- **Repoint the bridge (no Render needed):** change the SPA's upstream from
  `https://ember-signal-web.onrender.com` to a service that is actually live.
  A `aungmyatm187-ship-it/ember-signal` deployment with the `ember_signal/`
  surface would serve the same contract.

## Security note

The recovery bundle at `luma-foundry-platform/docs/recovery/literal-source/A1__render-api-connector-draft.json`
contains a **plaintext Render API key and it is committed to git**. Rotate that
key in the Render dashboard, then remove it from the repo and its history.
