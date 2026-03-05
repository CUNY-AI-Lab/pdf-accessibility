// MaintenancePage.jsx
import React from 'react';
import { Box, Typography } from '@mui/material';

const MaintenancePage = () => {
  return (
    <Box
      display="flex"
      flexDirection="column"
      justifyContent="center"
      alignItems="center"
      minHeight="100vh"
      textAlign="center"
      p={2}
    >
      <Typography variant="h3" gutterBottom>
        Site Under Maintenance
      </Typography>
      <Typography variant="h6">
        We're currently working to get the site back up and running.
      </Typography>
      <Typography variant="body1" mt={2}>
        Thank you for your patience.
      </Typography>
    </Box>
  );
};

export default MaintenancePage;
