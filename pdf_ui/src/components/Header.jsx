// src/components/Header.js
import React, { useState } from 'react';
import {
  AppBar,
  Toolbar,
  Typography,
  Button,
  Box,
  LinearProgress,
  IconButton,
  Collapse,
  useMediaQuery,
  useTheme
} from '@mui/material';
import PropTypes from 'prop-types';
import { HEADER_BACKGROUND } from '../utilities/constants';
import logo from '../assets/pdf-accessability-logo.svg';
import MenuIcon from '@mui/icons-material/Menu';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';

function Header({ handleSignOut, usageCount, maxFilesAllowed, refreshUsage, usageError, loadingUsage, onMenuClick }) {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const [usageExpanded, setUsageExpanded] = useState(false);
  
  // Compute usage visually
  const usagePercentage = maxFilesAllowed > 0 ? Math.min((usageCount / maxFilesAllowed) * 100, 100) : 0;

  // Determine progress bar color based on usage
  const getProgressBarColor = () => {
    if (usagePercentage < 50) return '#66bb6a'; // Green
    if (usagePercentage < 80) return '#ffa726'; // Orange
    return '#ef5350'; // Red
  };

  // Format numbers for better readability
  const formatNumber = (num) => {
    return num.toLocaleString();
  };

  const toggleUsageExpanded = () => {
    setUsageExpanded(!usageExpanded);
  };

  return (
    <AppBar position="static" color={HEADER_BACKGROUND} role="banner" aria-label="Application Header">
      <Toolbar sx={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'center',
        flexWrap: 'nowrap',
        minHeight: { xs: 56, sm: 64 },
        overflow: 'hidden'
      }}>
        
        {/* Left Side: Menu Button (mobile) + App Title with Logo */}
        <Box sx={{ 
          display: 'flex', 
          alignItems: 'center', 
          gap: { xs: 1, sm: 2 },
          flex: '0 0 auto',
          minWidth: 0
        }}>
          {isMobile && onMenuClick && (
            <IconButton
              color="inherit"
              aria-label="open navigation menu"
              onClick={onMenuClick}
              sx={{ mr: 1 }}
            >
              <MenuIcon />
            </IconButton>
          )}
          
          <Box sx={{ display: { xs: 'none', sm: 'block' } }}>
            <img
              src={logo}
              alt="PDF Accessibility Logo"
              style={{ 
                height: isMobile ? '32px' : '40px', 
                width: 'auto' 
              }}
            />
          </Box>
        </Box>

        {/* Right Side: Usage Count and Home Button */}
        <Box sx={{ 
          display: 'flex', 
          alignItems: 'center', 
          gap: { xs: 0.5, sm: 2 },
          flexWrap: 'nowrap',
          minWidth: 0, // Allow shrinking
          flex: '0 0 auto' // Don't grow or shrink
        }}>
          
          {/* Display usage + progress bar */}
          {isMobile ? (
            <Box sx={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: 0.25,
              minWidth: 0,
              flex: '0 0 auto'
            }}>
              <Typography 
                variant="body2" 
                sx={{ 
                  fontSize: '0.7rem',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  maxWidth: '60px'
                }}
              >
                {loadingUsage
                  ? 'Checking...'
                  : usageError
                    ? 'Error'
                    : `${formatNumber(usageCount)}/${formatNumber(maxFilesAllowed)}`}
              </Typography>
              <IconButton
                size="small"
                onClick={toggleUsageExpanded}
                aria-label={usageExpanded ? 'Hide usage details' : 'Show usage details'}
                sx={{ 
                  color: 'inherit', 
                  p: 0.25,
                  minWidth: 24,
                  minHeight: 24,
                  width: 24,
                  height: 24
                }}
              >
                {usageExpanded ? <ExpandLessIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />}
              </IconButton>
            </Box>
          ) : (
            <Box sx={{ 
              minWidth: { xs: 150, sm: 200 },
              maxWidth: { xs: 180, sm: 250 },
              flex: '0 0 auto'
            }}>
              <Typography 
                variant="body2" 
                sx={{ 
                  mb: 0.5,
                  fontSize: { xs: '0.75rem', sm: '0.875rem' },
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis'
                }}
              >
                {loadingUsage
                  ? 'Checking usage...'
                  : usageError
                    ? `Error: ${usageError}`
                    : `Used: ${formatNumber(usageCount)} / ${formatNumber(maxFilesAllowed)}`}
              </Typography>
              
              {!usageError && !loadingUsage && (
                <LinearProgress
                  variant="determinate"
                  value={usagePercentage}
                  sx={{
                    height: 6,
                    borderRadius: '3px',
                    '& .MuiLinearProgress-bar': {
                      backgroundColor: getProgressBarColor(), 
                    },
                  }}
                  aria-valuenow={usagePercentage}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  role="progressbar"
                  aria-label={`Usage: ${formatNumber(usageCount)} out of ${formatNumber(maxFilesAllowed)} files uploaded`}
                />
              )}
            </Box>
          )}

          {/* Optional: "Refresh Usage" button */}
          {/* Uncomment the button below if you want to allow manual refreshing from the header */}
          {/*
          <Button
            onClick={refreshUsage}
            variant="contained"
            disabled={loadingUsage}
            sx={{
              textTransform: 'none',
              backgroundColor: '#1976d2',
              '&:hover': {
                backgroundColor: '#125b9d'
              }
            }}
          >
            Refresh Usage
          </Button>
          */}

          {/* Home Button */}
          <Button
            onClick={handleSignOut}
            variant="outlined"
            size={isMobile ? 'small' : 'medium'}
            sx={{
              borderColor: '#1976d2',
              color: '#1976d2',
              padding: isMobile ? '2px 6px' : '6px 16px',
              borderRadius: '4px',
              fontSize: isMobile ? '0.6rem' : '0.875rem',
              minHeight: isMobile ? 32 : 40,
              maxHeight: isMobile ? 32 : 40,
              minWidth: isMobile ? 45 : 'auto',
              maxWidth: isMobile ? 45 : 'auto',
              height: isMobile ? 32 : 40,
              flex: '0 0 auto',
              whiteSpace: 'nowrap',
              transform: 'scale(1)',
              zoom: 1,
              '&:hover': {
                backgroundColor: 'rgba(25, 118, 210, 0.1)',
                borderColor: '#1565c0',
                transform: 'scale(1)',
              },
              '&:focus': {
                outline: 'none',
                boxShadow: '0 0 4px rgba(25, 118, 210, 0.5)',
                transform: 'scale(1)',
              },
              transition: 'all 0.3s ease-in-out',
            }}
            aria-label="Home Button"
          >
            {isMobile ? 'Home' : 'Home'}
          </Button>
        </Box>
      </Toolbar>
      
      {/* Mobile Usage Details */}
      {isMobile && (
        <Collapse in={usageExpanded}>
          <Box sx={{ p: 2, backgroundColor: 'rgba(0, 0, 0, 0.1)' }}>
            <Typography variant="body2" sx={{ mb: 1 }}>
              {loadingUsage
                ? 'Checking usage...'
                : usageError
                  ? `Error: ${usageError}`
                  : `Used: ${formatNumber(usageCount)} / ${formatNumber(maxFilesAllowed)}`}
            </Typography>
            
            {!usageError && !loadingUsage && (
              <LinearProgress
                variant="determinate"
                value={usagePercentage}
                sx={{
                  height: 6,
                  borderRadius: '3px',
                  '& .MuiLinearProgress-bar': {
                    backgroundColor: getProgressBarColor(), 
                  },
                }}
                aria-valuenow={usagePercentage}
                aria-valuemin={0}
                aria-valuemax={100}
                role="progressbar"
                aria-label={`Usage: ${formatNumber(usageCount)} out of ${formatNumber(maxFilesAllowed)} files uploaded`}
              />
            )}
          </Box>
        </Collapse>
      )}
    </AppBar>
  );
}

Header.propTypes = {
  handleSignOut: PropTypes.func.isRequired,
  usageCount: PropTypes.number.isRequired,
  maxFilesAllowed: PropTypes.number.isRequired,
  refreshUsage: PropTypes.func.isRequired,
  usageError: PropTypes.string,
  loadingUsage: PropTypes.bool,
  onMenuClick: PropTypes.func,
};

export default Header;
