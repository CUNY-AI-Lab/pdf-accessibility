import React from 'react';
import { Drawer, Box, Typography, Card, CardContent, Divider, Link, IconButton, useMediaQuery, useTheme } from '@mui/material';
import DocumentScannerIcon from '@mui/icons-material/DocumentScanner';
import SupportIcon from '@mui/icons-material/Support';
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';

const LeftNav = ({ isCollapsed, setIsCollapsed, mobileOpen, setMobileOpen, maxFilesAllowed = 100, maxPagesAllowed = 50, maxSizeAllowedMB = 500 }) => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  
  const toggleCollapse = () => {
    if (isMobile) {
      setMobileOpen(!mobileOpen);
    } else {
      setIsCollapsed(!isCollapsed);
    }
  };

  const handleDrawerClose = () => {
    if (isMobile) {
      setMobileOpen(false);
    }
  };

  return (
    <Drawer
      variant={isMobile ? 'temporary' : 'permanent'}
      open={isMobile ? mobileOpen : true}
      onClose={handleDrawerClose}
      sx={{
        width: isMobile ? '100%' : (isCollapsed ? 60 : 360),
        flexShrink: 0,
        transition: 'width 0.3s ease',
        [`& .MuiDrawer-paper`]: {
          width: isMobile ? '100%' : (isCollapsed ? 60 : 360),
          maxWidth: isMobile ? '320px' : 'none',
          boxSizing: 'border-box',
          backgroundColor: '#f9f9f9',
          transition: 'width 0.3s ease',
          overflowX: 'hidden',
        },
      }}
    >
      <Box sx={{ padding: isCollapsed ? 1 : 3, position: 'relative' }}>
        {/* Toggle Button */}
        <IconButton
          onClick={toggleCollapse}
          sx={{
            position: 'absolute',
            top: 8,
            right: isMobile ? 8 : (isCollapsed ? 8 : 8),
            zIndex: 1,
            backgroundColor: 'rgba(255, 255, 255, 0.8)',
            '&:hover': {
              backgroundColor: 'rgba(255, 255, 255, 1)',
            },
            width: isMobile ? 40 : 32,
            height: isMobile ? 40 : 32,
            minHeight: 44,
            minWidth: 44,
          }}
          size="small"
          aria-label={isMobile ? 'Close navigation menu' : (isCollapsed ? 'Expand navigation' : 'Collapse navigation')}
        >
          {isMobile ? <ChevronLeftIcon /> : (isCollapsed ? <ChevronRightIcon /> : <ChevronLeftIcon />)}
        </IconButton>

        {/* Header - Hidden when collapsed on desktop, always shown on mobile */}
        {(!isCollapsed || isMobile) && (
          <Typography variant="h5" fontWeight="bold" gutterBottom sx={{ marginTop: 4 }}>
            How to Use
          </Typography>
        )}

        {/* Document Requirements Card - Hidden when collapsed on desktop, always shown on mobile */}
        {(!isCollapsed || isMobile) && (
          <Card
            sx={{
              marginBottom: 3,
              borderRadius: 2,
              boxShadow: '0px 4px 10px rgba(0, 0, 0, 0.1)',
            }}
          >
          <CardContent>
            <Box display="flex" alignItems="center" marginBottom={2}>
              <DocumentScannerIcon fontSize="large" color="primary" />
              <Typography variant="h6" fontWeight="bold" sx={{ marginLeft: 1 }}>
                Getting Started
              </Typography>
            </Box>
            <Divider sx={{ marginBottom: 2 }} />
            <Typography variant="body2" gutterBottom>
              1. Choose <strong>PDF or HTML</strong> as your output format.
            </Typography>
            <Typography variant="body2" gutterBottom>
              2. <strong>Upload a PDF</strong> document using the upload area.
            </Typography>
            <Typography variant="body2" gutterBottom>
              3. Wait for remediation to complete (typically 1-3 minutes).
            </Typography>
            <Typography variant="body2" gutterBottom>
              4. <strong>Download</strong> your accessible document and review the accessibility report.
            </Typography>
            <Divider sx={{ marginY: 2 }} />
            <Typography variant="subtitle2" fontWeight="bold" gutterBottom>
              Limits
            </Typography>
            <Typography variant="body2" gutterBottom>
              - Up to <strong>{maxFilesAllowed}</strong> documents per account
            </Typography>
            <Typography variant="body2" gutterBottom>
              - Max <strong>{maxPagesAllowed} pages</strong> per document
            </Typography>
            <Typography variant="body2" gutterBottom>
              - Max <strong>{maxSizeAllowedMB} MB</strong> per file
            </Typography>
            <Divider sx={{ marginY: 2 }} />
            <Typography variant="subtitle2" fontWeight="bold" gutterBottom>
              Privacy & Data
            </Typography>
            <Typography variant="body2" gutterBottom>
              - <strong>Zero retention</strong> — uploaded files are processed and then deleted. No data is stored after remediation.
            </Typography>
            <Typography variant="body2" gutterBottom>
              - Only <strong>PDF files</strong> are accepted.
            </Typography>
            <Typography variant="body2" gutterBottom>
              - Fillable forms are not currently remediated.
            </Typography>
          </CardContent>
        </Card>
        )}

        {/* Support Resources Card - Hidden when collapsed on desktop, always shown on mobile */}
        {(!isCollapsed || isMobile) && (
          <Card
            sx={{
              borderRadius: 2,
              boxShadow: '0px 4px 10px rgba(0, 0, 0, 0.1)',
            }}
          >
          <CardContent>
            <Box display="flex" alignItems="center" marginBottom={2}>
              <SupportIcon fontSize="large" color="secondary" />
              <Typography variant="h6" fontWeight="bold" sx={{ marginLeft: 1 }}>
                Need Help?
              </Typography>
            </Box>
            <Divider sx={{ marginBottom: 2 }} />
            <Typography variant="body2" gutterBottom>
              Having trouble or have questions? Reach out to us:
            </Typography>
            <Typography variant="body2" gutterBottom>
              Email: <Link href="mailto:ailab@gc.cuny.edu"><strong>ailab@gc.cuny.edu</strong></Link>
            </Typography>
            <Typography variant="body2" gutterBottom>
              <Link href="https://ailab.gc.cuny.edu" target="_blank" rel="noopener noreferrer">
                Visit the CUNY AI Lab
              </Link>
            </Typography>
          </CardContent>
        </Card>
        )}
      </Box>
    </Drawer>
  );
};

export default LeftNav;
