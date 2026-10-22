# Impact Circles Assessment

## Two projects, one FastAPI application

**Part 1 — Financial document assistant:** upload invoices or receipts, extract their
text, validate financial fields, save valid expenses, and summarize spending.

**Part 2 — Content generation and publishing:** submit research information, generate
three communication drafts, review/edit them, approve selected channels, and publish
to a working local HTTP mock.

> **Start exploring:** [Interactive API](http://localhost:8000/docs) ·
> [Financial tracker](http://localhost:8000/documents/expenses) ·
> [Expense summary](http://localhost:8000/documents/summary) ·
> [App health](http://localhost:8000/health)
>
> These links work after starting the app. This README provides clickable navigation,
> expandable guides and diagrams; Swagger provides the interactive request forms.

### Navigate

[Overview](#overview) · [Quick start](#quick-start) · [Project tree](#project-tree) ·
[Architecture](#architecture) · [Part 1](#part-1-financial-document-assistant) ·
[Part 2](#part-2-content-generation-and-publishing) · [Database](#database) ·
[Configuration](#configuration) · [Troubleshooting](#troubleshooting) ·
[Demo checklist](#demo-checklist) · [Limitations](#limitations)

---

## Overview

| | Part 1: financial documents | Part 2: research content |
|---|---|---|
| Input | PDF or image containing invoices/receipts | Project name, content type and description |
| AI task | Extract financial facts and classify expenses | Generate LinkedIn, newsletter and website drafts |
| Code checks | Source evidence, required fields, numbers, dates, totals, duplicates | Input/output structure, current revision, approval and selected channels |
| Storage rule | Save only validated, nonduplicate invoices | Save input and editable drafts before approval |
| Output | Expense tracker and category/currency/project summaries | Approved local mock posts with URLs and delivery logs |
| Human action | Inspect warnings and correct/re-upload invalid source documents | Review text, approve channels, then explicitly publish |
| API prefix | `/documents` | `/api/content` |

### Workflow at a glance

[![Flowchart showing financial document validation and content approval/publishing workflows](docs/images/project-workflows.png)](docs/images/project-workflows.png)

Click any diagram to open its full-resolution image. All diagrams are embedded PNG
images, so a Mermaid renderer is not required. Editable Graphviz sources are stored
next to their rendered images in `docs/images`.

### Technology

| Component | Used for |
|---|---|
| FastAPI + Pydantic | HTTP endpoints, input validation and Swagger forms |
| PostgreSQL + SQLAlchemy | Shared persistent storage and database operations |
| Groq, configured as `openai/gpt-oss-120b` by default | Financial extraction and content generation |
| pypdf | Read embedded PDF text |
| Tesseract + Poppler + Pillow | OCR scanned pages and uploaded images |
| Docker Compose | Run the API and PostgreSQL together |

There is one backend, one database and no separate frontend or publishing container.
The newsletter is generated and stored; email delivery is not included.

[Back to navigation](#navigate)

## Quick start

### Existing workspace

Your actual configuration is in `.env`. Start the app without printing secrets:

```bash
docker compose up -d --build
```

Open **[http://localhost:8000/docs](http://localhost:8000/docs)**.

There is one actual environment file: `.env` in the project root. Docker Compose
loads it automatically to resolve the database password. Python loads the same file
through the existing configuration code.

<details>
<summary><strong>Fresh checkout: configure the app for the first time</strong></summary>

1. Copy the example **only if you do not already have `.env`**:

   ```bash
   cp .env.example .env
   chmod 600 .env
   ```

2. Edit the actual `.env`:
   - Set your `GROQ_API_KEY`.
   - Choose a strong database password. Use the same value in `POSTGRES_PASSWORD`
     and the password component of `DATABASE_URL`.
   - Set a random `CONTENT_REVIEWER_TOKEN` for reviewer authorization.
   - Keep `OCR_LANGUAGES=eng+ara` when using the supplied Docker image.

3. Start the app:

   ```bash
   docker compose up -d --build
   ```

The example contains placeholders only. Private environment files and their backups
are excluded from Git and Docker builds. Do not place real credentials in this README.
For an existing PostgreSQL volume, preserve the working password: editing an environment
file alone does not change the database user's stored password.

</details>

<details>
<summary><strong>Run Python locally instead of running the API in Docker</strong></summary>

Use Python 3.11+, PostgreSQL, Tesseract with every configured language pack, and Poppler.
Docker remains the easiest way to install the OCR system dependencies.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r src/requirements.txt
uvicorn main:app --app-dir src --reload
```

`DATABASE_URL` in `.env` must point to the database reachable from your computer.
The supplied PostgreSQL container is available at `localhost:5434`.
Stop the Docker API first if it is already using port 8000.

</details>

<details>
<summary><strong>Stop, restart or inspect the app</strong></summary>

```bash
# Container status
docker compose ps

# Rebuild after code changes
docker compose up -d --build api

# Recreate the API after configuration changes
docker compose up -d --force-recreate api

# Stop services while preserving the database volume
docker compose stop
```

`GET /health` is a simple application liveness response. It does not execute a database
query. Compose separately checks PostgreSQL readiness with `pg_isready`.

</details>

[Back to navigation](#navigate)

## Project tree

Runtime files marked **private** are not committed. Cache folders and Git metadata
are omitted from this view. Automated test files were removed from this delivery.

```text
ImpactCircle_Assessment/
├── README.md                           # Unified guide for both projects
├── docs/
│   └── images/
│       ├── project-workflows.png        # Generated overview flowchart
│       ├── project-workflows.prompt.txt # Image generation prompt
│       ├── architecture.png            # Application architecture
│       ├── database-request-flow.png   # Request/session/database lifecycle
│       ├── financial-workflow.png      # Part 1 flowchart
│       ├── content-workflow.png        # Part 2 flowchart
│       ├── mock-publishing-flow.png    # Actual local HTTP publishing
│       ├── database-tables.png         # Table relationships
│       └── *.dot                       # Editable sources for rendered diagrams
├── Dockerfile                          # API image with OCR dependencies
├── compose.yaml                        # API + PostgreSQL services
├── .env                                # PRIVATE: actual runtime configuration
├── .env.example                        # Shareable placeholders
├── .gitignore                          # Excludes credentials, uploads and caches
├── .dockerignore                       # Excludes private env files and tests
└── src/
    ├── main.py                         # App startup and route registration
    ├── requirements.txt                # Python dependencies
    ├── Controllers/                    # Business logic
    │   ├── database.py                 # Initialize/upgrade database tables
    │   ├── documents.py                # Upload, validation gate and persistence
    │   ├── ocr.py                      # PDF text extraction and image OCR
    │   ├── financial.py                # Groq extraction, financial checks, duplicate keys
    │   ├── expenses.py                 # Expense filters and summaries
    │   ├── content.py                  # Generation, edits, approval, publishing and mock
    │   └── health.py                   # Application liveness response
    ├── Helpers/
    │   └── database.py                 # Shared engine and per-request sessions
    ├── Models/                         # Tables, schemas and constants
    │   ├── base.py                     # Shared SQLAlchemy model base
    │   ├── upload.py                   # One uploaded financial document
    │   ├── document.py                 # One financial expense/invoice
    │   ├── document_schema.py          # Financial API response shapes
    │   ├── financial_schema.py         # Extraction and validation types/categories
    │   ├── ocr_schema.py               # Extracted page/text types
    │   ├── content.py                  # Content and publication-log tables
    │   ├── content_schema.py           # Content API input/output schemas
    │   ├── content_constants.py        # Content prompt and publisher/reviewer settings
    │   ├── constants.py                # Shared/financial configuration and prompts
    │   ├── health_schema.py            # Health response schema
    │   └── migrations/
    │       ├── 001_document_text.sql
    │       ├── 002_validated_financial_data.sql
    │       ├── 003_multi_invoice_uploads.sql
    │       └── 004_expense_tracker.sql
    ├── Routes/                         # Thin HTTP routes calling controllers
    │   ├── documents.py                # Financial upload, retrieval, tracker and summary
    │   ├── content.py                  # Seven content operations + local mock routes
    │   └── health.py                   # /health
    └── uploads/                        # PRIVATE: retained source PDFs/images
```

**Where to make changes:** routes define the HTTP interface; controllers perform the
work; models define stored data, schemas and constants. Both projects reuse the
connection/session helper.

[Back to navigation](#navigate)

## Architecture

[![Application architecture](docs/images/architecture.png)](docs/images/architecture.png)

### How one request reaches the database

[![How a request uses the database](docs/images/database-request-flow.png)](docs/images/database-request-flow.png)

Closing a session is different from committing: `commit()` saves changes; `rollback()`
cancels changes that have not been committed. Publishing commits each channel result
separately so a later failure cannot erase an earlier successful delivery.

[Back to navigation](#navigate)

## Part 1 financial document assistant

### Processing illustration

[![Part 1 · Financial document processing](docs/images/financial-workflow.png)](docs/images/financial-workflow.png)

**Text versus OCR:** extraction is decided per page. A PDF page with selectable text
uses pypdf. A page with no extractable text uses OCR. PNG, JPEG, TIFF and WebP inputs
use OCR; multipage TIFF frames are supported. A PDF can therefore use text extraction
on some pages and OCR on others. A page containing some text currently skips OCR even
if images on that same page also contain text.

### Financial endpoints

| Method | Endpoint | What you get/do |
|---|---|---|
| POST | `/documents/upload` | Process a file and save validated, nonduplicate invoices |
| GET | `/documents/expenses` | Browse stored expenses; optional category/status/pagination |
| GET | `/documents/summary` | Totals grouped by project, category and currency |

<details open>
<summary><strong>Try it: upload invoices in Swagger</strong></summary>

1. Open [Swagger](http://localhost:8000/docs).
2. Expand `POST /documents/upload` and click **Try it out**.
3. Choose a PDF or supported image, then click **Execute**.
4. Read the saved invoices and warnings in the upload response. To browse saved expenses later, use `GET /documents/expenses`.

An illustrative compact upload response:

```json
{
  "id": "11111111-1111-4111-8111-111111111111",
  "processing_status": "validated",
  "saved_count": 1,
  "invoices": [
    {
      "id": "22222222-2222-4222-8222-222222222222",
      "invoice_date": "2026-10-20",
      "vendor": "CloudTools Demo Ltd",
      "invoice_number": "INV-1001",
      "description": "Research collaboration software",
      "amount": "120.00",
      "currency": "EUR",
      "category": "software",
      "project": "CRP-2026",
      "processing_status": "validated"
    }
  ],
  "warnings": []
}
```

These example IDs are fictional. The top-level ID identifies the upload; each nested ID identifies a saved invoice.

</details>

<details>
<summary><strong>Try it: category filters and pagination in the browser</strong></summary>

- [All expenses](http://localhost:8000/documents/expenses)
- [Software expenses](http://localhost:8000/documents/expenses?category=software)
- [First 10 validated software expenses](http://localhost:8000/documents/expenses?category=software&processing_status=validated&offset=0&limit=10)
- [Next 10 validated software expenses](http://localhost:8000/documents/expenses?category=software&processing_status=validated&offset=10&limit=10)
- [All expense summaries](http://localhost:8000/documents/summary)
- [Software summary](http://localhost:8000/documents/summary?category=software)

| Parameter | Endpoint | Meaning |
|---|---|---|
| `category` | Expenses and summary | Optional category filter |
| `processing_status` | Expenses | Optional stored status filter, usually `validated` |
| `offset` | Expenses | Skip this many records; default 0 |
| `limit` | Expenses | Return at most this many; default 100, maximum 500 |

Categories: `personnel`, `travel`, `equipment`, `software`, `events`,
`operational_expenses`. Filtering uses category, not project name. Summaries still
group results by project when present, category and currency. Different currencies
are never combined or converted.

</details>

### What gets validated and stored?

| Field | Meaning / policy |
|---|---|
| `invoice_date` | Valid ISO date, `YYYY-MM-DD` |
| `vendor` | Seller/service provider |
| `invoice_number` | Number without its label; optional |
| `description` | Expense description supported by source text |
| `amount` | Final total including tax; serialized as a decimal string |
| `currency` | Identifiable ISO currency code; missing currency prevents saving |
| `tax_amount`, `subtotal` | Optional stated monetary amounts |
| `discount_amount`, `other_charges` | Optional stated adjustments after subtotal |
| `category` | One of the six categories; unclear classification prevents saving |
| `project` | Optional explicitly stated project name/code |

Code verifies evidence quotes against extracted text. Full evidence and raw extraction
remain in storage. GET responses show useful `financial_evidence` quotes while omitting
quotes that exactly repeat normalized values, including repeated nulls. `raw_extraction`
is not returned. Compact upload responses omit these detailed audit fields.

When subtotal, tax and total are available, decimal arithmetic checks:

```text
expected total = subtotal + tax - discount_amount + other_charges
allowed difference = 0.01
```

Missing optional values are not invented. A single stated VAT percentage is also checked
for simple invoices without adjustments. Complex or ambiguous treatments require review
and prevent that invoice from being saved.

| Example | Result |
|---|---|
| INV-1001: subtotal EUR 100 + VAT EUR 20 = total EUR 120 | Save if all other checks pass |
| INV-1002: subtotal EUR 100 + VAT EUR 20, but stated total EUR 150 | Warn about EUR 30 mismatch; do not save invoice |
| Valid receipt without invoice number or tax details | Can pass; missing optional fields alone do not reject it |
| Missing currency | Warn and do not save |
| Same document/invoice uploaded again | Warn and do not save it again |
| File containing valid and invalid invoices | Save only valid invoices and return rejection warnings |

**Duplicate detection runs in code.** It uses normalized vendor + invoice number,
or a potential match on vendor + date + amount + currency when a number is missing.
A file hash also detects identical uploads. Database uniqueness rules and PostgreSQL
locks guard concurrent uploads.

**Summary policy:** include only validated expenses with a completed duplicate check
and no match. Previously stored review/unchecked legacy records remain excluded;
new uploads do not create invalid expense rows. For a mixed file, the complete original
source file is retained, but only validated invoices become expense rows.

### Financial response codes

| Code | Meaning |
|---|---|
| `201` | At least one invoice saved; status `partial` if there are warnings |
| `400` | Unsupported file or invalid PDF signature |
| `409` | Exact duplicate file, or all remaining valid invoices are duplicates |
| `413` | Upload exceeds the size limit |
| `422` | Unreadable file, no valid invoices, or failed validation; no new file/rows saved if none pass |
| `429`, `502`, `503` | AI rate limit, response or availability/configuration issue |

[Back to navigation](#navigate)

## Part 2 content generation and publishing

### Approval and publishing illustration

[![Part 2 · Content review and publishing](docs/images/content-workflow.png)](docs/images/content-workflow.png)

**Three generated outputs:** a professional LinkedIn post, a concise newsletter summary,
and a website title/article. Newsletter delivery is not implemented. Supported publishing
channels are **LinkedIn and Website**, both simulated locally by the implemented mock.

### Content endpoints

| Method | Endpoint | Responsibility |
|---|---|---|
| POST | `/api/content/` | Save original project input; return its ID |
| POST | `/api/content/{id}/generate/` | Generate and store all three drafts |
| GET | `/api/content/{id}/` | Retrieve source, generated outputs, revision and approval |
| PUT | `/api/content/{id}/` | Edit one or more generated outputs |
| POST | `/api/content/{id}/approve/` | Reviewer approves/rejects and selects channels |
| POST | `/api/content/{id}/publish/` | Publish the approved current content |
| GET | `/api/content/{id}/status/` | Read approval, selected channels and publication results |

<details open>
<summary><strong>Step 1 — Submit original research</strong></summary>

In Swagger, execute `POST /api/content/`:

```json
{
  "project_name": "Digital Learning Research",
  "content_type": "research_findings",
  "description": "Fictional study: 250 participants across three regions. Learning engagement improved by 30%."
}
```

Supported content types: `project_description`, `project_update`, `research_findings`,
`event_announcement`. The description must have 10–12000 characters.

Creation returns `201`, an `id`, `revision: 1`, `generated: null`, and `approved: false`.
Copy this content ID for the following operations. Creating input does not call the LLM.

</details>

<details>
<summary><strong>Step 2 — Generate and retrieve drafts</strong></summary>

Call `POST /api/content/ID/generate/` with no body, then `GET /api/content/ID/`.
Generation uses the existing Groq configuration and validates structured JSON before saving.

The `generated` object has this shape; the prose below is illustrative:

```json
{
  "linkedin": "Professional post about the supplied research...",
  "newsletter": "Concise summary for research stakeholders...",
  "website": {
    "title": "Digital Learning Research Findings",
    "body": "Introduction, structured headings, key findings and conclusion..."
  }
}
```

The first successful generation advances revision 1 to 2 and leaves approval false.
Generating again replaces current drafts, increases the revision and clears approval.
AI failure returns an error without overwriting the saved drafts.

</details>

<details>
<summary><strong>Step 3 — Edit using the current revision</strong></summary>

`PUT /api/content/ID/`

```json
{
  "revision": 2,
  "linkedin": "Reviewed update: 250 participants across three regions. Engagement improved by 30%."
}
```

Include only outputs you want to change: linkedin, newsletter, website, or a combination.
Editing website content requires its title and body together.

**Send the revision currently stored, not the next number.** If GET says revision 2,
send 2. After a real edit, the backend changes it to 3 and resets approval.
A no-op edit keeps the revision. A stale revision returns 409.

</details>

<details>
<summary><strong>Step 4 — Authorize, review and choose channels</strong></summary>

1. Open the actual `.env` locally.
2. Copy the value of `CONTENT_REVIEWER_TOKEN` without quotes.
3. In [Swagger](http://localhost:8000/docs), click **Authorize** at the top.
4. Paste it into **X-Reviewer-Token**, click **Authorize**, then **Close**.
5. Review the current generated text before executing approval.

The token is an HTTP header. Do not put it in the JSON body or prefix it with `Bearer`.

`POST /api/content/ID/approve/`

```json
{
  "revision": 3,
  "approved": true,
  "channels": ["linkedin"]
}
```

This approves delivery to **LinkedIn only**. The response still returns all generated
outputs for inspection; `channels` determines which will actually publish.
To approve both supported destinations, use `["linkedin", "website"]`.

To reject the current revision:

```json
{
  "revision": 3,
  "approved": false
}
```

Approval records the current revision and a digest of the outputs/channel selection.
Missing/incorrect token returns 403. Missing reviewer configuration returns 503.
Approval alone does not publish; the next endpoint is an explicit action.

</details>

<details>
<summary><strong>Step 5 — Publish, view the post and inspect status</strong></summary>

Call `POST /api/content/ID/publish/` with the reviewer header and no body.

The server checks approval again, creates durable publication intents, then makes an
actual HTTP request to the local mock for each selected channel. The mock checks the
approved payload, stores the received post and returns an ID/URL.

Read `GET /api/content/ID/status/`:

| Field | What to inspect |
|---|---|
| `approved`, `revision` | Whether the current content revision is approved |
| `channels` | Exactly which destinations were selected |
| `status` | Overall publishing state |
| `publications[].channel` | Destination of each current publication |
| `published_url`, `external_id` | Stored receipt and viewable local post |
| `published_at` | Successful delivery timestamp |
| `error`, `attempts` | Failure details and attempt history |

Open the actual `published_url` from the response. Its format is:

```text
http://localhost:8000/api/mock-publisher/PUBLICATION_ID/
```

A failed channel does not erase a successful one. Retry `/publish/` to retry failures;
already published deliveries are skipped and retain their URLs.

</details>

### Revisions: a concrete example

| Action | Stored revision | Approved? | Can publish? |
|---|---|---|---|
| Create original input | 1 | No | No |
| Generate the three drafts | 2 | No | No |
| Edit a draft using `revision: 2` | 3 | No | No |
| Approve using `revision: 3` and selected channels | 3 | Yes | Selected channels only |
| Edit again using `revision: 3` | 4 | No | No, until reviewed and approved again |

### What the mock really does

[![What happens during mock publishing](docs/images/mock-publishing-flow.png)](docs/images/mock-publishing-flow.png)

There are two additional supporting routes: POST and GET
`/api/mock-publisher/{publication_id}/`. The POST requires the reviewer header and an
existing authorized delivery intent. The GET displays safely escaped stored text.
The publisher accepts only local destinations and does not follow redirects or use
proxy settings when sending the reviewer credential.

### Content states and recovery

| State | Meaning |
|---|---|
| `created` | Original input stored; no generated drafts yet |
| `draft` | Generated/edited content awaits approval |
| `approved` | Reviewer approved the current content and channels |
| `rejected` | Reviewer rejected it; publishing is blocked |
| `publishing` | Delivery is in progress |
| `published` | Selected deliveries completed successfully |
| `partially_published` | Some channels succeeded and others failed |
| `failed` | Selected deliveries failed |

Publishing without current approval returns 409. Active publishing blocks editing and
approval changes. A stalled publish can be retried after its 120-second lease; it reuses
publication IDs. PostgreSQL row locks, a unique content/revision/channel constraint,
and attempt IDs protect retries and late workers. Current drafts are overwritten when
edited; older delivered payloads remain in logs, without a separate version-history table.

[Back to navigation](#navigate)

## Database

Both parts use the **same PostgreSQL database**, named `impact_circle`, and the same
[connection/session helper](src/Helpers/database.py). Their tables remain separate.

[![One database · Separate tables for each project](docs/images/database-tables.png)](docs/images/database-tables.png)

| Question | Part 1 | Part 2 |
|---|---|---|
| What does one parent row represent? | One uploaded source document | One research content request |
| What does one child row represent? | One validated invoice/expense | One channel delivery for a content revision |
| What prevents duplicates? | File hash and normalized financial identity | Unique content ID + revision + channel; mock reuses the publication ID |
| When is data saved? | Expense rows after validation and duplicate checks | Input/drafts before approval, publication results after authorized delivery |
| Where are originals? | Source file on disk, extracted text/evidence in database | Original research text in content_requests |

### Connection explained

```text
DATABASE_URL structure:
postgresql+psycopg2://USER:PASSWORD@HOST:PORT/DATABASE
```

- **Engine:** manages reusable database connections.
- **Session:** the database workspace supplied to a request by `get_db()`.
- **Model:** Python definition mapped to a database table.
- **Foreign key:** links a child row to its parent ID.
- **Commit:** makes pending changes permanent.
- **Rollback:** cancels uncommitted changes.

| Connecting from | Host and port |
|---|---|
| API container | `postgres:5432` |
| Your computer / database client | `localhost:5434` |
| Browser to the API | `localhost:8000` |

Compose overrides the API's DATABASE_URL to use the internal database hostname. Local
Python execution reads DATABASE_URL from `.env`. The API uses psycopg2 as its
PostgreSQL driver through SQLAlchemy.

At startup, idempotent financial SQL migrations update existing tables, and SQLAlchemy
creates missing registered tables for both parts. `create_all()` does not replace general
schema migrations and does not erase existing data. PostgreSQL data lives in the named
Docker volume `postgres_data`; source uploads are mounted from `src/uploads`.

[Back to navigation](#navigate)

## Configuration

The actual `.env` is private. [.env.example](.env.example) contains safe
placeholders. Real keys, database passwords and reviewer tokens must not appear in
source code, examples, screenshots or shared logs.

<details>
<summary><strong>Expand the environment-variable reference</strong></summary>

| Variable | Purpose / current default |
|---|---|
| `DATABASE_URL` | Local Python database connection string |
| `POSTGRES_PASSWORD` | Compose database password; match DATABASE_URL for local access |
| `GROQ_API_KEY` | Actual Groq API credential |
| `GROQ_MODEL` | `openai/gpt-oss-120b` by default; used by both parts |
| `UPLOAD_DIR` | Source document storage; Compose sets `/app/uploads` |
| `OCR_LANGUAGES` | `eng+ara`; Docker installs both packs |
| `MAX_PDF_MB` | 50 MB per upload; also applies to image inputs |
| `MAX_DOCUMENT_PAGES` | 500 pages/frames |
| `MAX_EXTRACTED_CHARACTERS` | 5,000,000 characters |
| `GROQ_BATCH_CHARACTERS` | 12,000 characters per financial model batch |
| `CONTENT_REVIEWER_TOKEN` | Private shared reviewer credential |
| `CONTENT_PUBLISH_URL` | `http://127.0.0.1:8000/api/mock-publisher` |
| `CONTENT_PUBLIC_URL` | `http://localhost:8000` for returned post links |

Image frames are additionally limited to 40 million pixels. Content-generation timeouts
and the publisher's 10-second HTTP timeout/120-second lease are defined in code.

If you change the API port, adjust the publishing URLs to the actual internal and
browser-reachable addresses. Environment changes require recreating the API container.

</details>

[Back to navigation](#navigate)

## Troubleshooting

<details>
<summary><strong>“Content changed. Read the latest revision first.”</strong></summary>

Execute `GET /api/content/ID/`. Copy its current revision into your edit or approval
request. Do not increment it yourself. For example, GET returning 2 means send 2;
the backend changes it to 3 after a real edit.

</details>

<details>
<summary><strong>“A valid reviewer token is required.”</strong></summary>

Copy CONTENT_REVIEWER_TOKEN from the actual `.env`. Scroll to the top of Swagger,
click **Authorize**, paste the plain value under X-Reviewer-Token, and authorize.
Execute the approval/publish request again. The token does not belong in the JSON body.

</details>

<details>
<summary><strong>“I approved only LinkedIn, but the response includes website/newsletter text.”</strong></summary>

The approval response returns the complete saved content record. Check `channels`:
`["linkedin"]` means only LinkedIn is authorized for publication. The returned presence
of another draft does not authorize publishing it. Newsletter is never emailed.

</details>

<details>
<summary><strong>“My invoice was read but not saved.”</strong></summary>

Read `warnings` or `detail.warnings`. Missing essential fields, unsupported evidence,
inconsistent amounts and duplicate matches prevent saving. The validator does not rewrite
a stated total to make it balance. For mixed uploads, check saved_count and warnings;
only validated invoices become expense rows.

</details>

<details>
<summary><strong>“OCR language data is missing” or a scan has no readable text.</strong></summary>

Check OCR_LANGUAGES in the actual `.env`. Every listed language must be installed.
The supplied Dockerfile includes English and Arabic plus Poppler. For local Python,
install those system packages yourself. A clearer scan may be required; OCR cannot
recover text that the scan does not make readable.

</details>

<details>
<summary><strong>“POSTGRES_PASSWORD is missing” or database login fails.</strong></summary>

Run Docker Compose from the project root, where `.env` contains POSTGRES_PASSWORD.
Ensure POSTGRES_PASSWORD matches the existing PostgreSQL user's password and the local
DATABASE_URL. Existing volumes retain their credentials; changing only `.env` does not
rotate the stored database password. Do not delete the volume to fix a configuration typo.

</details>

<details>
<summary><strong>Groq rate limit, invalid output or generation unavailable.</strong></summary>

Check the configured key/model privately and inspect the returned error code. Creating,
editing, approving, reading and publishing content do not call the LLM; generation does.
Financial uploads call it after source extraction unless rejected earlier, such as an
identical file upload. Retry rate-limited work later. For dense financial pages, adjust
the batch setting or split the source document within the configured limits.

</details>

<details>
<summary><strong>Publishing failed or is stuck in progress.</strong></summary>

Read `/api/content/ID/status/`, including per-channel errors and attempts. Verify the
local publishing URL and port, then retry `/publish/`. Successful channels are skipped.
For an interrupted worker, wait for the 120-second lease before retrying. While an active
publication is pending, editing and approval changes are blocked.

</details>

[Back to navigation](#navigate)

## Demo checklist

Use fictional inputs. These are manual demonstration steps; no automated test suite
is included in this delivery, as requested.

### Part 1

- [ ] Upload a text-based PDF; inspect normalized fields and the upload ID.
- [ ] Upload an image or scanned PDF; inspect the OCR-derived result.
- [ ] Upload INV-1001 with total EUR 120 and confirm it saves once.
- [ ] Upload it again and inspect the duplicate warning.
- [ ] Upload INV-1002 with stated total EUR 150 versus expected EUR 120; inspect the rejection.
- [ ] Open the tracker and a category-filtered summary.

### Part 2

- [ ] Create fictional research input and generate the three drafts.
- [ ] Read the current revision and edit one output.
- [ ] Attempt publishing before approval; confirm 409.
- [ ] Authorize with the private reviewer token and approve LinkedIn only.
- [ ] Publish and open the returned local mock URL.
- [ ] Read publication timestamps, receipts and attempts in the status endpoint.
- [ ] Publish again; confirm the existing delivery is reused.
- [ ] Edit again; confirm approval resets and publishing is blocked until reapproval.

[Back to navigation](#navigate)

## Limitations

- This is a local prototype. Financial endpoints and content input/read/edit endpoints
  are not user-authenticated; content approval/publishing use a shared demo reviewer
  token. There is no per-user login, reviewer dashboard or SSO.
- Groq needs a valid key and network access. Local OCR does not require a paid OCR API.
  Reviewers must verify generated claims; prompts and schema validation do not prove
  factual accuracy.
- OCR quality, page attribution and configured limits affect extraction. Mixed text/image
  content on one page may need manual inspection. There is no fixed invoice count,
  but page, byte, character, context and provider limits still apply.
- Financial amounts use NUMERIC(14,2). Negative credit notes, currencies needing more
  than two decimals and complex tax/discount rules require manual handling. No exchange
  rates are inferred. Duplicate matching is heuristic; a match may need investigation.
- PostgreSQL is the expense tracker; there is no Sheets/Airtable synchronization. Invalid
  invoices are not persisted as expenses, and there is no financial review-resolution UI.
- Content generation and publishing are synchronous. Current drafts are overwritten on
  edits, with a revision counter protecting approval. There is no separate history table
  or durable background-job system.
- LinkedIn/website publishing is a persistent local HTTP simulation. Real accounts/CMS
  integrations are not connected. A production adapter needs appropriate permissions
  and persistent retry reconciliation; changing the URL alone is insufficient.
- Newsletter content is stored only. No emails, notifications or messages are delivered
  to external recipients. The publication response/status serves as the user-visible result.
- Mock pages display escaped plain text/Markdown rather than a full CMS theme. Previously
  published pages remain historical snapshots even when current drafts are edited.

---

**Ready to use it?** [Open Swagger](http://localhost:8000/docs) or
[return to the quick start](#quick-start).
