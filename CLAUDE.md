# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PDF Accessibility Solutions: an AWS-based tool that remediates PDFs for WCAG 2.1 Level AA compliance. Two approaches exist side-by-side:

- **PDF-to-PDF** (`app.py`): Step Functions pipeline using ECS Fargate + Lambda. AI-powered tagging via Bedrock vision models replaces the original Adobe API dependency.
- **PDF-to-HTML** (`pdf2html/`): Single Lambda using Bedrock Data Automation. Separate TypeScript CDK stack.
- **Frontend** (`pdf_ui/`): React 19 + MUI 6 app deployed to AWS Amplify. Uses OIDC auth with Cognito.

## Build & Deploy Commands

### CDK Backend (PDF-to-PDF)
```bash
# Install CDK deps
pip install -r requirements.txt

# Synth/deploy with model selection
cdk synth
cdk deploy PDFAccessibility \
  -c bedrock_vision_model=qwen.qwen3-vl-235b-a22b \
  -c bedrock_text_model=qwen.qwen3-32b-v1:0
```

### Frontend (React)
```bash
cd pdf_ui
npm install
npm start          # Dev server
npm run build      # Production build (requires REACT_APP_* env vars)
npm test           # Tests
```

Required env vars for frontend build: `REACT_APP_AUTHORITY`, `REACT_APP_AWS_REGION`, `REACT_APP_PDF_BUCKET_NAME`, `REACT_APP_HOSTED_UI_URL`, `REACT_APP_IDENTITY_POOL_ID`, `REACT_APP_USER_POOL_CLIENT_ID`, `REACT_APP_USER_POOL_ID`, `REACT_APP_DOMAIN_PREFIX`, `REACT_APP_UPDATE_FIRST_SIGN_IN`, `REACT_APP_UPLOAD_QUOTA_API`. All defined in `src/utilities/constants.jsx`.

### Automated Deployment
```bash
./deploy.sh        # Interactive: picks solution, models, deploys everything
```

### PDF-to-HTML CDK (TypeScript)
```bash
cd pdf2html/cdk
npm install
npx cdk deploy
```

## Architecture: PDF-to-PDF Pipeline

```
S3 Upload → PDF Splitter (Lambda) → Step Functions Map:
    → AI Tagger (ECS) → Alt-Text Generator (ECS)
→ PDF Merger (Lambda) → Title Generator (Lambda) → Post-Check (Lambda)
Pre-Check (Lambda) runs in parallel with Map
```

### Key Components

| Component | Path | Language | Runtime |
|---|---|---|---|
| CDK Stack | `app.py` | Python | CDK |
| AI Tagger | `ai-tagger-container/` | Python | ECS Fargate |
| Alt-Text Generator | `alt-text-generator-container/` | Node.js | ECS Fargate |
| PDF Splitter | `lambda/pdf-splitter-lambda/` | Python | Lambda (zip) |
| PDF Merger | `lambda/pdf-merger-lambda/` | Java | Lambda (zip) |
| Title Generator | `lambda/title-generator-lambda/` | Python | Lambda (Docker) |
| Pre/Post Checker | `lambda/pre-remediation-accessibility-checker/` | Python | Lambda (Docker) |
| Shared Checker Logic | `lambda/accessibility-checker-common/` | Python | Shared lib |
| Bedrock Client (Python) | `ai-tagger-container/lib/bedrock_model_client.py` | Python | Shared |
| Bedrock Client (Node) | `alt-text-generator-container/bedrock_client.js` | Node.js | Shared |

### Model Abstraction

All Bedrock calls use the **Converse API** (not InvokeModel) for model-agnostic support. Configured via env vars `BEDROCK_MODEL_ID_VISION` and `BEDROCK_MODEL_ID_TEXT`. Defaults to Qwen3 VL 235B (vision) and Qwen3 32B (text). Cross-region inference profile IDs (e.g. `us.qwen.*`) are resolved to full ARNs at runtime using STS.

### Accessibility Checker

`pdf_accessibility_checker.py` implements 13 PDF/UA + WCAG checks using pikepdf (structure tree) and PyMuPDF (content). Output format must match the UI schema: `{Summary: {Description, Passed, Failed, "Needs manual check"}, "Detailed Report": {Category: [{Rule, Description, Status}]}}`.

## Important Patterns & Gotchas

### pikepdf
- `pikepdf.Dictionary()` constructor does NOT accept `pikepdf.Name` as dict keys. Set attributes individually: `d["/Key"] = value`
- `pikepdf.Name()` requires leading `/`: use `pikepdf.Name("/H1")` not `pikepdf.Name("H1")`

### Lambda Packaging
- Lambdas using native C libraries (pikepdf, PyMuPDF) must be `DockerImageFunction` with `DockerImageCode.from_image_asset()`, not zip packages via `Code.from_docker_build()`
- The Dockerfiles install system deps: `dnf install -y qpdf-libs qpdf-devel gcc python3-devel`

### Step Functions State
- ECS RunTask results replace state unless `result_path` is set (e.g., `result_path="$.ai_tagger_result"`)
- Alt-text container reads `$.s3_bucket` and `$.s3_key` from the original input state

### Bedrock Limits
- Qwen models have ~1MB image payload limit. Images are resized via `sharp` (Node) before sending.
- Context text truncated to 4000 chars to avoid payload limits.

### PyMuPDF TOC
- `doc.set_toc()` requires first entry at level 1 with no jumps > 1 between consecutive entries. Normalize heading levels before calling.

### Frontend Deployment
- Amplify manual deploy: zip must contain files at root, not inside a `build/` subdirectory
- `cd build && zip -r ../deploy.zip .`

## Infrastructure Notes

- VPC with public/private subnets, NAT gateway, VPC endpoints (ECR, S3) for Fargate
- ECS tasks: AI Tagger (512 CPU / 2048 MiB), Alt-Text (256 CPU / 1024 MiB)
- Step Functions Map concurrency configurable (default 100, reduce for rate limiting)
- CloudWatch dashboard defined in `app.py` for monitoring
- Cognito user pool with custom attributes for per-user quotas (`custom:max_files_allowed`, etc.)
