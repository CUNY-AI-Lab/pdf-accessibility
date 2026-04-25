# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current Deployment State

**The deployed stack is OFFLINE as of 2026-04-25.** Pipeline trigger removed and Amplify frontend gated behind basic auth — both reversible. See `docs/OFFLINE_STATE.md` for the bring-online runbook, idle-cost breakdown, and resource references (Amplify app id, bucket name, state machine ARN, live Cognito pool).

Backups for the offline action live in `.offline-backup/` (gitignored).

## Project Overview

PDF Accessibility Solutions: an AWS-based tool that remediates PDFs for WCAG 2.1 Level AA compliance. Two approaches exist side-by-side:

- **PDF-to-PDF** (`app.py`): Step Functions pipeline using Lambda (Docker). AI-powered tagging via Bedrock vision models.
- **PDF-to-HTML** (`pdf2html/`): Single Lambda using Bedrock Data Automation. Separate TypeScript CDK stack.
- **Frontend** (`pdf_ui/`): React 19 + MUI 6 app deployed to AWS Amplify. Uses OIDC auth with Cognito. Separate repo: `PDF_accessability_UI`.

## Build & Deploy Commands

### CDK Backend (PDF-to-PDF)
```bash
pip install -r requirements.txt
cdk synth
cdk deploy PDFAccessibility \
  -c bedrock_vision_model=qwen.qwen3-vl-235b-a22b \
  -c bedrock_text_model=openai.gpt-oss-120b-1:0
```

### Frontend (React)
```bash
cd pdf_ui && npm install
npm start          # Dev server
npm run build      # Production build (requires REACT_APP_* env vars)
npm test           # Tests (stub only — no real test coverage)
```

Required env vars for frontend build: `REACT_APP_AUTHORITY`, `REACT_APP_AWS_REGION`, `REACT_APP_PDF_BUCKET_NAME`, `REACT_APP_HTML_BUCKET_NAME`, `REACT_APP_HOSTED_UI_URL`, `REACT_APP_IDENTITY_POOL_ID`, `REACT_APP_USER_POOL_CLIENT_ID`, `REACT_APP_USER_POOL_ID`, `REACT_APP_DOMAIN_PREFIX`, `REACT_APP_UPDATE_FIRST_SIGN_IN`, `REACT_APP_UPLOAD_QUOTA_API`. All defined in `src/utilities/constants.jsx`. For local builds, these must be in `pdf_ui/.env` (Amplify branch env vars are NOT injected into manual deploys).

### Automated Deployment
```bash
./deploy.sh        # Interactive: picks solution, models, deploys via CodeBuild
```

### PDF-to-HTML CDK (TypeScript)
```bash
cd pdf2html/cdk && npm install && npx cdk deploy
```

### Verifying Pipeline After Deploy
```bash
# Check latest Step Functions execution
aws stepfunctions list-executions \
  --state-machine-arn "$(aws stepfunctions list-state-machines --query 'stateMachines[?contains(name,`PdfAccessibility`)].stateMachineArn' --output text)" \
  --max-results 3 --query 'executions[*].[status,startDate]' --output table

# Check Lambda logs (replace function name)
aws logs tail "/aws/lambda/<FUNCTION_NAME>" --since 30m
```

## Architecture: PDF-to-PDF Pipeline

```
S3 Upload (pdf/) → PDF Splitter → Step Functions Parallel:
  Branch 1: Map(AI Tagger → Alt-Text) → Merger → Title Generator → Post-Check
  Branch 2: Pre-Check (audits original PDF)
```

### Key Components

| Component | Path | Language | Runtime |
|---|---|---|---|
| CDK Stack | `app.py` | Python | CDK |
| AI Tagger | `lambda/ai-tagger-lambda/` | Python | Docker Lambda |
| Alt-Text Generator | `lambda/alt-text-lambda/` | Node.js | Docker Lambda |
| PDF Splitter | `lambda/pdf-splitter-lambda/` | Python | Zip Lambda (`Code.from_docker_build`) |
| PDF Merger | `lambda/pdf-merger-lambda-python/` | Python | Docker Lambda |
| Title Generator | `lambda/title-generator-lambda/` | Python | Docker Lambda |
| Pre/Post Checker | `lambda/{pre,post}-remediation-accessibility-checker/` | Python | Docker Lambda |
| Shared Checker Logic | `lambda/accessibility-checker-common/` | Python | Copied into pre/post dirs |

### S3 Key Conventions & Data Flow

The pipeline uses S3 key prefixes to pass data between Lambdas. Understanding these paths is critical:

```
pdf/<user>_<timestamp>_<filename>.pdf                          ← User upload (triggers splitter)
temp/<basename>/<basename>_chunk_N.pdf                         ← Splitter output (5-page chunks)
temp/<basename>/output_autotag/COMPLIANT_<chunk>.pdf           ← AI Tagger output (tagged PDF)
temp/<basename>/output_autotag/<chunk>_temp_images_data.db     ← AI Tagger output (SQLite DB)
temp/<basename>/output_autotag/images/<chunk>_<img>.png        ← AI Tagger output (extracted images)
temp/<basename>/FINAL_<chunk>.pdf                              ← Alt-Text output (final per-chunk)
temp/<basename>/merged_<basename>.pdf                          ← Merger output
result/COMPLIANT_<basename>.pdf                                ← Title Generator output (final result)
temp/<basename>/accessability-report/*_before_remidiation.json ← Pre-check report
temp/<basename>/accessability-report/*_after_remidiation.json  ← Post-check report
```

**Inter-Lambda data passing via SQLite**: The AI Tagger creates a SQLite DB per chunk with figure metadata (image paths, page context, pikepdf object numbers). The Alt-Text Lambda downloads this DB to match generated alt text to the correct Figure struct elements by `pdf_obj_number`.

**Merger key derivation**: The merger receives chunk `s3_key` values from the Map state and prepends `FINAL_` to the filename portion to find alt-text-completed chunks.

### Model Abstraction

All Bedrock calls use the **Converse API** (not InvokeModel) for model-agnostic support. Configured via env vars `BEDROCK_MODEL_ID_VISION` and `BEDROCK_MODEL_ID_TEXT`. Defaults: Qwen3 VL 235B (vision), GPT-OSS 120B (text). Cross-region inference profile IDs (e.g. `us.qwen.*`) are resolved to full ARNs at runtime using STS.

### Accessibility Checker

`pdf_accessibility_checker.py` implements 27 PDF/UA + WCAG checks using pikepdf (structure tree) and PyMuPDF (content). The checker lives in `lambda/accessibility-checker-common/` and is copied to both `pre-` and `post-remediation-accessibility-checker/` directories — all three files must stay in sync.

**Automated checks include:**
- Document: MarkInfo, StructTreeRoot, Lang, Title, DisplayDocTitle, PDF/UA ID, RoleMap, Font Embedding, Unicode Mapping, Artifact Marking (checks content streams for `/Artifact BMC` markers)
- Navigation: Tab Order, Outlines (validates `/Count` and `/First`), Reading Order (struct tree MCID vs visual layout), Annotation Tagging
- Structure: Heading Nesting (reports all skips), Figure Alt Text, Table Headers/Scope (fail not warn), List Structure (validates LI has LBody), Language of Parts, Symbolic Font ActualText
- Links: Alt Text, Meaningful Text (checks for generic link text like "click here")
- Forms: Field Labels (TU tooltip)
- Visual: **Color Contrast** (automated via PyMuPDF pixmap + WCAG luminance formula — 4.5:1 normal, 3:1 large text), Text Reflow (manual), Non-Text Contrast (manual)

**Color Contrast implementation** (`_check_color_contrast`): Renders each page at 150 DPI, extracts text spans with `page.get_text("dict")`, samples background color from 4 edge pixels around each text bbox via pixmap, calculates WCAG contrast ratio. Falls back to manual warning if pixmap rendering fails.

**Reading Order implementation** (`_check_reading_order`): Detects multi-column layouts by analyzing horizontal gaps between text blocks. Single-column pages with top-to-bottom flow pass automatically. Multi-column pages trigger a warning with specific page numbers.

Output format must match the UI schema:
```json
{"Summary": {"Description": "...", "Passed": N, "Failed": N, "Needs manual check": N},
 "Detailed Report": {"Category": [{"Rule": "...", "Description": "...", "Status": "Passed|Failed|Needs manual check"}]}}
```
**Note**: The key is `"Summary"` (capital S). The internal accumulator uses lowercase `"summary"`. The `_convert_to_ui_format()` function maps between them.

### Structure Tree & MCID Linkage

The AI tagger writes a properly linked PDF/UA structure tree:
- Each structure element gets `/Pg` (page reference) and `/K` (MCID integer) linking it to page content
- ParentTree `/Nums` maps page indices to arrays of struct element refs ordered by MCID
- Figure elements record their pikepdf object numbers in SQLite (`pdf_obj_number` column) so the alt-text generator can match by object number instead of sequential index
- Lists: consecutive LI elements are wrapped in `/L` containers with `/LI` → `/Lbl` + `/LBody` children
- Tables: LLM extracts row/column structure; tags written as `/Table` → `/TR` → `/TH` (with `/Scope Column`) + `/TD`

### PDF Merger (Python/pikepdf)

The merger (`lambda/pdf-merger-lambda-python/merger.py`) preserves accessibility metadata across chunks:
- Copies all structure tree children from each chunk under a unified `/Document` element
- Remaps `/Pg` page references from chunk-local to global page indices
- Offsets MCID values by running total from prior chunks
- Merges ParentTree `/Nums` entries with remapped page indices
- Creates fresh `/MarkInfo`, `/Lang`, `/ViewerPreferences` from first chunk (avoids `copy_foreign` for these)

## Important Patterns & Gotchas

### pikepdf
- `pikepdf.Dictionary()` constructor does NOT accept `pikepdf.Name` as dict keys. Set attributes individually: `d["/Key"] = value`
- `pikepdf.Name()` requires leading `/`: use `pikepdf.Name("/H1")` not `pikepdf.Name("H1")`
- Indirect references auto-dereference on attribute access — check `pikepdf.Name.S in child` instead of calling `pikepdf.Object(child)`
- **`copy_foreign` only works with indirect objects**. Direct objects (Dictionary, Array, String, Name created inline) throw `ForeignObjectError`. Use `_safe_copy_foreign()` in the merger which catches this and manually rebuilds the object, or create objects fresh in the target PDF instead of copying.

### Lambda Packaging
- Lambdas using native C libraries (pikepdf, PyMuPDF) must be `DockerImageFunction` with `DockerImageCode.from_image_asset()`, not zip packages via `Code.from_docker_build()`
- The Dockerfiles install system deps: `dnf install -y qpdf-libs qpdf-devel gcc python3-devel`
- The PDF Splitter is the exception — uses `pypdf` (pure Python) and deploys via `Code.from_docker_build()` as a zip Lambda

### Step Functions State
- The Parallel state runs two branches simultaneously on the same input
- LambdaInvoke results stored via `result_path` (e.g., `result_path="$.ai_tagger_result"`)
- AI Tagger and Alt-Text tasks have 14-minute timeouts and 2 retries with exponential backoff (`add_retry` with `backoff_rate=2.0`)
- Merger task uses `output_path=$.Payload` — subsequent tasks receive the raw merger string output
- Title Generator task has no `output_path` — post-checker receives the full LambdaInvoke envelope and navigates `event.Payload.body`

### Bedrock Limits & Throttling
- Qwen models have ~1MB image payload limit. Images are resized via `sharp` (Node) before sending.
- Context text truncated to 4000 chars to avoid payload limits.
- Converse API response: extract text via `response['output']['message']['content']` — iterate blocks looking for `'text'` key (some models structure content blocks differently).
- Alt-Text Lambda uses exponential backoff between image Bedrock calls (1s base, doubles on failure, caps at 15s). Aborts after 5 consecutive failures.
- Link alt-text generation uses concurrency pool (max 3 concurrent Bedrock calls) to avoid throttling. Falls back to URL-based alt text on failure.
- Bedrock client (`bedrock_client.js`) uses aggressive backoff for throttling errors (3s base with 3x multiplier vs 1s for other errors).

### PyMuPDF TOC
- `doc.set_toc()` requires first entry at level 1 with no jumps > 1 between consecutive entries. Normalize heading levels before calling.

### Frontend Deployment
- Amplify manual deploy: zip must contain files at root, not inside a `build/` subdirectory: `cd build && zip -r ../deploy.zip .`
- Deploy sequence: `aws amplify create-deployment` → `curl -T` zip to presigned URL → `aws amplify start-deployment`
- `REACT_APP_AUTHORITY` must NOT include `https://` — `App.js` prepends it automatically. Use bare domain: `cognito-idp.<region>.amazonaws.com/<pool-id>`
- All env vars are stored on the Amplify branch (not app level) — fetch with `aws amplify get-branch --app-id <APP_ID> --branch-name main --query 'branch.environmentVariables'`

### Frontend Design
- Palette matches CUNY AI Lab website (ailab.gc.cuny.edu): navy `#1D3A83`, vibrant blue `#3B73E6`, teal `#2FB8D6`, cream `#FAFCF8`
- Fonts: Outfit (headings) + Inter (body) — loaded via Google Fonts in `public/index.html`
- Theme defined in `src/theme.jsx`, color constants in `src/utilities/constants.jsx`

### Frontend Components
- **ProcessingContainer**: Real-time progress bar that polls S3 every 10s for actual pipeline artifacts (chunks, tagged files, merged output). Shows percentage, current stage name, and per-chunk progress (e.g. "3 of 5 chunks tagged"). Uses `HeadObject` probing on individual chunk keys (not `ListObjectsV2`) because the Cognito authenticated role lacks `s3:ListBucket`.
- **ResultsContainer**: "View Report" opens AccessibilityChecker dialog; "Download Report" downloads post-remediation JSON directly via presigned URL; "Download PDF" downloads the remediated file.
- **LeftNav**: Sidebar with dynamic limits from Cognito custom attributes (`maxFilesAllowed`, `maxPagesAllowed`, `maxSizeAllowedMB` passed from MainApp). Zero-retention privacy note.
- **UploadSection**: Supports drag-and-drop (`onDragOver`/`onDrop` handlers) and click-to-browse. Validates file type, size, and page count via pdf-lib before upload.

## Infrastructure Notes

- No VPC required — all Lambdas access Bedrock, S3, and Comprehend over public endpoints
- All Docker Lambdas: 2048 MiB memory, 2048 MiB ephemeral storage, 900s timeout (except Title Generator: 1024 MiB, Pre/Post Checker: 512 MiB)
- Step Functions Map concurrency: 5 (reduced from 15 to avoid Bedrock throttling cascades)
- CloudWatch dashboard defined in `app.py` with `$filename` pattern variable for filtering
- Cognito user pool with custom attributes for per-user quotas (`custom:max_files_allowed`, etc.) — see `docs/CONFIGURING_LIMITS.md`
- A `LambdaNodejsUpgradeAspect` CDK Aspect in `app.py` auto-upgrades any CDK-generated Node.js 20.x Lambdas to 22.x (future-proofing for runtime deprecations)
- No CI/CD pipeline — deployment is manual via `./deploy.sh` (CodeBuild) or direct `cdk deploy`
- No test suite — only a stub React test exists at `pdf_ui/src/App.test.js`
