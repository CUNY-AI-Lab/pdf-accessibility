# Cost Estimate: PDF Accessibility Tool on AWS

## Monthly Fixed Infrastructure (~$130/mo)

| Service | Cost/mo | Notes |
|---|---|---|
| NAT Gateways (3 AZs) | ~$97 | $0.045/hr x 3 x 720 hrs. Largest fixed cost |
| VPC Endpoints (ECR, S3) | ~$22 | $0.01/hr x 3 endpoints |
| CloudWatch Logs | ~$5 | Log storage + ingestion |
| S3 Storage | ~$2 | Minimal unless storing thousands of PDFs |
| Cognito | Free | Free tier covers 50,000 MAUs |
| API Gateway | ~$1 | Pay per request |
| Amplify Hosting | Free | Free tier covers most usage |
| Step Functions | ~$1 | $0.025 per 1,000 state transitions |

### Cost Reduction Options
- Use 1 NAT Gateway instead of 3 → saves ~$65/mo (reduced availability)
- Use NAT instances (t3.nano) instead → ~$10/mo total
- Remove VPC endpoints and route through NAT → saves $22/mo but increases NAT data costs

## Per-Page Conversion Cost (~$0.007/page)

| Step | Cost/page | Details |
|---|---|---|
| Bedrock Vision (AI Tagger) | ~$0.003 | Page image + text → structure classification |
| Bedrock Vision (Alt-Text) | ~$0.002 | Per image, ~1 image/page average |
| Bedrock Text (Title Gen) | ~$0.0005 | One call per document, amortized |
| ECS Fargate (AI Tagger) | ~$0.001 | ~60s per page at 0.5 vCPU / 2GB |
| ECS Fargate (Alt-Text) | ~$0.0005 | ~30s per page at 0.25 vCPU / 1GB |
| Lambda (Splitter/Merger/Checkers) | <$0.001 | Negligible |

### Example: 100-page document
- Bedrock tokens: ~$0.55
- ECS compute: ~$0.15
- **Total: ~$0.70**

### Example: 1,000 documents/month (avg 10 pages each)
- Fixed infra: $130
- Conversion (10,000 pages): ~$70
- **Total: ~$200/mo ($0.02/page all-in)**

## Model Costs (Bedrock pricing, us-east-1)

| Model | Input | Output | Used for |
|---|---|---|---|
| Qwen3 VL 235B | $0.00075/1K tokens | $0.00075/1K tokens | Vision (tagging, alt-text) |
| GPT-OSS 120B | $0.00036/1K tokens | $0.00036/1K tokens | Text (link alt-text) |

Switching to more expensive models (e.g., Claude Sonnet) increases per-page cost to ~$0.02-0.04/page.
