import React from 'react';
import { Box, Typography, Link } from '@mui/material';

const PacChecker = () => {
  return (
    <Box sx={{ margin: 2 }}>
      <Typography variant="h6">
        PAC Accessibility Checker
      </Typography>
      <Typography variant="body1">
        This tool helps check the accessibility of PDF files and is only available for Windows. For more information or to download the tool, please visit:
      </Typography>
      <Link href="https://pac.pdf-accessibility.org/en" target="_blank" rel="noopener noreferrer" sx={{ marginTop: 1 }}>
        PDF Accessibility Checker (PAC)
      </Link>
    </Box>
  );
};

export default PacChecker;
