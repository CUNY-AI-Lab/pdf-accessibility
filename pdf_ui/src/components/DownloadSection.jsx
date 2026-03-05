import React from 'react';
import ProcessingContainer from './ProcessingContainer';

export default function DownloadSection({ originalFileName, updatedFilename, onFileReady, awsCredentials, selectedFormat }) {
  return (
    <ProcessingContainer
      originalFileName={originalFileName}
      updatedFilename={updatedFilename}
      onFileReady={onFileReady}
      awsCredentials={awsCredentials}
      selectedFormat={selectedFormat}
    />
  );
}
