import React from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Typography,
  Box,
  Alert,
  Chip,
  Divider,
} from '@mui/material';
import WarningIcon from '@mui/icons-material/Warning';
import BuildIcon from '@mui/icons-material/Build';

const DeploymentPopup = ({ open, onClose, validation }) => {
  const handleVisitRepo = () => {
    window.open(validation.deploymentUrl, '_blank');
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="md"
      fullWidth
      PaperProps={{
        sx: {
          borderRadius: 3,
          padding: 1,
        }
      }}
    >
      <DialogTitle sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 2,
        backgroundColor: '#ffffff',
        color: '#1f2937',
        borderBottom: '1px solid #e5e7eb'
      }}>
        <WarningIcon sx={{ fontSize: 28 }} />
        <Typography variant="h5" sx={{ fontWeight: 600 }}>
          Backend Deployment Required
        </Typography>
      </DialogTitle>

      <DialogContent sx={{ padding: 3 }}>
        <Box sx={{ mb: 3 }}>
          <Typography variant="body1" sx={{ mb: 2, color: '#374151' }}>
            {validation.specificFormat
              ? `The ${validation.specificBucket} for ${validation.specificFormat === 'pdf' ? 'PDF to PDF' : 'PDF to HTML'} processing is not configured.`
              : 'The PDF Accessibility backend infrastructure has not been deployed yet. This is required for the application to function properly.'
            }
          </Typography>

          {validation.missingBuckets.length > 0 && (
            <Alert severity="warning" sx={{ mb: 3 }}>
              <Typography variant="body2" sx={{ fontWeight: 600, mb: 1 }}>
                Missing Configuration:
              </Typography>
              <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                {validation.missingBuckets.map((bucket, index) => (
                  <Chip
                    key={index}
                    label={bucket}
                    color="warning"
                    size="small"
                    variant="outlined"
                  />
                ))}
              </Box>
            </Alert>
          )}

          <Divider sx={{ my: 3 }} />

          <Typography variant="h6" sx={{ mb: 2, color: '#1f2937', fontWeight: 600 }}>
            🚀 {validation.specificFormat ? 'Enable This Feature:' : 'Quick Installation Options:'}
          </Typography>

          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <Box sx={{
              padding: 2,
              backgroundColor: '#f8fafc',
              borderRadius: 2,
              border: '1px solid #e2e8f0'
            }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1, color: '#1f2937' }}>
                Option 1: Install Backend Infrastructure
              </Typography>
              <Typography variant="body2" sx={{ color: '#6b7280', mb: 2 }}>
                {validation.specificFormat
                  ? `Install the ${validation.specificBucket} and related infrastructure for ${validation.specificFormat === 'pdf' ? 'PDF to PDF' : 'PDF to HTML'} processing.`
                  : 'Install the complete AWS infrastructure using CDK. This will create all necessary resources including S3 buckets, Lambda functions, and ECS tasks.'
                }
              </Typography>
              <Button
                variant="contained"
                startIcon={<BuildIcon />}
                onClick={handleVisitRepo}
                sx={{
                  backgroundColor: '#0033A1',
                  '&:hover': { backgroundColor: '#002080' }
                }}
              >
                Deploy from GitHub
              </Button>
            </Box>

            <Box sx={{
              padding: 2,
              backgroundColor: '#f0f9ff',
              borderRadius: 2,
              border: '1px solid #bae6fd'
            }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1, color: '#1f2937' }}>
                Option 2: Configure Environment Variables
              </Typography>
              <Typography variant="body2" sx={{ color: '#6b7280', mb: 2 }}>
                If you already have the backend deployed, add the bucket name to your Amplify environment variables:
              </Typography>
              <Box sx={{ fontFamily: 'monospace', fontSize: '0.875rem', backgroundColor: '#f1f5f9', padding: 2, borderRadius: 1 }}>
                {validation.specificFormat ? (
                  <div>
                    {validation.specificFormat === 'pdf'
                      ? 'REACT_APP_PDF_BUCKET_NAME=your-pdf-bucket-name'
                      : 'REACT_APP_HTML_BUCKET_NAME=your-html-bucket-name'
                    }
                  </div>
                ) : (
                  <>
                    <div>REACT_APP_PDF_BUCKET_NAME=your-pdf-bucket-name</div>
                    <div>REACT_APP_HTML_BUCKET_NAME=your-html-bucket-name</div>
                  </>
                )}
              </Box>
            </Box>
          </Box>
        </Box>

        <Alert severity="info">
          <Typography variant="body2">
            <strong>Note:</strong> After deployment or configuration, refresh the page to apply the changes.
          </Typography>
        </Alert>
      </DialogContent>

      <DialogActions sx={{ padding: 3, borderTop: '1px solid #e5e7eb' }}>
        <Button onClick={onClose} variant="outlined">
          Close
        </Button>
        <Button
          onClick={handleVisitRepo}
          variant="contained"
          sx={{
            backgroundColor: '#0033A1',
            '&:hover': { backgroundColor: '#002080' }
          }}
        >
          Go to Deployment Guide
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default DeploymentPopup;
