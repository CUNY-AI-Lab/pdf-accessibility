import aws_cdk as cdk
from aws_cdk import (
    Duration,
    Size,
    Stack,
    aws_lambda as lambda_,
    aws_s3 as s3,
    aws_s3_notifications as s3n,
    aws_s3_deployment as s3deploy,
    aws_iam as iam,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
    aws_logs as logs,
    aws_cloudwatch as cloudwatch,
)
from constructs import Construct
import platform
import datetime

class PDFAccessibility(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Model configuration from CDK context (with defaults)
        bedrock_vision_model = self.node.try_get_context("bedrock_vision_model") or "qwen.qwen3-vl-235b-a22b"
        bedrock_text_model = self.node.try_get_context("bedrock_text_model") or "openai.gpt-oss-120b-1:0"

        # S3 Bucket
        pdf_processing_bucket = s3.Bucket(self, "pdfaccessibilitybucket1",
                          encryption=s3.BucketEncryption.S3_MANAGED,
                          enforce_ssl=True,
                          versioned=True,
                          removal_policy=cdk.RemovalPolicy.RETAIN)

        # Get account and region for use throughout the stack
        account_id = Stack.of(self).account
        region = Stack.of(self).region

        # Detect host architecture for Docker image builds
        host_machine = platform.machine().lower()
        print("Architecture of Machine:", host_machine)
        if "arm" in host_machine:
            lambda_arch = lambda_.Architecture.ARM_64
        else:
            lambda_arch = lambda_.Architecture.X86_64

        # --- AI Tagger Lambda (replaces ECS Fargate task) ---
        ai_tagger_lambda = lambda_.DockerImageFunction(
            self, "AiTaggerLambda",
            code=lambda_.DockerImageCode.from_image_asset('lambda/ai-tagger-lambda'),
            timeout=Duration.seconds(900),
            memory_size=2048,
            ephemeral_storage_size=Size.mebibytes(2048),
            architecture=lambda_arch,
            environment={
                'BEDROCK_MODEL_ID_VISION': bedrock_vision_model,
                'BEDROCK_MODEL_ID_TEXT': bedrock_text_model,
            },
        )

        pdf_processing_bucket.grant_read_write(ai_tagger_lambda)

        # Bedrock permissions (Converse API)
        ai_tagger_lambda.add_to_role_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel", "bedrock:Converse"],
            resources=["*"],
        ))

        # STS for model ARN resolution
        ai_tagger_lambda.add_to_role_policy(iam.PolicyStatement(
            actions=["sts:GetCallerIdentity"],
            resources=["*"],
        ))

        # Comprehend for language detection
        ai_tagger_lambda.add_to_role_policy(iam.PolicyStatement(
            actions=["comprehend:DetectDominantLanguage"],
            resources=["*"],
        ))

        # CloudWatch metrics
        cloudwatch_metrics_policy = iam.PolicyStatement(
            actions=["cloudwatch:PutMetricData"],
            resources=["*"],
        )
        ai_tagger_lambda.add_to_role_policy(cloudwatch_metrics_policy)

        # --- Alt-Text Generator Lambda (replaces ECS Fargate task) ---
        alt_text_lambda = lambda_.DockerImageFunction(
            self, "AltTextLambda",
            code=lambda_.DockerImageCode.from_image_asset('lambda/alt-text-lambda'),
            timeout=Duration.seconds(900),
            memory_size=2048,
            ephemeral_storage_size=Size.mebibytes(2048),
            architecture=lambda_arch,
            environment={
                'BEDROCK_MODEL_ID_VISION': bedrock_vision_model,
                'BEDROCK_MODEL_ID_TEXT': bedrock_text_model,
            },
        )

        pdf_processing_bucket.grant_read_write(alt_text_lambda)

        alt_text_lambda.add_to_role_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel", "bedrock:Converse"],
            resources=["*"],
        ))

        alt_text_lambda.add_to_role_policy(iam.PolicyStatement(
            actions=["sts:GetCallerIdentity"],
            resources=["*"],
        ))

        alt_text_lambda.add_to_role_policy(cloudwatch_metrics_policy)

        # --- Step Functions tasks for AI Tagger and Alt-Text (Lambda) ---
        ai_tagger_task = tasks.LambdaInvoke(
            self, "RunAiTaggerTask",
            lambda_function=ai_tagger_lambda,
            payload=sfn.TaskInput.from_object({
                "s3_bucket.$": "$.s3_bucket",
                "s3_key.$": "$.s3_key",
                "chunk_key.$": "$.chunk_key",
            }),
            result_path="$.ai_tagger_result",
        )

        alt_text_generation_task = tasks.LambdaInvoke(
            self, "RunAltTextGenerationTask",
            lambda_function=alt_text_lambda,
            payload=sfn.TaskInput.from_object({
                "s3_bucket.$": "$.s3_bucket",
                "s3_key.$": "$.s3_key",
            }),
            result_path="$.alt_text_result",
        )

        # Step Function Map State - reduced concurrency to avoid Bedrock rate limiting
        pdf_chunks_map_state = sfn.Map(self, "ProcessPdfChunksInParallel",
                            max_concurrency=15,
                            items_path=sfn.JsonPath.string_at("$.chunks"),
                            result_path="$.MapResults")

        pdf_chunks_map_state.iterator(ai_tagger_task.next(alt_text_generation_task))

        pdf_merger_lambda = lambda_.DockerImageFunction(
            self, 'PdfMergerLambda',
            code=lambda_.DockerImageCode.from_image_asset('lambda/pdf-merger-lambda-python'),
            timeout=Duration.seconds(900),
            memory_size=2048,
            ephemeral_storage_size=Size.mebibytes(2048),
            architecture=lambda_arch,
            environment={
                'BUCKET_NAME': pdf_processing_bucket.bucket_name
            },
        )

        pdf_merger_lambda.add_to_role_policy(cloudwatch_metrics_policy)
        pdf_merger_lambda_task = tasks.LambdaInvoke(self, "MergePdfChunks",
                                      lambda_function=pdf_merger_lambda,
                                      payload=sfn.TaskInput.from_object({
        "fileNames.$": "$.chunks[*].s3_key"
                     }),
                                      output_path=sfn.JsonPath.string_at("$.Payload"))
        pdf_processing_bucket.grant_read_write(pdf_merger_lambda)

        title_generator_lambda = lambda_.DockerImageFunction(
            self, 'BedrockTitleGeneratorLambda',
            code=lambda_.DockerImageCode.from_image_asset('lambda/title-generator-lambda'),
            timeout=Duration.seconds(900),
            memory_size=1024,
            architecture=lambda_arch,
            environment={
                'BEDROCK_MODEL_ID_VISION': bedrock_vision_model,
                'BEDROCK_MODEL_ID_TEXT': bedrock_text_model,
            },
        )

        # Grant the Lambda function read/write permissions to the S3 bucket
        pdf_processing_bucket.grant_read_write(title_generator_lambda)

        # Define the task to invoke the Add Title Lambda function
        title_generator_lambda_task = tasks.LambdaInvoke(
            self, "GenerateAccessibleTitle",
            lambda_function=title_generator_lambda,
            payload=sfn.TaskInput.from_object({
                "Payload.$": "$"
            })
        )

        # Add the necessary policy to the Lambda function's role
        title_generator_lambda.add_to_role_policy(cloudwatch_metrics_policy)

        # Bedrock permissions for title generation models (Converse API)
        title_generator_lambda.add_to_role_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel", "bedrock:Converse"],
            resources=["*"],
        ))

        # STS for model ARN resolution
        title_generator_lambda.add_to_role_policy(iam.PolicyStatement(
            actions=["sts:GetCallerIdentity"],
            resources=["*"],
        ))

        pre_remediation_accessibility_checker = lambda_.DockerImageFunction(
            self,'PreRemediationAccessibilityAuditor',
            code=lambda_.DockerImageCode.from_image_asset('lambda/pre-remediation-accessibility-checker'),
            timeout=Duration.seconds(900),
            memory_size=512,
            architecture=lambda_arch,
        )

        pdf_processing_bucket.grant_read_write(pre_remediation_accessibility_checker)
        pre_remediation_accessibility_checker.add_to_role_policy(cloudwatch_metrics_policy)

        pre_remediation_accessibility_checker_task = tasks.LambdaInvoke(
            self,
            "AuditPreRemediationAccessibility",
            lambda_function=pre_remediation_accessibility_checker,
            payload=sfn.TaskInput.from_json_path_at("$"),
            output_path="$.Payload"
        )

        post_remediation_accessibility_checker = lambda_.DockerImageFunction(
            self,'PostRemediationAccessibilityAuditor',
            code=lambda_.DockerImageCode.from_image_asset('lambda/post-remediation-accessibility-checker'),
            timeout=Duration.seconds(900),
            memory_size=512,
            architecture=lambda_arch,
        )

        pdf_processing_bucket.grant_read_write(post_remediation_accessibility_checker)
        post_remediation_accessibility_checker.add_to_role_policy(cloudwatch_metrics_policy)

        post_remediation_accessibility_checker_task = tasks.LambdaInvoke(
            self,
            "AuditPostRemediationAccessibility",
            lambda_function=post_remediation_accessibility_checker,
            payload=sfn.TaskInput.from_json_path_at("$"),
            output_path="$.Payload"
        )

        remediation_chain = pdf_chunks_map_state.next(pdf_merger_lambda_task).next(title_generator_lambda_task).next(post_remediation_accessibility_checker_task)

        parallel_accessibility_workflow = sfn.Parallel(self, "ParallelAccessibilityWorkflow",
                                      result_path="$.ParallelResults")
        parallel_accessibility_workflow.branch(remediation_chain)
        parallel_accessibility_workflow.branch(pre_remediation_accessibility_checker_task)

        pdf_remediation_workflow_log_group = logs.LogGroup(self, "PdfRemediationWorkflowLogs",
            log_group_name="/aws/states/pdf-accessibility-remediation-workflow",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=cdk.RemovalPolicy.DESTROY
        )

        # State Machine
        pdf_remediation_state_machine = sfn.StateMachine(self, "PdfAccessibilityRemediationWorkflow",
                                         definition=parallel_accessibility_workflow,
                                         timeout=Duration.minutes(150),
                                         logs=sfn.LogOptions(
                                             destination=pdf_remediation_workflow_log_group,
                                             level=sfn.LogLevel.ALL
                                         ))

        # Lambda Function
        pdf_splitter_lambda = lambda_.Function(
            self, 'PdfChunkSplitterLambda',
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler='main.lambda_handler',
            code=lambda_.Code.from_docker_build("lambda/pdf-splitter-lambda"),
            timeout=Duration.seconds(900),
            memory_size=1024
        )

        pdf_splitter_lambda.add_to_role_policy(cloudwatch_metrics_policy)

        # S3 Permissions for Lambda
        pdf_processing_bucket.grant_read_write(pdf_splitter_lambda)

        # Trigger Lambda on S3 Event
        pdf_processing_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(pdf_splitter_lambda),
            s3.NotificationKeyFilter(prefix="pdf/"),
            s3.NotificationKeyFilter(suffix=".pdf")
        )

        # Step Function Execution Permissions
        pdf_remediation_state_machine.grant_start_execution(pdf_splitter_lambda)

        # Pass State Machine ARN to Lambda as an Environment Variable
        pdf_splitter_lambda.add_environment("STATE_MACHINE_ARN", pdf_remediation_state_machine.state_machine_arn)

        # Store log group names dynamically for CloudWatch dashboard
        pdf_splitter_lambda_log_group_name = f"/aws/lambda/{pdf_splitter_lambda.function_name}"
        pdf_merger_lambda_log_group_name = f"/aws/lambda/{pdf_merger_lambda.function_name}"
        title_generator_lambda_log_group_name = f"/aws/lambda/{title_generator_lambda.function_name}"
        ai_tagger_lambda_log_group_name = f"/aws/lambda/{ai_tagger_lambda.function_name}"
        alt_text_lambda_log_group_name = f"/aws/lambda/{alt_text_lambda.function_name}"
        pre_remediation_checker_log_group_name = f"/aws/lambda/{pre_remediation_accessibility_checker.function_name}"
        post_remediation_checker_log_group_name = f"aws/lambda/{post_remediation_accessibility_checker.function_name}"

        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        dashboard_name = f"PDF_Processing_Dashboard-{timestamp}"
        dashboard = cloudwatch.Dashboard(self, "PdfRemediationMonitoringDashboard", dashboard_name=dashboard_name,
                                         variables=[cloudwatch.DashboardVariable(
                                            id="filename",
                                            type=cloudwatch.VariableType.PATTERN,
                                            label="File Name",
                                            input_type=cloudwatch.VariableInputType.INPUT,
                                            value="filename",
                                            visible=True,
                                            default_value=cloudwatch.DefaultValue.value(".*"),
                                        )]
                                         )
        # Add Widgets to the Dashboard
        dashboard.add_widgets(
            cloudwatch.LogQueryWidget(
                title="File status",
                log_group_names=[pdf_splitter_lambda_log_group_name, pdf_merger_lambda_log_group_name, ai_tagger_lambda_log_group_name, alt_text_lambda_log_group_name],
                query_string='''fields @timestamp, @message
                    | parse @message "File: *, Status: *" as file, status
                    | stats latest(status) as latestStatus by file
                    | sort file asc ''',
                width=24,
                height=6
            ),
            cloudwatch.LogQueryWidget(
                title="Split PDF Lambda Logs",
                log_group_names=[pdf_splitter_lambda_log_group_name],
                query_string='''fields @message
                                | filter @message like /filename/''',
                width=24,
                height=6
            ),
            cloudwatch.LogQueryWidget(
                title="Step Function Execution Logs",
                log_group_names=[pdf_remediation_workflow_log_group.log_group_name],
                query_string='''fields @message
                                | filter @message like /filename/''',
                width=24,
                height=6
            ),
            cloudwatch.LogQueryWidget(
                title="AI Tagger Processing Logs",
                log_group_names=[ai_tagger_lambda_log_group_name],
                query_string='''fields @message
                                | filter @message like /filename/''',
                width=24,
                height=6
            ),
            cloudwatch.LogQueryWidget(
                title="Alt Text Generation Logs",
                log_group_names=[alt_text_lambda_log_group_name],
                query_string='''fields @message
                                | filter @message like /filename/''',
                width=24,
                height=6
            ),
            cloudwatch.LogQueryWidget(
                title="PDF Merger Lambda Logs",
                log_group_names=[pdf_merger_lambda_log_group_name],
                query_string='''fields @message
                                | filter @message like /filename/''',
                width=24,
                height=6
            ),
        )

app = cdk.App()
PDFAccessibility(app, "PDFAccessibility")
app.synth()
