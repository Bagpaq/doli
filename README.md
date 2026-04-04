# Sophia — AI Dental Receptionist

A fully-functional AI voice agent for dental clinics that handles inbound and outbound calls, books appointments, and speaks in a warm, low-tone female voice.

---

## Architecture

```
Caller  ──SIP──►  LiveKit  ──►  sophia-agent (Python)
                                     │
                          ┌──────────┼──────────────┐
                          ▼          ▼               ▼
                    OpenAI      Google           Gmail API
                  Realtime API  Calendar API   (confirmations)
                  (shimmer voice)
```

| Component | Technology |
|-----------|-----------|
| Voice engine | OpenAI Realtime API — `gpt-4o-realtime-preview`, voice `shimmer` |
| Telephony | LiveKit SIP |
| Appointments | Google Calendar API (service account) |
| Notifications | Gmail API (HTML emails) |
| Backend | Python 3.12, `livekit-agents` |
| Config | YAML per clinic |
| Deployment | Docker Compose |

---

## Quick Start

### 1. Prerequisites

- Python 3.12+
- Docker + Docker Compose
- [LiveKit Cloud](https://cloud.livekit.io) account (or self-hosted)
- OpenAI API key with Realtime API access
- Google Cloud project with **Calendar API** and **Gmail API** enabled
- Google Service Account JSON key with:
  - Editor access to the clinic's Google Calendar
  - Domain-wide delegation for Gmail (to send email as the clinic address)

### 2. Clone & configure

```bash
git clone https://github.com/bagpaq/doli.git
cd doli

cp .env.example .env
# Edit .env with your real credentials
```

### 3. Edit clinic config

Open `config/businesses/dental-clinic.yaml` and update:
- `clinic.name`, `clinic.address`, `clinic.phone`, `clinic.email`
- `hours` block to match your actual opening hours
- `faq` answers to match your clinic policies
- `agent.greeting` with your clinic name

### 4. Run with Docker

```bash
mkdir -p secrets
cp /path/to/your/service-account-key.json secrets/google-service-account.json

docker compose up --build
```

### 5. Connect a SIP trunk in LiveKit

1. Go to your [LiveKit Cloud dashboard](https://cloud.livekit.io)
2. Create a **SIP Trunk** pointed at your phone number provider (Twilio, Vonage, etc.)
3. Create an **Inbound SIP Rule** that dispatches to your `sophia-agent` worker
4. Copy the **SIP Trunk ID** into `.env` as `LIVEKIT_SIP_TRUNK_ID`

---

## Project Structure

```
doli/
├── agent/
│   ├── main.py                 # LiveKit worker entrypoint
│   ├── dental_agent.py         # DentalAgent class + tool registration
│   ├── config_loader.py        # YAML loader with env-var expansion
│   ├── flows/
│   │   ├── booking.py          # Appointment booking logic
│   │   ├── reschedule.py       # Reschedule flow
│   │   ├── cancel.py           # Cancellation flow
│   │   └── faq.py              # FAQ answer lookup
│   └── tools/
│       ├── calendar_tool.py    # Google Calendar integration
│       └── email_tool.py       # Gmail integration
├── config/
│   └── businesses/
│       └── dental-clinic.yaml  # Clinic-specific config (edit this!)
├── templates/
│   ├── confirmation_email.html # HTML booking confirmation
│   └── cancellation_email.html # HTML cancellation notice
├── outbound/
│   └── reminder_caller.py      # 24h reminder outbound calls
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## Voice Configuration

Sophia uses OpenAI Realtime API voice **`shimmer`** — a warm, low-tone, soft female voice.

| Setting | Value |
|---------|-------|
| Model | `gpt-4o-realtime-preview` |
| Voice | `shimmer` |
| Temperature | `0.6` (consistent, professional) |
| Turn detection | Server VAD, 600ms silence threshold |

---

## Conversation Flows

### Inbound — Booking
1. Sophia greets the caller
2. Identifies intent (book / reschedule / cancel / FAQ)
3. Collects: patient name → reason for visit → preferred date/time
4. Calls `check_available_slots` → offers up to 3 options
5. Confirms chosen slot verbally
6. Calls `book_appointment` → creates calendar event
7. Sends HTML confirmation email
8. Ends call warmly

### Inbound — Reschedule
1. Collects name + original appointment date
2. Looks up event on Google Calendar
3. Updates event to new slot
4. Sends updated confirmation email

### Inbound — Cancel
1. Collects name + appointment date
2. Confirms cancellation verbally
3. Deletes calendar event
4. Sends cancellation email

### Outbound — 24h Reminder
- Runs daily at 10:00 AM (configurable)
- Reads tomorrow's appointments from Google Calendar
- Places an outbound SIP call to each patient
- Sophia reminds them of date, time, and what to bring
- Patient can confirm or cancel on the spot
- Falls back to email if no phone number is found

---

## Configuration Reference (`dental-clinic.yaml`)

```yaml
clinic:
  name:     "Your Clinic Name"
  address:  "123 Main St, City, State ZIP"
  phone:    "(555) 555-0100"
  email:    "hello@yourclinic.com"
  timezone: "America/New_York"   # IANA timezone string

agent:
  voice:       shimmer    # Do not change — shimmer only
  temperature: 0.6

hours:
  Monday:  "8:00 AM – 5:00 PM"
  # ...

faq:
  insurance: "We accept Delta Dental, Cigna, Aetna..."
  parking:   "Free parking behind the building."
  emergency: "Call (555) 555-0911 after hours."
  # Add any key → answer pairs you like

google:
  calendar_id:              "${GOOGLE_CALENDAR_ID}"
  service_account_json_path: "${GOOGLE_SERVICE_ACCOUNT_JSON_PATH}"

gmail:
  sender_email: "${GMAIL_SENDER_EMAIL}"
```

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key (Realtime API access required) |
| `LIVEKIT_URL` | LiveKit WebSocket URL (`wss://...`) |
| `LIVEKIT_API_KEY` | LiveKit API key |
| `LIVEKIT_API_SECRET` | LiveKit API secret |
| `LIVEKIT_SIP_TRUNK_ID` | SIP trunk for outbound calls (optional) |
| `GOOGLE_CALENDAR_ID` | Google Calendar ID (e.g. `primary`) |
| `GOOGLE_SERVICE_ACCOUNT_JSON_PATH` | Path to service account JSON key |
| `GMAIL_SENDER_EMAIL` | Email address Sophia sends FROM |
| `CLINIC_CONFIG_PATH` | Path to clinic YAML (default: `config/businesses/dental-clinic.yaml`) |

---

## Local Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export $(cat .env | xargs)
cd agent
python main.py dev   # hot-reload dev mode
```

---

## Multi-clinic Support

To run Sophia for multiple clinics, create additional YAML files:

```
config/businesses/clinic-a.yaml
config/businesses/clinic-b.yaml
```

Then run separate agent workers with different `CLINIC_CONFIG_PATH` values, each connecting to its own LiveKit SIP trunk.
