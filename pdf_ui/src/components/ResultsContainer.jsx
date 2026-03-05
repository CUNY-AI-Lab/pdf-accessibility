import React, { useState } from 'react';
import './ResultsContainer.css';
import img1 from "../assets/zap.svg";
import AccessibilityChecker from './AccessibilityChecker';

const ResultsContainer = ({
  fileName,
  processedResult,
  format,
  fileSize,
  processingTime,
  originalFileName,
  updatedFilename,
  awsCredentials,
  onNewUpload
}) => {
  const [isDownloading, setIsDownloading] = useState(false);
  const [showReportDialog, setShowReportDialog] = useState(false);
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);

  // Function to format processing time
  const formatProcessingTime = (seconds) => {
    if (!seconds || seconds < 0) return 'Processing completed';

    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;

    if (mins > 0) {
      return `${mins}m ${secs}s`;
    }
    return `${secs}s`;
  };

  const handleDownload = async () => {
    if (!processedResult || !format || !fileName) {
      alert('Download information not available');
      return;
    }

    setIsDownloading(true);
    try {
      console.log('Starting download for:', { fileName, format });

      // Use the download URL passed from ProcessingContainer
      const downloadUrl = processedResult.url;

      if (!downloadUrl) {
        throw new Error('No download URL received');
      }

      console.log('Using download URL:', downloadUrl);

      // Method 1: Try window.open first (bypasses React Router)
      const downloadWindow = window.open(downloadUrl, '_blank');

      // Fallback: If popup blocked, use temporary link method
      if (!downloadWindow || downloadWindow.closed) {
        console.log('Popup blocked, using link method');

        // Method 2: Create temporary link and force download
        const link = document.createElement('a');
        link.href = downloadUrl;
        link.target = '_blank';
        link.style.display = 'none';

        // Add to DOM, click, and remove
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
      } else {
        // If window.open worked, close it after a short delay (the download should start)
        setTimeout(() => {
          if (downloadWindow && !downloadWindow.closed) {
            downloadWindow.close();
          }
        }, 1000);
      }

      console.log('Download initiated successfully');

    } catch (error) {
      console.error('Download failed:', error);

      // Provide more specific error messages
      let errorMessage = 'Download failed. Please try again.';

      if (error.message.includes('File not found')) {
        errorMessage = 'File not ready yet. Please wait for processing to complete.';
      } else if (error.message.includes('Access denied')) {
        errorMessage = 'Access denied. Please check permissions or contact support.';
      } else if (error.message.includes('credentials')) {
        errorMessage = 'Authentication error. Please refresh the page and try again.';
      }

      alert(errorMessage);
    } finally {
      setIsDownloading(false);
    }
  };


  return (
    <>
      <div className="results-container">
        <div className="results-content">
          <div className="results-header">
            <h2>PDF Remediation Successful</h2>
            <div className="flow-indicator">
              {format === 'html' ? 'PDF → HTML' : 'PDF → PDF'}
            </div>
          </div>

          <div className="processing-info">
            <div className="processing-time">
              <img alt="" className="block max-w-none size-full" src={img1} />
              <span>Total Processing Time: {formatProcessingTime(processingTime)}</span>
            </div>
            <p className="description">Your PDF has been successfully remediated for accessibility</p>
          </div>

          <div className="file-success-container">
            <div className="file-info-card">
              <div className="file-name-section">
                <div className="file-icon">
                  <img alt="" className="block max-w-none size-full" src={require("../assets/pdf-icon.svg")} />
                </div>
                <div className="file-details">
                  <div className="file-name">{fileName}</div>
                  <div className="file-status">File processed successfully</div>
                </div>
              </div>
            </div>
          </div>

          <div className="button-group">
            {format === 'pdf' && (
              <button className="view-report-btn" onClick={() => setShowReportDialog(true)}>
                View Report
              </button>
            )}
            <button
              className="download-btn"
              onClick={handleDownload}
              disabled={isDownloading || !processedResult}
              title={isDownloading ? 'Downloading...' : 'Download the processed file'}
            >
              {isDownloading ? 'Downloading...' : `Download ${format === 'html' ? 'ZIP' : 'PDF'} File`}
            </button>
          </div>

                        </div>

      {/* Accessibility Report Dialog - Only for PDF-PDF format */}
      {format === 'pdf' && (
        <AccessibilityChecker
          originalFileName={originalFileName || fileName}
          updatedFilename={updatedFilename}
          awsCredentials={awsCredentials}
          open={showReportDialog}
          onClose={() => setShowReportDialog(false)}
        />
      )}

        <div className="upload-new-section">
          <button className="upload-new-btn" onClick={() => setShowConfirmDialog(true)}>
            Upload a New PDF
          </button>
        </div>
      </div>

      {/* Custom Confirmation Dialog */}
      {showConfirmDialog && (
        <div className="confirm-overlay" onClick={() => setShowConfirmDialog(false)}>
          <div className="confirm-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="confirm-header">
              <h3>Confirm New Upload</h3>
            </div>
            <div className="confirm-body">
              <p>Are you sure you want to upload a new PDF?</p>
              <p className="confirm-warning">This will discard the current PDF and start a new session.</p>
            </div>
            <div className="confirm-actions">
              <button
                className="confirm-btn cancel-btn"
                onClick={() => setShowConfirmDialog(false)}
              >
                Cancel
              </button>
              <button
                className="confirm-btn confirm-btn-primary"
                onClick={() => {
                  setShowConfirmDialog(false);
                  onNewUpload();
                }}
              >
                Yes, Upload New PDF
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default ResultsContainer;
