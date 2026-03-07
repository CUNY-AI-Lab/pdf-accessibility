import React, { useState, useEffect, useCallback, useRef } from 'react';
import { S3Client, HeadObjectCommand, GetObjectCommand, ListObjectsV2Command } from '@aws-sdk/client-s3';
import { getSignedUrl } from '@aws-sdk/s3-request-presigner';
import ResultsContainer from './ResultsContainer';
import './ProcessingContainer.css';
import { PDFBucket, HTMLBucket, region } from '../utilities/constants';

/**
 * Pipeline stages for PDF-to-PDF:
 *   Upload → Splitter → AI Tagger → Alt-Text → Merger → Title Generator → Done
 *
 * S3 artifacts at each stage:
 *   temp/<base>/<base>_chunk_N.pdf                    — Splitter output
 *   temp/<base>/output_autotag/COMPLIANT_*.pdf        — AI Tagger output
 *   temp/<base>/FINAL_*.pdf                           — Alt-Text output
 *   temp/<base>/merged_<base>.pdf                     — Merger output
 *   result/COMPLIANT_<updatedFilename>                — Final output
 */

const STAGES = [
  { key: 'uploading',   label: 'Uploading PDF',                   pct: 5  },
  { key: 'splitting',   label: 'Splitting into chunks',           pct: 10 },
  { key: 'precheck',    label: 'Running pre-remediation audit',   pct: 15 },
  { key: 'tagging',     label: 'AI tagging for accessibility',    pct: 40 },
  { key: 'alttext',     label: 'Generating alt text for images',  pct: 65 },
  { key: 'merging',     label: 'Merging chunks',                  pct: 80 },
  { key: 'finalizing',  label: 'Adding title & metadata',         pct: 90 },
  { key: 'postcheck',   label: 'Running post-remediation audit',  pct: 95 },
  { key: 'done',        label: 'Complete',                        pct: 100 },
];

const ProcessingContainer = ({
  originalFileName,
  updatedFilename,
  onFileReady,
  awsCredentials,
  selectedFormat,
  onNewUpload
}) => {
  const [downloadUrl, setDownloadUrl] = useState('');
  const [isFileReady, setIsFileReady] = useState(false);
  const [elapsedTime, setElapsedTime] = useState(0);
  const [currentStage, setCurrentStage] = useState(0); // index into STAGES
  const [progress, setProgress] = useState(5);
  const [chunkInfo, setChunkInfo] = useState(''); // e.g. "3 of 5 chunks tagged"
  const pollingRef = useRef(0);

  const basename = updatedFilename ? updatedFilename.replace(/\.pdf$/i, '') : '';

  const getS3Client = useCallback(() => {
    if (!awsCredentials?.accessKeyId) return null;
    return new S3Client({
      region,
      credentials: {
        accessKeyId: awsCredentials.accessKeyId,
        secretAccessKey: awsCredentials.secretAccessKey,
        sessionToken: awsCredentials.sessionToken,
      },
    });
  }, [awsCredentials]);

  const generatePresignedUrl = useCallback(async (bucket, key, filename) => {
    const s3 = getS3Client();
    if (!s3) throw new Error('No S3 client');
    const command = new GetObjectCommand({
      Bucket: bucket,
      Key: key,
      ResponseContentDisposition: `attachment; filename="${filename}"`,
    });
    return await getSignedUrl(s3, command, { expiresIn: 30000 });
  }, [getS3Client]);

  // Count S3 objects matching a prefix
  const countObjects = useCallback(async (s3, prefix) => {
    try {
      const res = await s3.send(new ListObjectsV2Command({
        Bucket: PDFBucket,
        Prefix: prefix,
        MaxKeys: 200,
      }));
      return res.Contents ? res.Contents.length : 0;
    } catch {
      return 0;
    }
  }, []);

  // Check if a specific S3 key exists
  const objectExists = useCallback(async (s3, bucket, key) => {
    try {
      await s3.send(new HeadObjectCommand({ Bucket: bucket, Key: key }));
      return true;
    } catch {
      return false;
    }
  }, []);

  const truncateFilename = (filename) => {
    const THRESHOLD = 30;
    if (filename.length > THRESHOLD) {
      const ext = filename.substring(filename.lastIndexOf('.'));
      return filename.substring(0, THRESHOLD - ext.length) + '...' + ext;
    }
    return filename;
  };

  const formatElapsedTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  // Main polling effect — checks real S3 artifacts to determine stage
  useEffect(() => {
    if (!updatedFilename || !basename || isFileReady) return;

    let timeInterval;
    let pollInterval;
    let cancelled = false;

    const pollProgress = async () => {
      const s3 = getS3Client();
      if (!s3 || cancelled) return;

      pollingRef.current += 1;
      const attempt = pollingRef.current;

      // Stop after 30 min (180 attempts at 10s)
      if (attempt > 180) {
        clearInterval(pollInterval);
        clearInterval(timeInterval);
        return;
      }

      const selectedBucket = selectedFormat === 'html' ? HTMLBucket : PDFBucket;

      // For HTML format, just check final file (no intermediate artifacts to track)
      if (selectedFormat === 'html') {
        const sanitize = (fn) => {
          let s = fn.replace(/\s/g, '_');
          // eslint-disable-next-line no-control-regex
          s = s.replace(/[\x00-\x1F\x7F{^}%`\]">[~<#|&\\*?/$!'":@+=]/g, '_');
          while (s.includes('__')) s = s.replace(/__/g, '_');
          return s.replace(/^_+|_+$/g, '');
        };
        const htmlKey = `remediated/final_${sanitize(updatedFilename.replace('.pdf', '.zip'))}`;
        const done = await objectExists(s3, selectedBucket, htmlKey);
        if (done) {
          const desiredFilename = `final_${originalFileName.replace('.pdf', '.zip')}`;
          const url = await generatePresignedUrl(selectedBucket, htmlKey, desiredFilename);
          if (!cancelled) {
            setProgress(100);
            setCurrentStage(STAGES.length - 1);
            setDownloadUrl(url);
            setIsFileReady(true);
            onFileReady(url);
            clearInterval(pollInterval);
            clearInterval(timeInterval);
          }
        } else {
          // Estimate progress for HTML based on elapsed time (no intermediate files)
          const elapsed = pollingRef.current * 10;
          const estimated = Math.min(85, 10 + Math.floor(elapsed / 3));
          if (!cancelled) {
            setProgress(estimated);
            setCurrentStage(Math.min(6, Math.floor(estimated / 15)));
          }
        }
        return;
      }

      // --- PDF-to-PDF: check real pipeline artifacts ---

      // Stage 1: Check for chunks (splitter output)
      const chunkCount = await countObjects(s3, `temp/${basename}/${basename}_chunk_`);

      if (chunkCount === 0) {
        // Still splitting or waiting
        if (!cancelled) {
          setCurrentStage(1);
          setProgress(10);
          setChunkInfo('');
        }
        return;
      }

      // Stage 2: Pre-check report
      const preReportCount = await countObjects(s3, `temp/${basename}/accessability-report/${basename}_accessibility_report_before`);

      // Stage 3: AI Tagger — count COMPLIANT_*.pdf files in output_autotag
      const taggedCount = await countObjects(s3, `temp/${basename}/output_autotag/COMPLIANT_`);

      if (taggedCount < chunkCount) {
        // Still tagging
        const tagPct = chunkCount > 0 ? Math.floor((taggedCount / chunkCount) * 100) : 0;
        const stagePct = 15 + Math.floor(tagPct * 0.25); // 15% to 40%
        if (!cancelled) {
          setCurrentStage(3);
          setProgress(Math.max(preReportCount > 0 ? 15 : 12, stagePct));
          setChunkInfo(chunkCount > 1 ? `${taggedCount} of ${chunkCount} chunks tagged` : '');
        }
        return;
      }

      // Stage 4: Alt-text — count FINAL_*.pdf files
      const altTextCount = await countObjects(s3, `temp/${basename}/FINAL_`);

      if (altTextCount < chunkCount) {
        const altPct = chunkCount > 0 ? Math.floor((altTextCount / chunkCount) * 100) : 0;
        const stagePct = 40 + Math.floor(altPct * 0.25); // 40% to 65%
        if (!cancelled) {
          setCurrentStage(4);
          setProgress(stagePct);
          setChunkInfo(chunkCount > 1 ? `${altTextCount} of ${chunkCount} chunks processed` : '');
        }
        return;
      }

      // Stage 5: Merger
      const mergedExists = await objectExists(s3, PDFBucket, `temp/${basename}/merged_${basename}.pdf`);

      if (!mergedExists) {
        if (!cancelled) {
          setCurrentStage(5);
          setProgress(70);
          setChunkInfo('');
        }
        return;
      }

      // Stage 6: Final result
      const finalKey = `result/COMPLIANT_${updatedFilename}`;
      const finalExists = await objectExists(s3, PDFBucket, finalKey);

      if (!finalExists) {
        // Check for post-check report as a signal we're close
        const postReportCount = await countObjects(s3, `temp/${basename}/accessability-report/COMPLIANT_${basename}_accessibility_report_after`);
        if (!cancelled) {
          setCurrentStage(postReportCount > 0 ? 7 : 6);
          setProgress(postReportCount > 0 ? 95 : 85);
          setChunkInfo('');
        }
        return;
      }

      // Done!
      const desiredFilename = `COMPLIANT_${originalFileName}`;
      const url = await generatePresignedUrl(PDFBucket, finalKey, desiredFilename);
      if (!cancelled) {
        setProgress(100);
        setCurrentStage(STAGES.length - 1);
        setChunkInfo('');
        setDownloadUrl(url);
        setIsFileReady(true);
        onFileReady(url);
        clearInterval(pollInterval);
        clearInterval(timeInterval);
      }
    };

    // Timer
    timeInterval = setInterval(() => {
      setElapsedTime(prev => prev + 1);
    }, 1000);

    // Poll every 10 seconds
    pollInterval = setInterval(pollProgress, 10000);
    // Also poll immediately
    pollProgress();

    return () => {
      cancelled = true;
      clearInterval(timeInterval);
      clearInterval(pollInterval);
    };
  }, [updatedFilename, basename, isFileReady, selectedFormat, getS3Client, countObjects, objectExists, generatePresignedUrl, originalFileName, onFileReady]);

  const stage = STAGES[currentStage] || STAGES[0];

  return (
    <div className="processing-container">
      <div className="processing-content">
        <div className="processing-header">
          <div className="header-content">
            <h2>{isFileReady ? `File Ready: ${truncateFilename(originalFileName)}` : `Processing: ${truncateFilename(originalFileName)}`}</h2>
            <div className="flow-indicator">
              {selectedFormat === 'html' ? 'PDF → HTML' : 'PDF → PDF'}
            </div>
          </div>
        </div>

        <div className="processing-info">
          <div className="time-info">
            <span>Time elapsed: {formatElapsedTime(elapsedTime)}</span>
          </div>
          <p className="processing-description">
            {isFileReady
              ? 'Remediation complete! Your file is ready for download.'
              : 'Processing time depends on document size and complexity.'
            }
          </p>
        </div>

        {!isFileReady ? (
          <div className="progress-section">
            <div className="progress-percentage">{progress}%</div>
            <div className="progress-bar-track">
              <div
                className="progress-bar-fill"
                style={{ width: `${progress}%` }}
              />
            </div>
            <div className="progress-stage-label">
              {stage.label}
              {chunkInfo && <span className="progress-chunk-info"> — {chunkInfo}</span>}
            </div>
          </div>
        ) : (
          <ResultsContainer
            fileName={originalFileName}
            processedResult={{ url: downloadUrl }}
            format={selectedFormat}
            fileSize="File processed successfully"
            processingTime="Processing completed"
          />
        )}

      </div>
    </div>
  );
};

export default ProcessingContainer;
