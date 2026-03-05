// src/components/LogoutPage.js
import React, { useEffect } from 'react';
import { Box, Typography } from '@mui/material';
import { ThemeProvider } from '@mui/material/styles';
import theme from '../../theme';
import { useAuth } from 'react-oidc-context';

function LogoutPage({ setIsLoggingOut }) {
  const auth = useAuth();

  useEffect(() => {
    const performLogout = async () => {
      try {
        // Use the signoutRedirect method provided by react-oidc-context
        await auth.signoutRedirect();
        // After logout, reset the isLoggingOut state
        setIsLoggingOut(false);
      } catch (error) {
        console.error('Error during sign out:', error);
        setIsLoggingOut(false); // Reset even if there's an error
      }
    };

    performLogout();
  }, [auth, setIsLoggingOut]);

  return (
    <ThemeProvider theme={theme}>
      <Box
        sx={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          height: '100vh',
        }}
      >
        <Typography variant="h5">
          You will been successfully logged out. Please ignore the error 
        </Typography>
      </Box>
    </ThemeProvider>
  );
}

export default LogoutPage;
