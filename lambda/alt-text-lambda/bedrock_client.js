/**
 * Model-agnostic Bedrock client using the Converse API.
 *
 * Supports any model available through Amazon Bedrock (Claude, Nova, Llama, Mistral, etc.)
 * by using the unified Converse API instead of model-specific InvokeModel payloads.
 *
 * Configuration via environment variables:
 *   BEDROCK_MODEL_ID_VISION  - Model for image analysis (default: qwen.qwen3-vl-235b-a22b)
 *   BEDROCK_MODEL_ID_TEXT    - Model for text-only tasks (default: openai.gpt-oss-120b-1:0)
 *   BEDROCK_MAX_TOKENS       - Max output tokens (default: 1000)
 *   BEDROCK_TEMPERATURE      - Sampling temperature (default: 0.2)
 */

const { BedrockRuntimeClient, ConverseCommand } = require('@aws-sdk/client-bedrock-runtime');
const { STSClient, GetCallerIdentityCommand } = require('@aws-sdk/client-sts');
const sharp = require('sharp');

const DEFAULT_VISION_MODEL = 'qwen.qwen3-vl-235b-a22b';
const DEFAULT_TEXT_MODEL = 'openai.gpt-oss-120b-1:0';
const DEFAULT_MAX_TOKENS = 1000;
const DEFAULT_TEMPERATURE = 0.2;

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

class BedrockClient {
    /**
     * @param {'vision'|'text'} modelType - Which model env var to use
     */
    constructor(modelType = 'vision') {
        this.region = process.env.AWS_REGION || process.env.AWS_DEFAULT_REGION || process.env.CDK_DEFAULT_REGION || 'us-east-1';
        this.maxTokens = parseInt(process.env.BEDROCK_MAX_TOKENS || DEFAULT_MAX_TOKENS, 10);
        this.temperature = parseFloat(process.env.BEDROCK_TEMPERATURE || DEFAULT_TEMPERATURE);
        this.modelType = modelType;
        this.rawModelId = modelType === 'vision'
            ? (process.env.BEDROCK_MODEL_ID_VISION || DEFAULT_VISION_MODEL)
            : (process.env.BEDROCK_MODEL_ID_TEXT || DEFAULT_TEXT_MODEL);
        this.client = new BedrockRuntimeClient({ region: this.region });
        this._resolvedModelId = null;
    }

    async _getModelId() {
        if (this._resolvedModelId) return this._resolvedModelId;

        if (this.rawModelId.match(/^(us|eu|ap)\./)) {
            const stsClient = new STSClient({ region: this.region });
            const identity = await stsClient.send(new GetCallerIdentityCommand({}));
            this._resolvedModelId = `arn:aws:bedrock:${this.region}:${identity.Account}:inference-profile/${this.rawModelId}`;
        } else {
            this._resolvedModelId = this.rawModelId;
        }
        return this._resolvedModelId;
    }

    async invokeWithText(prompt, options = {}) {
        const messages = [{ role: 'user', content: [{ text: prompt }] }];
        return this._converse(messages, options);
    }

    async invokeWithImage(prompt, imageBuffer, options = {}) {
        let format = options.imageFormat || 'png';
        let buffer = imageBuffer;

        const MAX_IMAGE_BYTES = 1_000_000;
        if (buffer.length > MAX_IMAGE_BYTES) {
            console.warn(`Image size ${buffer.length} bytes exceeds ${MAX_IMAGE_BYTES}, resizing...`);
            let quality = 80;
            let scale = 0.75;
            for (let i = 0; i < 4; i++) {
                const metadata = await sharp(imageBuffer).metadata();
                const newWidth = Math.round(metadata.width * scale);
                buffer = await sharp(imageBuffer)
                    .resize(newWidth)
                    .jpeg({ quality })
                    .toBuffer();
                format = 'jpeg';
                if (buffer.length <= MAX_IMAGE_BYTES) break;
                scale *= 0.7;
                quality = Math.max(40, quality - 10);
            }
            console.log(`Resized image to ${buffer.length} bytes`);
        }

        const messages = [
            {
                role: 'user',
                content: [
                    { text: prompt },
                    {
                        image: {
                            format,
                            source: { bytes: buffer },
                        },
                    },
                ],
            },
        ];
        return this._converse(messages, options);
    }

    async _converse(messages, options = {}) {
        const modelId = await this._getModelId();
        const maxTokens = options.maxTokens || this.maxTokens;
        const temperature = options.temperature || this.temperature;

        const params = {
            modelId,
            messages,
            inferenceConfig: {
                maxTokens,
                temperature,
            },
        };

        if (options.systemPrompt) {
            params.system = [{ text: options.systemPrompt }];
        }

        let lastError;
        for (let attempt = 0; attempt < 4; attempt++) {
            try {
                const response = await this.client.send(new ConverseCommand(params));
                return response.output.message.content[0].text;
            } catch (error) {
                lastError = error;
                const isThrottling = error.name === 'ThrottlingException' ||
                    error.name === 'TooManyRequestsException' ||
                    error.$metadata?.httpStatusCode === 429;
                if (attempt < 3) {
                    // Longer backoff for throttling: 3s, 9s, 27s
                    const baseDelay = isThrottling ? 3000 : 1000;
                    const delay = Math.pow(3, attempt) * baseDelay + Math.random() * 1000;
                    console.warn(`Bedrock call failed (attempt ${attempt + 1}/4): ${error.message}. Retrying in ${(delay / 1000).toFixed(1)}s`);
                    await sleep(delay);
                }
            }
        }
        throw lastError;
    }
}

module.exports = { BedrockClient };
