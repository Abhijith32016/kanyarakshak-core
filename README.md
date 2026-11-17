KanyaRakshak
A Distributed LLM-Integrated Personal Safety System with Geospatial Risk Analysis
KanyaRakshak is a cloud-deployed personal safety web application that
combines live location telemetry, emergency SOS handling, geospatial
responder discovery, machine-learning-based risk analysis, and a
conversational AI assistant.
The project was developed as a B.Tech capstone. It explores how
geospatial processing, distributed backend services, and language-model
assistance can be brought together in a single application. It is a
research and engineering prototype, not a production
emergency-response service.
Live demo: https://kanyarakshak.netlify.app
Source code: https://github.com/Abhijith32016/kanyarakshak-core
Research preprint: KanyaRakshak: A Distributed LLM-Integrated
Personal Safety System with Geospatial Risk Scoring and a Real-Data
Evaluation
Zenodo DOI: https://doi.org/10.5281/zenodo.23955487
Hackathon: Winner, RAMpage V2.5 24-Hour Hackathon (highest
overall score across the tracks)
---
Contents
Overview
Core capabilities
System architecture
Technology stack
Machine-learning and geospatial
components
Evaluation and results
API overview
Repository structure
Local development
Environment configuration
Known limitations
Future work
---
Overview
The application is organized around three connected functions:
Emergency response: A user can trigger an SOS alert. The backend
records the alert and current location, searches for nearby
responders using Redis geospatial commands, and initiates
notification and location-update workflows.
Location awareness: The browser obtains location coordinates
through the Geolocation API and sends telemetry to the backend.
Redis stores current location information and supports proximity
searches.
Conversational assistance: A chat interface sends messages to a
backend endpoint, which retrieves session context and relevant risk
information before requesting a response from an external language
model.
The system uses managed cloud services rather than requiring dedicated
hardware. Its components communicate through HTTP APIs and shared Redis
state.
---
Core capabilities
Emergency SOS and responder discovery
The frontend submits an SOS request with the user's current
coordinates.
The FastAPI backend creates or updates the alert state in Redis.
Redis geospatial indexing (`GEOADD` and `GEOSEARCH`) is used to
identify nearby responders. The prototype uses an approximately
500-metre nearby-responder search radius.
The application sends alert notifications through its configured
webhook integration.
Location updates can continue to be broadcast periodically while an
alert remains active.
An alert can be marked as resolved, after which the associated
tracking workflow stops.
Important: The notification integration is a prototype mechanism. It
is not connected to a verified emergency dispatch service or public
safety authority.
Live location telemetry
The browser uses the HTML5 Geolocation API to obtain coordinates,
subject to user permission and browser support.
The frontend sends location updates to the backend.
The backend stores current location data in Redis geospatial
structures.
Leaflet is used to display map information in the browser.
Redis Streams are used to separate telemetry ingestion from
subsequent processing.
Browser geolocation requires a secure context (normally HTTPS) and may
be interrupted by mobile background restrictions, loss of connectivity,
or unavailable location permissions.
Conversational safety assistant
The chat endpoint uses the Groq API with the `openai/gpt-oss-20b`
model.
Conversation history is maintained per session using Redis.
The assistant can receive relevant application-generated context,
including a medium- or high-risk tier for the user's last known
location.
The language model is accessed through an external inference API; it
is not hosted as part of the application backend.
The assistant is intended to provide conversational support. Its
responses should not be treated as verified emergency instructions,
professional advice, or a substitute for contacting local emergency
services.
---
System architecture
┌──────────────────────────────┐
│       Browser Frontend       │
│  HTML / JavaScript /         │
│  Tailwind CSS / Leaflet      │
│  Browser Geolocation API     │
└──────────────┬───────────────┘
               │ HTTPS / JSON
               ▼
┌──────────────────────────────┐
│       FastAPI Backend        │
│       Python / Uvicorn       │
│  SOS • Telemetry • Chat      │
│  Alert state • Notifications│
└───────┬──────────┬───────────┘
        │          │
        ▼          ▼
┌──────────────┐  ┌─────────────────────┐
│ Upstash      │  │ Groq API            │
│ Redis        │  │ openai/gpt-oss-20b  │
│              │  │ Conversational AI   │
│ Sessions     │  └─────────────────────┘
│ Alert state  │
│ GEO index    │
│ Redis Streams│
└──────┬───────┘
       │
       ▼
┌──────────────────────────────┐
│ Notification integration     │
│ Discord webhook (deployed    │
│ prototype integration)       │
└──────────────────────────────┘
Deployment components
Component                             Deployment / service
---
Frontend                              Netlify
Backend                               Render, running FastAPI with Uvicorn
State, geospatial index and streams   Upstash Redis
LLM inference                         Groq API
Prototype alert notification          Discord webhook
The notification path changed during development: `ntfy.sh` worked
during local testing but did not work reliably after deployment, so a
Discord webhook was used for the deployed prototype.
---
Technology stack
Layer                   Technologies
---
Frontend                HTML, JavaScript, Tailwind CSS, Leaflet
Browser location        HTML5 Geolocation API
Backend                 Python, FastAPI, Uvicorn
State and caching       Upstash Redis
Geospatial operations   Redis `GEOADD`, `GEOSEARCH`
Event processing        Redis Streams
Conversational AI       Groq API, `openai/gpt-oss-20b`
Clustering              DBSCAN with Haversine distance
Classification          Random Forest
API communication       HTTPS, JSON
Frontend hosting        Netlify
Backend hosting         Render
Version control         Git, GitHub
---
Machine-learning and geospatial components
Synthetic-data experiment
A synthetic location dataset was created to test the initial geospatial
and risk-classification workflow.
DBSCAN used Haversine distance with an `eps` setting of 400 metres
and `min_samples` of 8.
The generated dataset contained four planted spatial zones and 116
background points treated as noise.
A Random Forest classifier was used for an initial risk-tier
experiment.
The first experiment produced 100% accuracy because the target
labels were derived from a distance feature supplied to the model.
The data-generation and evaluation setup was revised to reduce this
leakage. The corrected experiment reported 82% accuracy on held-out
synthetic data.
The 82% result is synthetic-data validation only. It is not a
measure of real-world safety prediction performance and is not evidence
that the deployed application can reliably predict danger.
Evaluation using public Chicago records
A separate retrospective experiment evaluated the spatial methodology
using 68,648 public-place incident records from the City of Chicago
covering 2021--2023.
The dataset does not contain victim-gender information. It is therefore
not a women-specific evaluation, and it does not represent Hyderabad or
another Indian city. This experiment evaluates the methodology on the
selected public-place incidents; it does not mean that the deployed
KanyaRakshak risk model was retrained on Chicago data.
The analysis compared DBSCAN-derived zones with K-Means and a grid-based
top-N baseline. It also evaluated a Random Forest risk-tier classifier
against simple baselines.
---
Evaluation and results
The project was evaluated in three distinct ways: backend engineering
tests, a synthetic-data experiment, and a forward-in-time analysis of
public Chicago records. These results measure different aspects of the
work and should not be combined into a single claim of predictive
performance.
Backend concurrency and latency
A Locust test with 10 simulated users exposed a blocking Redis operation
in an asynchronous request path. Moving the blocking operation to
`asyncio.to_thread` reduced the measured average SOS endpoint latency.
Measurement                                  Before change      After change
---
Requests completed in the reported run                  47                72
Average SOS endpoint latency                      27.491 s           9.719 s
Throughput                                 0.33 requests/s   0.88 requests/s
Failed requests                                          0                 0
These are measurements from successive development runs, not a
controlled A/B experiment. They should be interpreted as evidence of an
observed improvement during debugging, not as a production capacity
guarantee.
Additional observed timings included approximately 1.2 seconds for a
warm LLM response, around 33 seconds for a cold backend start, and
approximately 1.5 seconds for a Redis Stream update to become visible in
the observed test.
Chicago spatial evaluation
---
Method                     Next-year incident        Next-year incident
capture, 2021→2022        capture, 2022→2023
---
DBSCAN zones                            51.9%                     53.8%
K-Means                                 39.2%                     43.7%
Grid top-N                              57.0%                     59.3%
DBSCAN captured more next-year incidents than K-Means in these two
splits, but fewer than the grid top-N baseline. The results do not
establish DBSCAN as the best-performing method.
Chicago risk-tier classification
Metric       Random Forest   Majority-class baseline
---
Accuracy             59.4%                     55.2%
Macro-F1             0.497                     0.475
The classifier's improvement over the majority-class baseline was
modest. The results require further testing with repeated temporal
splits, stronger baselines, and statistical analysis.
---
API overview
The backend exposes application endpoints for telemetry, SOS handling,
chat, and alert resolution. The exact request and response schemas are
defined by the FastAPI application.
---
Method                  Endpoint                   Purpose
---
`POST`                  `/api/v1/telemetry`        Submit a location
update
`POST`                  `/api/v1/voice-distress`   Trigger an SOS alert
`POST`                  `/api/v1/chat`             Send a message to the
conversational
assistant
`GET`                   `/api/v1/resolve`          Mark an active alert as
resolved
FastAPI's interactive API documentation is available at `/docs` when the
backend is running and the route is enabled.
---
Repository structure
The following is the high-level project layout. Refer to the repository
itself for the current, exact file tree.

kanyarakshak-core/
├── backend/
│   ├── main.py
│   ├── database.py
│   ├── requirements.txt
│   ├── render.yaml
│   └── .env.example
├── dashboard/
│   └── index.html
├── chatbot/
│   └── app.py
├── netlify.toml
├── docker-compose.yml
└── README.md
---
Local development
Prerequisites
Python 3.11 or a compatible version supported by the backend
dependencies
Git
An Upstash Redis database
A Groq API key
Node.js is not required for the static HTML frontend unless you add
a separate frontend build process
1. Clone the repository
git clone https://github.com/Abhijith32016/kanyarakshak-core.git
cd kanyarakshak-core
2. Install backend dependencies
cd backend
pip install -r requirements.txt
3. Configure environment variables
Copy the example environment file:
cp .env.example .env
Add the required values to `.env`. Do not commit real credentials or
secrets.
4. Start the backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
5. Open the frontend
Open `dashboard/index.html` in a browser and ensure its API base URL
points to the local backend, normally:
http://localhost:8000
For local geolocation testing, use a browser-supported secure context
such as `localhost` and grant location permission.
---
Environment configuration
The application uses environment variables for service credentials and
deployment-specific URLs. The exact names should match the backend's
`.env.example` and configuration code.
Common configuration values include:
---
Variable                            Purpose
---
`GROQ_API_KEY`                      Credential for Groq API access
`REDIS_URL`                         Redis connection URL; use the TLS
URL supplied by Upstash where
applicable
`BASE_URL`                          Public backend base URL used when
constructing alert or resolution
links
Never place API keys, Redis credentials, webhook URLs, or other secrets
in source control. Keep `.env` out of Git and configure production
secrets through the hosting provider's environment-variable settings.
---
Known limitations
KanyaRakshak is a prototype. The following limitations are important
when interpreting its results:
Synthetic risk model: The risk model used in the deployed
demonstration is based on synthetic data. Its reported 82% accuracy
is not real-world validation.
Separate Chicago evaluation: The Chicago experiment evaluates
the spatial methodology on public-place incident records. It does
not validate women's safety risk in Hyderabad or India, and the
dataset does not identify victim gender.
Modest predictive results: DBSCAN did not outperform the grid
top-N baseline in the reported forward-in-time comparisons. The
Random Forest improvement over the majority baseline was limited.
Browser location constraints: Geolocation depends on user
permission, device support, network availability, and browser
behaviour. Background location updates are not guaranteed on mobile
devices.
Prototype notifications: The Discord webhook is not an
emergency-services integration. It does not provide verified
dispatch, guaranteed delivery, or professional responder coverage.
LLM safety: The conversational assistant has not undergone a
formal safety evaluation. Its output can be incorrect or incomplete.
Infrastructure constraints: The hosted prototype uses
shared/free-tier services, which can introduce cold starts and
variable latency.
Authentication and access control: Production use would require
stronger identity, authorization, privacy, and audit controls.
Scale of testing: The reported load test is limited and does not
establish production-scale capacity or reliability.
The system should not be relied upon as the sole means of obtaining
emergency assistance.
---
Future work
Potential next steps include:
Evaluating risk models on appropriately sourced, representative
real-world data.
Running repeated rolling-time evaluations and significance tests.
Comparing DBSCAN with stronger spatial baselines, including kernel
density estimation.
Testing the system with larger and more controlled concurrent
workloads.
Evaluating Redis Streams against a dedicated message broker under
higher event volumes.
Adding robust user authentication, role-based access control, and
audit logging.
Conducting a structured safety and reliability evaluation of the
conversational assistant.
Improving mobile background location handling and notification
reliability.
Integrating with verified emergency-response services only after
appropriate operational, legal, and safety requirements are met.
---
Acknowledgements
The project was completed as a B.Tech capstone at Koneru Lakshmaiah
Education Foundation, Hyderabad, India, under the supervision of K.
Hema.
Research citation
If you refer to the research evaluation, cite the project preprint:
> *KanyaRakshak: A Distributed LLM-Integrated Personal Safety System
> with Geospatial Risk Scoring and a Real-Data Evaluation.* Zenodo.
> https://doi.org/10.5281/zenodo.23955487
---
Disclaimer
KanyaRakshak is an academic prototype developed for research and
demonstration. It is not a certified safety product, emergency dispatch
platform, or substitute for local emergency services. Location data and
AI-generated responses may be delayed, unavailable, or inaccurate. Do
not rely on this application as the only response in an emergency.
