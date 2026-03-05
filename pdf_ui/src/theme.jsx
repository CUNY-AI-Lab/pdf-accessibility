import { createTheme } from '@mui/material/styles';
import {
  PRIMARY_MAIN,
  SECONDARY_MAIN,
  CHAT_LEFT_PANEL_BACKGROUND,
  HEADER_BACKGROUND,
  primary_50
} from './utilities/constants.jsx';

const theme = createTheme({
  breakpoints: {
    values: {
      xs: 0,
      sm: 600,
      md: 900,
      lg: 1200,
      xl: 1536,
    },
  },
  typography: {
    fontFamily: '"Inter", system-ui, -apple-system, sans-serif',
    h1: {
      fontFamily: '"Outfit", system-ui, sans-serif',
      fontSize: '2.5rem',
      fontWeight: 700,
      '@media (max-width:600px)': {
        fontSize: '2rem',
      },
    },
    h2: {
      fontFamily: '"Outfit", system-ui, sans-serif',
      fontSize: '2rem',
      fontWeight: 700,
      '@media (max-width:600px)': {
        fontSize: '1.75rem',
      },
    },
    h3: {
      fontFamily: '"Outfit", system-ui, sans-serif',
      fontSize: '1.75rem',
      fontWeight: 600,
      '@media (max-width:600px)': {
        fontSize: '1.5rem',
      },
    },
    h4: {
      fontFamily: '"Outfit", system-ui, sans-serif',
      fontSize: '1.5rem',
      fontWeight: 600,
      '@media (max-width:600px)': {
        fontSize: '1.25rem',
      },
    },
    h5: {
      fontFamily: '"Outfit", system-ui, sans-serif',
      fontSize: '1.25rem',
      fontWeight: 600,
      '@media (max-width:600px)': {
        fontSize: '1.125rem',
      },
    },
    h6: {
      fontFamily: '"Outfit", system-ui, sans-serif',
      fontSize: '1.125rem',
      fontWeight: 600,
      '@media (max-width:600px)': {
        fontSize: '1rem',
      },
    },
    body1: {
      fontSize: '1rem',
      lineHeight: 1.7,
      '@media (max-width:600px)': {
        fontSize: '0.875rem',
      },
    },
    body2: {
      fontSize: '0.875rem',
      lineHeight: 1.6,
      '@media (max-width:600px)': {
        fontSize: '0.8125rem',
      },
    },
  },
  palette: {
    primary: {
      main: PRIMARY_MAIN,
      50: primary_50,
    },
    secondary: {
      main: SECONDARY_MAIN,
    },
    background: {
      chatLeftPanel: CHAT_LEFT_PANEL_BACKGROUND,
      header: HEADER_BACKGROUND,
    },
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          textTransform: 'none',
          minHeight: 44,
          fontWeight: 500,
          fontFamily: '"Inter", system-ui, sans-serif',
          '@media (max-width:600px)': {
            minHeight: 48,
            fontSize: '0.875rem',
            padding: '12px 16px',
          },
        },
      },
    },
    MuiIconButton: {
      styleOverrides: {
        root: {
          minHeight: 44,
          minWidth: 44,
          '@media (max-width:600px)': {
            minHeight: 48,
            minWidth: 48,
          },
        },
      },
    },
    MuiDrawer: {
      styleOverrides: {
        paper: {
          '@media (max-width:900px)': {
            width: '100%',
            maxWidth: '320px',
          },
        },
      },
    },
  },
});

export default theme;
