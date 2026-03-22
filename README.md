# PDF Accessibility Solutions

This repository provides two complementary solutions for PDF accessibility:

1. **PDF-to-PDF Remediation**: Processes PDFs and maintains the PDF format while improving accessibility using AI-powered tagging.
2. **PDF-to-HTML Remediation**: Converts PDFs to accessible HTML format using AWS Bedrock Data Automation.

Both solutions leverage AWS services and generative AI to improve content accessibility according to WCAG 2.1 Level AA standards.

## Table of Contents

| Index | Description |
|---|---|
| [Architecture Overview](#architecture-overview) | High level overview illustrating component interactions |
| [Deployment](#deployment) | How to deploy the project |
| [Testing Your Solution](#testing-your-pdf-accessibility-solution) | User guide for the working solution |
| [PDF-to-PDF Solution](#pdf-to-pdf-remediation-solution) | PDF format preservation solution details |
| [PDF-to-HTML Solution](#pdf-to-html-remediation-solution) | HTML conversion solution details |
| [Frontend](#frontend) | React web application |
| [Configuring Limits](docs/CONFIGURING_LIMITS.md) | How to modify document limits, quotas, and defaults |
| [Monitoring](#monitoring) | System monitoring and observability |
| [Troubleshooting](#troubleshooting) | Common issues and solutions |
| [Contributing](#contributing) | How to contribute to the project |

## Architecture Overview

### PDF-to-PDF Pipeline

```
                                    ┌─────────────────────────────────────────────────────────┐
                                    │                   Step Functions                        │
                                    │                                                         │
                                    │  ┌───────────────────────────────────────────────────┐  │
                                    │  │              Map State (per chunk)                 │  │
 ┌──────────┐    ┌──────────────┐   │  │  ┌─────────────┐    ┌──────────────────────────┐  │  │
 │  User     │    │ PDF Splitter │   │  │  │  AI Tagger  │───▶│  Alt-Text Generator      │  │  │
 │  uploads  │───▶│   Lambda     │──▶│  │  │  (Bedrock   │    │  (Bedrock vision + text) │  │  │
 │  to S3    │    │ (5-pg chunks)│   │  │  │   vision)   │    │                          │  │  │
 │  pdf/     │    └──────────────┘   │  │  └─────────────┘    └──────────────────────────┘  │  │
 └──────────┘                       │  └───────────────────────────────────────────────────┘  │
                                    │         │                                               │
                                    │         ▼                                               │
                                    │  ┌─────────────┐  ┌─────────────┐  ┌───────────────┐   │
                                    │  │ PDF Merger   │─▶│   Title     │─▶│  Post-Check   │   │
                                    │  │ (pikepdf)    │  │  Generator  │  │  (27 checks)  │   │
                                    │  └─────────────┘  └─────────────┘  └───────────────┘   │
                                    │                                                         │
                                    │  ┌───────────────────────────────────────────────────┐  │
                                    │  │  Pre-Check (audits original PDF — runs parallel)  │  │
                                    │  └───────────────────────────────────────────────────┘  │
                                    └─────────────────────────────────────────────────────────┘
                                                                              │
                                                                              ▼
                                                                    ┌─────────────────┐
                                                                    │  result/ in S3   │
                                                                    │  COMPLIANT_*.pdf │
                                                                    └─────────────────┘
```

All processing is serverless using AWS Lambda (Docker containers). AI-powered tagging and alt-text generation use Amazon Bedrock vision and text models via the Converse API. A CloudWatch dashboard provides per-file monitoring.

### Key Components

| Component | Path | Language | Runtime |
|---|---|---|---|
| CDK Stack | `app.py` | Python | CDK |
| AI Tagger | `lambda/ai-tagger-lambda/` | Python | Docker Lambda |
| Alt-Text Generator | `lambda/alt-text-lambda/` | Node.js | Docker Lambda |
| PDF Splitter | `lambda/pdf-splitter-lambda/` | Python | Zip Lambda |
| PDF Merger | `lambda/pdf-merger-lambda-python/` | Python | Docker Lambda |
| Title Generator | `lambda/title-generator-lambda/` | Python | Docker Lambda |
| Pre/Post Checker | `lambda/{pre,post}-remediation-accessibility-checker/` | Python | Docker Lambda |
| Frontend | `pdf_ui/` | React 19 | AWS Amplify |

## Deployment

### Prerequisites

1. **AWS Account** with permissions to create Lambda, S3, Step Functions, Bedrock, Cognito, and CloudWatch resources
2. **AWS CLI** configured with appropriate credentials
3. **Docker** installed and running (required for building Lambda container images)
4. **Node.js 22+** and **Python 3.12+**
5. **AWS CDK** installed (`npm install -g aws-cdk`)
6. **Bedrock model access** granted for your chosen vision and text models

### CDK Deployment (PDF-to-PDF)

```bash
git clone https://github.com/CUNY-AI-Lab/pdf-accessibility.git
cd pdf-accessibility
pip install -r requirements.txt
cdk synth
cdk deploy PDFAccessibility \
  -c bedrock_vision_model=qwen.qwen3-vl-235b-a22b \
  -c bedrock_text_model=openai.gpt-oss-120b-1:0
```

The vision and text models are configurable via CDK context. Any model available through Bedrock's Converse API can be used. Cross-region inference profile IDs (e.g. `us.qwen.*`) are resolved to full ARNs automatically.

### Automated Deployment

```bash
chmod +x deploy.sh
./deploy.sh
```

The script guides you through solution selection, model configuration, and deployment via CodeBuild.

### PDF-to-HTML Deployment (TypeScript CDK)

```bash
cd pdf2html/cdk && npm install && npx cdk deploy
```

## Testing Your PDF Accessibility Solution

### PDF-to-PDF Solution Testing

1. **Upload**: In the S3 bucket (starting with `pdfaccessibility-`), upload PDF files to the `pdf/` folder. Processing triggers automatically.
2. **Monitor**: Watch the CloudWatch dashboard or Step Functions console. The `temp/` folder contains intermediate files.
3. **Results**: Remediated PDFs appear in the `result/` folder with a `COMPLIANT_` prefix.

### PDF-to-HTML Solution Testing

1. **Upload**: In the S3 bucket (starting with `pdf2html-bucket-`), upload PDF files to the `uploads/` folder.
2. **Results**: Download `final_{filename}.zip` from the `remediated/` folder, containing:
   - `remediated.html` — Accessible HTML version
   - `images/` — Extracted images with generated alt text
   - `remediation_report.html` — Detailed accessibility improvements report

## PDF-to-PDF Remediation Solution

### How It Works

1. **PDF Splitter** splits uploaded PDFs into 5-page chunks
2. **AI Tagger** analyzes each chunk with a Bedrock vision model to build a PDF/UA structure tree (headings, paragraphs, lists, tables, figures)
3. **Alt-Text Generator** generates WCAG-compliant alt text for all images and links using Bedrock models, with throttle protection and exponential backoff
4. **PDF Merger** reassembles chunks, preserving structure trees, MCIDs, and page references
5. **Title Generator** adds an accessible document title using a Bedrock text model
6. **Accessibility Checker** runs 27 automated PDF/UA + WCAG checks (color contrast, reading order, heading nesting, figure alt text, table headers, etc.)

### Accessibility Checker

The checker (`pdf_accessibility_checker.py`) runs automated checks across these categories:

- **Document**: MarkInfo, StructTreeRoot, Lang, Title, PDF/UA ID, Font Embedding, Unicode Mapping, Artifact Marking
- **Navigation**: Tab Order, Outlines, Reading Order, Annotation Tagging
- **Structure**: Heading Nesting, Figure Alt Text, Table Headers/Scope, List Structure, Language of Parts
- **Links**: Alt Text, Meaningful Text (detects generic text like "click here")
- **Forms**: Field Labels
- **Visual**: Color Contrast (automated via WCAG luminance formula — 4.5:1 normal, 3:1 large text)

## PDF-to-HTML Remediation Solution

Converts PDF documents to accessible HTML using AWS Bedrock Data Automation for PDF parsing. Deployed as a separate TypeScript CDK stack with a single Lambda function.

## Frontend

The React 19 + MUI 6 web application (`pdf_ui/`) provides:

- Drag-and-drop PDF upload with file validation (type, size, page count)
- Real-time processing progress that polls S3 for pipeline artifacts
- Side-by-side before/after accessibility reports
- Download for remediated PDFs and accessibility reports
- OIDC authentication via Amazon Cognito

### Running Locally

```bash
cd pdf_ui
npm install
npm start
```

Requires environment variables in `pdf_ui/.env` — see `src/utilities/constants.jsx` for the full list.

### Deploying to Amplify

```bash
cd pdf_ui && npm run build
cd build && zip -r ../deploy.zip .
aws amplify create-deployment --app-id <APP_ID> --branch-name main
# Upload zip to presigned URL, then start deployment
```

## Monitoring

- **CloudWatch Dashboard**: Auto-created during deployment with per-file filtering
- **Step Functions Console**: Monitor workflow executions and individual task status
- **Lambda Logs**: Each Lambda writes to its own CloudWatch log group

### Verifying Pipeline After Deploy

```bash
# Check latest Step Functions execution
aws stepfunctions list-executions \
  --state-machine-arn "$(aws stepfunctions list-state-machines \
    --query 'stateMachines[?contains(name,`PdfAccessibility`)].stateMachineArn' \
    --output text)" \
  --max-results 3 --query 'executions[*].[status,startDate]' --output table

# Check Lambda logs
aws logs tail "/aws/lambda/<FUNCTION_NAME>" --since 30m
```

## Troubleshooting

### Common Issues

**Bedrock Throttling**: The pipeline uses exponential backoff and concurrency limits to handle Bedrock rate limiting. If processing stalls, check CloudWatch logs for throttling errors. Map state concurrency is set to 5 to avoid overwhelming Bedrock.

**Docker Build Failures**: Ensure Docker Desktop is running before `cdk deploy`. Lambda containers require Docker for image builds.

**Service Limits**: Check [AWS service quotas](https://us-east-1.console.aws.amazon.com/servicequotas/) if deployment fails.

**CDK Deploy Issues**: See [CDK troubleshooting guide](docs/TROUBLESHOOTING_CDK_DEPLOY.md) and [CDK GitHub Issue #30258](https://github.com/aws/aws-cdk/issues/30258).

## Contributing

Contributions to this project are welcome. Please fork the repository and submit a pull request with your changes.

## Acknowledgments

- Originally developed by Arizona State University's AI Cloud Innovation Center (AI CIC), powered by AWS.
- The PDF-to-HTML remediation functionality is adapted from AWS Labs' [Content Accessibility Utility on AWS](https://github.com/awslabs/content-accessibility-utility-on-aws).

---

**Maintained by [CUNY AI Lab](https://ailab.gc.cuny.edu)**
