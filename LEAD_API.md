# Lead Intake API

A public POST endpoint for registering a new lead into the PIE Real Estate CRM from
outside systems — website forms, a WhatsApp bot, property portals, etc.

On every successful call the lead is automatically:
1. **Scored** Hot / Warm / Cold based on requirement completeness.
2. **Assigned** to whichever active agent currently has the fewest leads (equal
   distribution across the team).
3. **Notified** — the assigned agent gets an in-CRM notification (visible on the
   Notifications page and as a sidebar badge) and a browser push notification if
   they've enabled push.

---

## Endpoint

```
POST /api/leads/create/
```

Example full URL: `https://your-domain.com/api/leads/create/`

## Authentication

Every request must include the shared API key in a header:

```
X-Api-Key: <your key>
```

The key is set via the `LEAD_API_KEY` environment variable (see `crm/settings.py`).
There is no per-caller identity — anyone with the key can create leads, so treat it
like a password (don't put it in client-side JS, don't commit it to a public repo).

| Response | Status | Meaning |
|---|---|---|
| `{"error": "Invalid or missing API key."}` | `401` | Header missing or doesn't match |

## Request

- **Method**: `POST`
- **Content-Type**: `application/json` (recommended) or `application/x-www-form-urlencoded`
- **Body**: a JSON object (or form fields) — see field reference below

Send `full_name` and `phone` with every lead. **The API never rejects a lead with a
valid API key**: anything missing or malformed is fixed up, the lead is saved (`201`),
and the response's `warning` explains what was changed. See *Never losing a lead* below.

### Field reference

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `full_name` | string | **yes** | — | |
| `phone` | string | **yes** | — | Any format; stored as-is |
| `email` | string | no | `""` | |
| `alternate_phone` | string | no | `""` | |
| `source` | string | no | `website` | One of: `website`, `whatsapp`, `referral`, `property_listing`, `walk_in`, `phone_call`, `social_media`, `chatbot`, `other`. Anything else is saved as `chatbot`. |
| `lead_type` | string | no | `buyer` | One of: `buyer`, `seller`, `investor`, `tenant`. Anything else is saved as `buyer`. |
| `interested_in` | array of strings (or a single string) | no | `[]` | Any of: `apartment`, `house`, `plot`, `commercial`. Unknown values are silently dropped. |
| `area_preferences` | string | no | `""` | Free text, e.g. `"Block A, Block C"` |
| `budget_min` | number | no | `null` | |
| `budget_max` | number | no | `null` | |
| `bedrooms_min` | integer | no | `null` | |
| `bedrooms_max` | integer | no | `null` | |
| `bathrooms_min` | integer | no | `null` | |
| `bathrooms_max` | integer | no | `null` | |
| `area_sqft_min` | integer | no | `null` | |
| `area_sqft_max` | integer | no | `null` | |
| `other_requirements` | string | no | `""` | Free text |
| `notes` | string | no | `""` | Free text |
| `agent_phone` | string | no | — | Send a lead that's **already assigned** to a specific agent — see below. Omit for a fresh, unassigned lead. |

An unrecognised `source` is saved as `chatbot`, and an unrecognised `lead_type` as
`buyer`. The lead is still created, and the response includes a `warning`.

### Assignment: auto vs. explicit

Most leads have no agent yet, so by default the lead is auto-assigned — round-robin
to whichever active agent currently has the fewest leads, keeping the workload equal
across the team.

If the lead is **already assigned** on your side (e.g. it came from an agent's own
listing, or a referral routed to a specific agent), pass that person's phone number
in `agent_phone`. It matches any active CRM user (agent, manager or admin) on the
last 10 digits, so `0312 2211828`, `+92 312 2211828`, `0092 312 2211828` and
`3122211828` all work. Auto-assignment is skipped and the lead goes straight to them.

**A non-matching `agent_phone` never rejects the lead.** If no active CRM user has
that number, the lead is still created (`201`), auto-assigned as usual, and the
response includes a `warning` saying so.

### Error responses

| Response | Status |
|---|---|
| `{"error": "Invalid or missing API key."}` | `401` (the only error the API returns) |

### Never losing a lead

| Problem in the request | What happens |
|---|---|
| Unknown `source` (e.g. `"chat bot"`) | Saved with source `chatbot` |
| Unknown `lead_type` | Saved as `buyer` |
| `full_name` missing | Saved as `Unknown` |
| `phone` missing | Saved with an empty phone; check the notes |
| Body isn't valid JSON | Saved as an `Unknown` lead with the raw body in the notes |
| JSON sent without `Content-Type: application/json` | Read as JSON anyway |
| Budget too large, `NaN` or not a number | Treated as not given |
| A field the database rejects | Saved with name, phone, source and type only; the full original payload goes in the notes |
| Notification fails after saving | Lead is kept, and the response is still `201` |

Each case adds a sentence to the response's `warning` and to the lead's activity log.

## Success response

`201 Created`

```json
{
  "id": 42,
  "full_name": "Ali Raza",
  "phone": "03001234567",
  "status": "received",
  "lead_score": "warm",
  "assigned_agent": {
    "name": "Fahad Nazeer",
    "phone": "+923001234567",
    "assignment": "auto"
  }
}
```

| Field | Notes |
|---|---|
| `id` | The new lead's primary key — use this to build a CRM deep link (`/crm/leads/{id}/`) if needed |
| `status` | Always `"new"` for a freshly created lead |
| `lead_score` | `"hot"`, `"warm"`, or `"cold"` — auto-calculated, see below |
| `assigned_agent` | `null` if no active agent exists to assign to; otherwise the assigned agent's name, phone, and how they were assigned |
| `assigned_agent.assignment` | `"auto"` (round-robin) or `"explicit"` (you supplied `agent_phone` and it matched) |
| `warning` | Only present when something in the request was fixed up (unknown source, unmatched `agent_phone`, missing name, etc.). The lead is saved either way. |

## Behavior details

**Auto-assignment.** When `agent_phone` isn't supplied, the lead goes to whichever
active agent (`role=agent`, `is_active=True`) currently has the fewest leads
assigned — this keeps the workload equal across the team over time. If no active
agent exists, `assigned_to` stays empty and `assigned_agent` in the response is `null`.

**Explicit assignment.** When `agent_phone` is supplied and matches an active CRM
user (agent, manager or admin), the lead is assigned directly to them and
auto-assignment is skipped. If it matches no one, the lead falls back to
auto-assignment and the response carries a `warning`.

**Lead scoring.** A starter rule based on what's known about the lead:

- +1 for each of: budget set, `interested_in` set, `area_preferences` set, bedrooms/bathrooms set
- Score ≥ 2 → **Warm**, score ≥ 5 → **Hot**, otherwise **Cold**
- (Score also factors in pipeline status for leads updated later in the CRM — a
  freshly-created lead only reflects the requirement-completeness signals above.)

This is a starting point and easy to retune (`Lead.calculate_lead_score()` in
`accounts/models.py`) once you've seen it run against real data.

**Notification.** If an agent was assigned, they receive:
- An in-CRM notification titled "New Lead Assigned" linking straight to the lead
- A browser push notification, if they have push enabled

## Known limitations

- **No deduplication** — calling this twice with the same phone number creates two
  separate leads. If you need duplicate-prevention, let me know and I'll add a
  phone-based check (the CRM's internal `lead_check_phone` view already has similar
  logic to build on).
- **No rate limiting** — the API key is the only gate. Don't expose it publicly.

## Example requests

**curl**
```bash
curl -X POST https://your-domain.com/api/leads/create/ \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: YOUR_LEAD_API_KEY" \
  -d '{
    "full_name": "Ali Raza",
    "phone": "03001234567",
    "email": "ali@example.com",
    "source": "whatsapp",
    "lead_type": "buyer",
    "interested_in": ["house", "plot"],
    "area_preferences": "Block A, Block C",
    "budget_min": 5000000,
    "budget_max": 15000000,
    "bedrooms_min": 3,
    "notes": "Wants a corner plot, prefers Block C."
  }'
```

**curl — lead already assigned to a specific agent**
```bash
curl -X POST https://your-domain.com/api/leads/create/ \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: YOUR_LEAD_API_KEY" \
  -d '{
    "full_name": "Sana Malik",
    "phone": "03331234567",
    "source": "referral",
    "agent_phone": "0312 2211828"
  }'
```

**JavaScript (fetch)**
```js
const res = await fetch('https://your-domain.com/api/leads/create/', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-Api-Key': 'YOUR_LEAD_API_KEY',
  },
  body: JSON.stringify({
    full_name: 'Ali Raza',
    phone: '03001234567',
    source: 'website',
  }),
});
const lead = await res.json();
```

**Python (requests)**
```python
import requests

resp = requests.post(
    'https://your-domain.com/api/leads/create/',
    headers={'X-Api-Key': 'YOUR_LEAD_API_KEY'},
    json={
        'full_name': 'Ali Raza',
        'phone': '03001234567',
        'source': 'property_listing',
    },
)
print(resp.status_code, resp.json())
```
