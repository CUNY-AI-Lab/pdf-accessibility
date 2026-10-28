"""
Model-agnostic Bedrock client using the Converse API.

Supports any model available through Amazon Bedrock (Claude, Nova, Llama, Mistral, etc.)
by using the unified Converse API instead of model-specific InvokeModel payloads.

Configuration via environment variables:
    BEDROCK_MODEL_ID_VISION  - Model for image analysis (default: qwen.qwen3-vl-235b-a22b)
    BEDROCK_MODEL_ID_TEXT    - Model for text-only tasks (default: openai.gpt-oss-120b-1:0)
    BEDROCK_MAX_TOKENS       - Max output tokens (default: 1000)
    BEDROCK_TEMPERATURE      - Sampling temperature (default: 0.2)
"""

import os
import time
import random
import logging
import boto3

logger = logging.getLogger(__name__)

# Defaults
DEFAULT_VISION_MODEL = "qwen.qwen3-vl-235b-a22b"
DEFAULT_TEXT_MODEL = "openai.gpt-oss-120b-1:0"
DEFAULT_MAX_TOKENS = 1000
DEFAULT_TEMPERATURE = 0.2


def _resolve_model_id(model_id, region, account_id):
    """Resolve a model ID to an inference profile ARN if it contains a prefix like 'us.'."""
    if model_id.startswith(("us.", "eu.", "ap.")):
        return f"arn:aws:bedrock:{region}:{account_id}:inference-profile/{model_id}"
    return model_id


class BedrockModelClient:
    """Model-agnostic Bedrock client using the Converse API."""

    def __init__(self, model_type="vision"):
        """
        Args:
            model_type: "vision" or "text" - determines which env var to read for model ID.
        """
        self.region = os.environ.get(
            "AWS_REGION",
            os.environ.get("AWS_DEFAULT_REGION", os.environ.get("CDK_DEFAULT_REGION", "us-east-1")),
        )
        self.max_tokens = int(os.environ.get("BEDROCK_MAX_TOKENS", DEFAULT_MAX_TOKENS))
        self.temperature = float(os.environ.get("BEDROCK_TEMPERATURE", DEFAULT_TEMPERATURE))

        if model_type == "vision":
            raw_model_id = os.environ.get("BEDROCK_MODEL_ID_VISION", DEFAULT_VISION_MODEL)
        else:
            raw_model_id = os.environ.get("BEDROCK_MODEL_ID_TEXT", DEFAULT_TEXT_MODEL)

        session = boto3.Session()
        sts = session.client("sts")
        account_id = sts.get_caller_identity()["Account"]

        self.model_id = _resolve_model_id(raw_model_id, self.region, account_id)
        self.client = session.client("bedrock-runtime", region_name=self.region)
        logger.info(f"BedrockModelClient initialized: model={self.model_id}, region={self.region}")

    def invoke_with_text(self, prompt, system_prompt=None, max_tokens=None, temperature=None):
        """Send a text-only prompt to the model."""
        messages = [{"role": "user", "content": [{"text": prompt}]}]
        return self._converse(messages, system_prompt, max_tokens, temperature)

    def invoke_with_image(self, prompt, image_bytes, image_format="png", system_prompt=None, max_tokens=None, temperature=None):
        """Send a prompt with an image to the model."""
        messages = [
            {
                "role": "user",
                "content": [
                    {"text": prompt},
                    {
                        "image": {
                            "format": image_format,
                            "source": {"bytes": image_bytes},
                        }
                    },
                ],
            }
        ]
        return self._converse(messages, system_prompt, max_tokens, temperature)

    def _converse(self, messages, system_prompt=None, max_tokens=None, temperature=None):
        """Call the Bedrock Converse API with exponential backoff retry."""
        max_tokens = max_tokens or self.max_tokens
        temperature = temperature or self.temperature

        kwargs = {
            "modelId": self.model_id,
            "messages": messages,
            "inferenceConfig": {
                "maxTokens": max_tokens,
                "temperature": temperature,
            },
        }
        if system_prompt:
            kwargs["system"] = [{"text": system_prompt}]

        last_error = None
        for attempt in range(4):
            try:
                response = self.client.converse(**kwargs)
                return response["output"]["message"]["content"][0]["text"]
            except Exception as e:
                last_error = e
                if attempt < 3:
                    delay = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(f"Bedrock call failed (attempt {attempt + 1}/4): {e}. Retrying in {delay:.1f}s")
                    time.sleep(delay)

        logger.error(f"Bedrock call failed after 4 attempts: {last_error}")
        raise last_error
