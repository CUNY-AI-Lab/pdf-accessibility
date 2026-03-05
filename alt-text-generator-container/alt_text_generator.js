/**
 * Alt-text generator for PDF accessibility remediation.
 *
 * Downloads a PDF and associated image data from S3, generates WCAG 2.1-compliant
 * alt text using a configurable Bedrock model (via Converse API), updates the PDF
 * with generated alt text, and re-uploads to S3.
 *
 * Model selection is controlled by environment variables:
 *   BEDROCK_MODEL_ID_VISION - for image alt-text (default: Claude Sonnet)
 *   BEDROCK_MODEL_ID_TEXT   - for link alt-text (default: Claude Haiku)
 */

const { S3Client, GetObjectCommand, PutObjectCommand } = require('@aws-sdk/client-s3');
const fs = require('fs').promises;
const fs_1 = require('fs');
const winston = require('winston');
const path = require('path');
const { PDFDocument, PDFName, PDFDict, PDFString } = require('pdf-lib');
const Database = require('better-sqlite3');
const stream = require('stream');
const { promisify } = require('util');
const { BedrockClient } = require('./bedrock_client');

const pipeline = promisify(stream.pipeline);

const logger = winston.createLogger({
    level: 'info',
    format: winston.format.simple(),
    transports: [new winston.transports.Console()]
});

const AWS_REGION = process.env.AWS_REGION || process.env.AWS_DEFAULT_REGION || process.env.CDK_DEFAULT_REGION;
const s3Client = new S3Client({ region: AWS_REGION });

// Initialize Bedrock clients (lazy — resolved on first call)
const visionClient = new BedrockClient('vision');
const textClient = new BedrockClient('text');

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Generate WCAG 2.1-compliant alt text for an image using the vision model.
 */
async function generateAltText(imageObject, imageBuffer) {
    logger.info(`imageObject in generate alt text function: ${imageObject.id}`);
    logger.info(`imageObject in generate alt text function: ${imageObject.context_json.context}`);

    const prompt = `Generate WCAG 2.1-compliant alt text for an image embedded in a PDF document. The output must be in strict JSON format as follows:
    {"${imageObject.id}": "Alternative text"}
    Follow these guidelines to create appropriate and effective alt text:
    1. Image Description:
       - Describe the key elements of the image, including objects, people, scenes, and any visible text.
       - Consider the image's role within the PDF. What information or function does it provide?
    2. WCAG 2.1 Compliance:
       a) Text in Image:
          - If duplicated nearby, use empty alt text: alt=""
          - For functional text (e.g., icons), describe the function
          - Otherwise, include the exact text
       b) Functional Images:
          - For links/buttons, describe the action/destination
       c) Informative Images:
          - Provide a concise description of essential information
          - For complex images, summarize key data or direct to full information
       d) Decorative Images:
          - Use empty alt text: alt=""
    3. Equation-Specific Alt Text Guidance:
        - For images containing mathematical equations, spell out every symbol, number, and operator.
        - Use explicit phrases such as "open parenthesis", "close parenthesis", "plus", "minus", "times", "divided by", "equals", "to the power of", etc.
        - **Basic Example:** Instead of "2(4y+1)=3y", write "2 open parenthesis 4 y plus 1 close parenthesis equals 3 y."
        - **Complex Example:** For an equation such as: f(t) = k1 e^(2t) sin(pi t) + k2 t^3,
            the alt text should be: "f open parenthesis t close parenthesis equals k1 e to the power of 2 t sin of pi t plus k2 t to the power of 3."
   - **Power Notation Accuracy:** Ensure that any exponentiation is represented accurately. Always check that the power formatting is preserved correctly by using the phrase "to the power of" immediately after the base value, followed by the exponent. Do not drop, alter, or misplace any exponent values.
   - **Subscript** Ensure that you properly describe subscript and superscript. For an example for equation Fi = mi a^2, you should give the alt text as "F with subscript i end subscript equals m with subscript i end subscript a to the power of 2". Another example: Fa/x = ma/x a^2, you should give the alt text as "F with subscript a divided by x end subscript equals m with subscript a divided by x end subscript a to the power of 2"
   - *Superscript*: Ensure that you properly describe the superscript. For example, Fa/x^(n+1) = mij^k + a^b, you should give the alt text as "F with subscript a divided by x end subscript with superscript n plus 1 end superscript equals m with subscript i j end subscript with superscript k end superscript plus a with superscript b end superscript"
   - **Variable Names:** Always use the exact variable names and symbols as provided in the original equation. Do not substitute or alter them.
    4. Output Guidelines:
       - Keep alt text short, clear, and relevant
       - Ensure it enhances accessibility for assistive technology users

    YOU MUST FOLLOW EACH INSTRUCTION STRICTLY:
    - <INSTRUCTION>Provide only the JSON output with no additional explanation</INSTRUCTION>
    - <INSTRUCTION>Do not use unnecessary phrases like "Certainly!" or "Here's the alt text:"</INSTRUCTION>
    - <INSTRUCTION>If you're unsure about specific details, focus on describing what you can clearly determine from the context provided</INSTRUCTION>
    - <INSTRUCTION>MAKE SURE YOU DO NOT USE IMAGE NAME OR NUMBER AS THEIR ID IN THE JSON RESPONSE [STRICTLY]</INSTRUCTION>
    - <INSTRUCTION>MAKE SURE YOU USE CONTENT TO IMPROVE THE QUALITY OF ALT TEXT AND NOT GENERATE A SUMMARY OF CONTEXT IF THE IMAGE IS EMPTY OR NOT RELEVANT</INSTRUCTION>

    <PAGE CONTENT AND CONTEXT INFORMATION>
    The page content and image of interest is provided below. This is the whole page content and wherever you see "<OTHER IMAGE>" tag, these are other images on the page. The main image is the one with the tag "<IMAGE INTERESTED>" [DO NOT USE THIS AS THE OBJECT ID IN THE JSON].
    NOW, USE THIS CONTENT TO GENERATE ALT TEXT BY FOLLOWING THE BELOW STEPS:
    - <STEP1> First determine where our image of interest is on the page </STEP1>
    - <STEP2> Determine what is the relevant text for our image of interest by considering its location in the whole page </STEP2>
    - <STEP3> If there are multiple images on the same page, determine which text is relevant for our image of interest and which is not </STEP3>
    - <STEP4> Always use the name of a person if available and ensure you DO NOT assign the wrong name to an image</STEP4>
    - <STEP5> Decide carefully which text to use, considering the image's before and after context [STRICT STEP]</STEP5>

    <IMPORTANT THING>
    In cases where there is text on both sides of our image of interest, analyze the overall page content and decide which portion to use. One method may be:
    - <STEP 1> Identify other images and the text associated with them </STEP 1>
    - <STEP 2> Assume that text associated with other images is not related to our image of interest </STEP 2>
    </IMPORTANT THING>

    <FEEDBACK>
    You tend to make mistakes when multiple images are present with small amounts of text in between. In such cases, choose the correct text for the alt text.
    *ALERT* Be careful when you are describing the subscript and superscripts in the alt text. Make sure you are describing them correctly. for subscripts you are making so many mistakes. you must first decide if this is the part of subscript or not and then go ahead.
    *ALERT* Always mention end of superscript and subscript, you are not describing end of subscript and superscript properly.
    </FEEDBACK>
    <ACTUAL CONTENT>
    ${imageObject.context_json.context.substring(0, 4000)}
    <ACTUAL CONTENT>

    Now, based on the above guidelines, generate the appropriate alt text in the required JSON format.
    `;

    const systemPrompt = "You are an intelligent assistant capable of analyzing images and answering questions about them.";
    const response = await visionClient.invokeWithImage(prompt, imageBuffer, {
        systemPrompt,
        imageFormat: 'png',
    });
    logger.info(`response of alt text: ${response}`);
    return response;
}

/**
 * Generate alt text for a hyperlink using the text model.
 */
async function generateAltTextForLink(url) {
    const prompt = `Generate WCAG 2.1-compliant alt text for a hyperlink. The alt text should describe the link's destination or purpose in a clear and concise manner. Example: "Link to YouTube video about PDF accessibility".
    The link URL is: ${url}. Follow the instructions provided to generate appropriate alt text:
    1. Just give only alt text. do not give give any other word or phrases like "Here is the alt text" or "The alt text is" etc.
    2. The alt text should be clear and concise, providing a brief description of the link's destination or purpose.`;

    const systemPrompt = "You are an intelligent assistant capable of analyzing links and answering questions about them.";
    return textClient.invokeWithText(prompt, { systemPrompt });
}

/**
 * Modify a PDF by adding alt text to images and links.
 */
async function modifyPDF(zipped, bucketName, inputKey, outputKey, filebasename) {
    const downloadPath = path.join('/tmp', path.basename(inputKey));

    try {
        const downloadParams = {
           Bucket: process.env.S3_BUCKET_NAME,
            Key: `temp/${filebasename}/output_autotag/COMPLIANT_${process.env.S3_FILE_KEY.split("/").pop()}`,
        };
        const pdfData = await s3Client.send(new GetObjectCommand(downloadParams));

        const writeStream = fs_1.createWriteStream(downloadPath);
        pdfData.Body.pipe(writeStream);

        await new Promise((resolve, reject) => {
            writeStream.on('finish', resolve);
            writeStream.on('error', reject);
        });

        const pdfBytes = fs_1.readFileSync(downloadPath);
        const pdfDoc = await PDFDocument.load(pdfBytes);

        const linkProcessingPromises = [];

        pdfDoc.context.enumerateIndirectObjects().forEach(([pdfRef, pdfObject]) => {
            if (pdfObject instanceof PDFDict) {
                const structType = pdfObject.lookup(PDFName.of('S'))?.encodedName;

                if (structType === '/Figure') {
                    Object.entries(zipped).forEach(([key, value]) => {
                        logger.info(`Filename: ${filebasename} | Key: ${key}, Value: ${value}`);
                        if (key == pdfRef.objectNumber) {
                            if (value === 'artifact') {
                                pdfObject.set(PDFName.of('S'), PDFName.of('Artifact'));
                            } else {
                                logger.info(`Filename: ${filebasename} | Adding the alt text`);
                                const newAltText = value;
                                pdfObject.set(PDFName.of('Alt'), PDFString.of(newAltText));
                                pdfObject.set(PDFName.of('Contents'), PDFString.of(newAltText));
                                delete zipped[key];
                                logger.info(`Filename: ${filebasename} | Alt text added:${newAltText}`);
                                logger.info(`Filename: ${filebasename} | Alt text  for object number:${pdfRef.objectNumber} and key ${key}`);
                            }
                        }
                    });
                }
                if (pdfObject.has(PDFName.of('Type')) && pdfObject.lookup(PDFName.of('Type')).encodedName === '/Annot') {
                    const subType = pdfObject.lookup(PDFName.of('Subtype'))?.encodedName;
                    if (subType === '/Link') {
                        const action = pdfObject.lookup(PDFName.of('A'));
                        const url = action?.lookup(PDFName.of('URI'))?.value;
                        logger.info(`Filename: ${filebasename} | URL of the link is: ${url}`);
                        if (url) {
                            console.log(`Processing URL: ${url}`);
                            const altTextPromise = generateAltTextForLink(url).then((altText) => {
                                pdfObject.set(PDFName.of('Alt'), PDFString.of(altText));
                                pdfObject.set(PDFName.of('Contents'), PDFString.of(altText));
                            });
                            linkProcessingPromises.push(altTextPromise);
                        }
                    }
                }
            }
        });
        await Promise.all(linkProcessingPromises);

        const modifiedPdfBytes = await pdfDoc.save();
        const modifiedPdfPath = path.join('/tmp', 'modified_' + path.basename(inputKey));
        fs_1.writeFileSync(modifiedPdfPath, modifiedPdfBytes);

        const uploadParams = {
            Bucket: bucketName,
            Key: `temp/${filebasename}/FINAL_${outputKey}`,
            Body: fs_1.createReadStream(modifiedPdfPath),
            ContentType: 'application/pdf'
        };
        await s3Client.send(new PutObjectCommand(uploadParams));

        logger.info(`PDF modification complete. Output saved to s3://${bucketName}/FINAL_${outputKey}`);

        fs_1.unlinkSync(downloadPath);
        fs_1.unlinkSync(modifiedPdfPath);

    } catch (err) {
        logger.error(`Filename: ${filebasename} | Error processing PDF: ${err}`);
        throw err;
    }
}

/**
 * Main process: retrieve image data, generate alt text, modify and re-upload PDF.
 */
async function startProcess() {
    const bucketName = process.env.S3_BUCKET_NAME;
    const textFileKey = `${process.env.S3_FILE_KEY.split("/")[1]}/output_autotag/${process.env.S3_FILE_KEY.split("/").pop()}_temp_images_data.db`;
    const filebasename = process.env.S3_FILE_KEY.split("/")[1];

    logger.info(`Filename: ${filebasename} | Text File Key: ${textFileKey}, Bucket Name: ${bucketName}`);
    try {
        const getObjectParams = {
            Bucket: bucketName,
            Key: `temp/${textFileKey}`,
        };
        const command = new GetObjectCommand(getObjectParams);
        const { Body } = await s3Client.send(command);

        const chunks = [];
        await pipeline(Body, async function* (source) {
            for await (const chunk of source) {
                chunks.push(chunk);
            }
        });
        logger.info(`Filename: ${filebasename} | Chunks:${chunks}`);
        const fileBuffer = Buffer.concat(chunks);
        const localFilePath = path.join(__dirname, `temp_images_data.db`);

        fs_1.writeFileSync(localFilePath, fileBuffer);

        const db = new Database(localFilePath, { readonly: true });
        let imageObjects = [];
        try {
            const rows = db.prepare('SELECT * FROM image_data').all();
            imageObjects = rows.map((row) => {
                const splitKey = process.env.S3_FILE_KEY.split('/');
                logger.info(`thr path in the loop: temp/${splitKey[1]}/output_autotag/images/${row.img_path}`);
                return {
                    id: row.objid,
                    path: `temp/${splitKey[1]}/output_autotag/images/${splitKey.pop()}_${row.img_path}`,
                    context_json: {
                        context: row.context,
                    },
                };
            });
        } catch (err) {
            console.error('Error querying the database:', err.message);
        } finally {
            db.close();
        }

        let combinedResults = {};
        let successCount = 0;
        let failureCount = 0;

        logger.info(`Filename: ${filebasename} | imageObjects: ${imageObjects}`);
        logger.info(`Filename: ${filebasename} | Total images to process: ${imageObjects.length}`);

        for (const imageObject of imageObjects) {
            try {
                const getObjectParams = {
                    Bucket: bucketName,
                    Key: imageObject.path,
                };
                logger.info(`Filename: ${filebasename} | Image Object Path: ${imageObject.path}`);
                logger.info(`Filename: ${filebasename} | Image Object Bucketname: ${bucketName}`);
                const command = new GetObjectCommand(getObjectParams);
                const { Body } = await s3Client.send(command);

                const chunks = [];
                await pipeline(Body, async function* (source) {
                    for await (const chunk of source) {
                        chunks.push(chunk);
                    }
                });
                const fileBuffer = Buffer.concat(chunks);
                const localFilePath = path.join(__dirname, `${imageObject.path.split('/').pop()}`);
                logger.info(`Filename: ${filebasename} | Local File Path: ${localFilePath}`);
                fs_1.writeFileSync(localFilePath, fileBuffer);
                const image_Buffer = await fs.readFile(localFilePath);
                const response = await generateAltText(imageObject, image_Buffer);
                logger.info(`Filename: ${filebasename} | Response:${response}`);
                Object.assign(combinedResults, JSON.parse(response));
                successCount++;
                logger.info(`Filename: ${filebasename} | Alt text generation succeeded for image ${imageObject.id} (${successCount} succeeded, ${failureCount} failed)`);
            } catch (error) {
                failureCount++;
                logger.error(`Filename: ${filebasename} | Alt text generation failed for image ${imageObject.id}: ${error.message || error}`);
                logger.info(`Filename: ${filebasename} | Progress: ${successCount} succeeded, ${failureCount} failed`);
            }
            await sleep(2000);
        }

        if (imageObjects.length > 0 && successCount === 0) {
            logger.error(`Filename: ${filebasename} | All ${failureCount} alt text generation requests failed - likely due to throttling or Bedrock API issues`);
            logger.error(`File: ${filebasename}, Status: Failed in second ECS task - All Bedrock requests failed`);
            process.exit(1);
        }

        logger.info(`Filename: ${filebasename} | Alt text generation complete: ${successCount} succeeded, ${failureCount} failed out of ${imageObjects.length} images`);

        let defaultText = "No text available";

        for (const imageObject of imageObjects) {
            if (!combinedResults.hasOwnProperty(imageObject.id)) {
                combinedResults[imageObject.id] = defaultText;
            }
        }

        logger.info(`Filename: ${filebasename} | Combined Results:${combinedResults}`);

        let descriptions = Object.values(combinedResults);
        let zipped = imageObjects.map((element, index) => [element.id, descriptions[index]]);
        logger.info(`Filename: ${filebasename} | zipped: ${zipped}`);

        await modifyPDF(combinedResults, bucketName, "output_autotag/COMPLIANT.pdf", path.basename(process.env.S3_FILE_KEY), filebasename);
        logger.info(`Filename: ${filebasename} | PDF modification complete`);

    } catch (error) {
        logger.info(`File: ${filebasename}, Status: Error in second ECS task`);
        logger.error(`Filename: ${filebasename} | Error processing images: ${error}`);
        process.exit(1);
    }
}

startProcess();
