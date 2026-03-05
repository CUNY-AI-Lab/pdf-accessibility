import React, { useEffect, useState } from 'react';
import { useAuth } from 'react-oidc-context';
import { useNavigate } from 'react-router-dom';

import {
  Box,
  Typography,
  Link,
  Dialog,
  DialogTitle,
  DialogContent,
  IconButton,
  Container,
} from '@mui/material';
import LoadingButton from '@mui/lab/LoadingButton';
import CircularProgress from '@mui/material/CircularProgress';

import ArrowForwardIcon from '@mui/icons-material/ArrowForward';
import CloseIcon from '@mui/icons-material/Close';

import cunyLogo from '../assets/cuny_ai_lab_logo.png';
import awsLogo from '../assets/POWERED_BY_AWS.png';

/* ── Palette (matches CUNY AI Lab website) ── */
const C = {
  navy: '#1D3A83',
  indigo: '#0f172a',
  vibrant: '#3B73E6',
  vibrantHover: '#2A6FB8',
  teal: '#2FB8D6',
  cream: '#FAFCF8',
  pearl: '#f7f4eb',
  stone: '#333333',
  gray600: '#4b5563',
  gray400: '#9ca3af',
  border: '#e5e7eb',
  white: '#ffffff',
};

const LandingPage = () => {
  const auth = useAuth();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [openDialog, setOpenDialog] = useState(false);

  useEffect(() => {
    if (auth.isLoading) return;
    if (auth.isAuthenticated) {
      navigate('/app', { replace: true });
    }
  }, [auth.isLoading, auth.isAuthenticated, navigate]);

  const handleSignIn = () => {
    setLoading(true);
    setTimeout(() => {
      auth.signinRedirect();
    }, 1000);
  };

  if (auth.isLoading) {
    return (
      <Box sx={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: C.cream }}>
        <CircularProgress size={36} thickness={4} sx={{ color: C.vibrant }} />
      </Box>
    );
  }

  return (
    <Box sx={{ backgroundColor: C.cream, minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>

      {/* ── Hero ── */}
      <Box
        sx={{
          backgroundColor: C.navy,
          color: C.white,
          position: 'relative',
          overflow: 'hidden',
        }}
      >
        {/* Subtle dot texture like CAIL site */}
        <Box
          sx={{
            position: 'absolute',
            inset: 0,
            opacity: 0.04,
            backgroundImage: 'radial-gradient(circle, rgba(255,255,255,0.8) 1px, transparent 1px)',
            backgroundSize: '24px 24px',
            pointerEvents: 'none',
          }}
        />

        <Container maxWidth="lg" sx={{ py: { xs: 8, md: 12 }, position: 'relative', zIndex: 1 }}>
          <Box
            sx={{
              display: 'flex',
              flexDirection: { xs: 'column', md: 'row' },
              alignItems: { xs: 'flex-start', md: 'center' },
              gap: { xs: 5, md: 10 },
            }}
          >
            {/* Left copy */}
            <Box sx={{ flex: 1.3 }}>
              <Typography
                sx={{
                  fontFamily: '"Outfit", system-ui, sans-serif',
                  fontSize: '0.8rem',
                  fontWeight: 600,
                  letterSpacing: '0.12em',
                  textTransform: 'uppercase',
                  color: C.teal,
                  mb: 2.5,
                }}
              >
                CUNY AI Lab
              </Typography>

              <Typography
                component="h1"
                sx={{
                  fontFamily: '"Outfit", system-ui, sans-serif',
                  fontSize: { xs: '2.5rem', md: '3.5rem' },
                  fontWeight: 800,
                  lineHeight: 1.1,
                  mb: 3,
                }}
              >
                PDF Accessibility{' '}
                <Box component="span" sx={{ color: C.teal }}>Remediation</Box>
              </Typography>

              <Typography
                sx={{
                  fontSize: { xs: '1rem', md: '1.1rem' },
                  lineHeight: 1.75,
                  color: 'rgba(255,255,255,0.75)',
                  maxWidth: '540px',
                  mb: 4,
                }}
              >
                AI-powered tagging and analysis to bring PDF documents into
                compliance with WCAG 2.1 Level AA standards. Upload a PDF,
                get back a fully remediated document with structural tags,
                alt text, and a compliance report.
              </Typography>

              <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', mb: 5 }}>
                <LoadingButton
                  variant="contained"
                  size="large"
                  endIcon={<ArrowForwardIcon sx={{ fontSize: '18px !important' }} />}
                  onClick={handleSignIn}
                  loading={loading}
                  loadingIndicator={<CircularProgress size={20} sx={{ color: C.white }} />}
                  sx={{
                    backgroundColor: C.vibrant,
                    color: C.white,
                    fontFamily: '"Inter", system-ui, sans-serif',
                    fontWeight: 600,
                    fontSize: '0.95rem',
                    px: 4,
                    py: 1.5,
                    borderRadius: '100px',
                    boxShadow: 'none',
                    transition: 'all 0.2s ease',
                    '&:hover': {
                      backgroundColor: C.vibrantHover,
                      boxShadow: '0 4px 16px rgba(59,115,230,0.3)',
                    },
                    '&.MuiLoadingButton-loading': {
                      backgroundColor: C.vibrant,
                    },
                  }}
                >
                  Log In and Remediate My PDF
                </LoadingButton>

                <Box
                  component="button"
                  onClick={() => setOpenDialog(true)}
                  sx={{
                    background: 'transparent',
                    border: '1px solid rgba(255,255,255,0.25)',
                    color: 'rgba(255,255,255,0.7)',
                    fontFamily: '"Inter", system-ui, sans-serif',
                    fontWeight: 500,
                    fontSize: '0.95rem',
                    px: 3,
                    py: 1.5,
                    borderRadius: '100px',
                    cursor: 'pointer',
                    transition: 'all 0.2s ease',
                    '&:hover': {
                      borderColor: 'rgba(255,255,255,0.5)',
                      color: C.white,
                    },
                  }}
                >
                  How it works
                </Box>
              </Box>

              {/* Logos */}
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                <img
                  src={cunyLogo}
                  alt="CUNY AI Lab Logo"
                  style={{ height: 44, width: 'auto', filter: 'brightness(0) invert(1)', opacity: 0.7 }}
                />
                <Box sx={{ width: '1px', height: '28px', backgroundColor: 'rgba(255,255,255,0.15)' }} />
                <img
                  src={awsLogo}
                  alt="Powered by AWS logo"
                  style={{ height: 28, width: 'auto', opacity: 0.6 }}
                />
              </Box>
            </Box>

            {/* Right side — simple feature list */}
            <Box sx={{ flex: 1 }}>
              <Box
                sx={{
                  backgroundColor: 'rgba(255,255,255,0.05)',
                  border: '1px solid rgba(255,255,255,0.08)',
                  borderRadius: '16px',
                  p: { xs: 3.5, md: 4.5 },
                }}
              >
                {[
                  { label: 'Structural Tagging', desc: 'Headings, paragraphs, lists, and tables tagged automatically' },
                  { label: 'Alt Text Generation', desc: 'AI-generated descriptions for images and figures' },
                  { label: 'Compliance Reports', desc: 'PDF/UA and WCAG 2.1 AA accessibility scoring' },
                  { label: 'Reading Order', desc: 'Logical content flow for screen readers' },
                ].map((item, i) => (
                  <Box
                    key={i}
                    sx={{
                      py: 2,
                      borderBottom: i < 3 ? '1px solid rgba(255,255,255,0.06)' : 'none',
                    }}
                  >
                    <Typography
                      sx={{
                        fontFamily: '"Outfit", system-ui, sans-serif',
                        fontWeight: 600,
                        fontSize: '0.95rem',
                        color: C.white,
                        mb: 0.3,
                      }}
                    >
                      {item.label}
                    </Typography>
                    <Typography sx={{ fontSize: '0.85rem', color: 'rgba(255,255,255,0.5)' }}>
                      {item.desc}
                    </Typography>
                  </Box>
                ))}
              </Box>
            </Box>
          </Box>
        </Container>
      </Box>

      {/* ── About section on cream ── */}
      <Box sx={{ backgroundColor: C.cream }}>
        <Container
          maxWidth="lg"
          sx={{
            py: { xs: 7, md: 10 },
            display: 'flex',
            flexDirection: { xs: 'column', md: 'row' },
            gap: { xs: 5, md: 8 },
          }}
        >
          <Box sx={{ flex: 1 }}>
            <Typography
              sx={{
                fontFamily: '"Outfit", system-ui, sans-serif',
                fontSize: '0.75rem',
                fontWeight: 600,
                letterSpacing: '0.12em',
                textTransform: 'uppercase',
                color: C.vibrant,
                mb: 1.5,
              }}
            >
              About
            </Typography>
            <Typography
              component="h2"
              sx={{
                fontFamily: '"Outfit", system-ui, sans-serif',
                fontSize: { xs: '1.75rem', md: '2.25rem' },
                fontWeight: 700,
                color: C.indigo,
                lineHeight: 1.2,
                mb: 2.5,
              }}
            >
              Built on open-source,{' '}
              <Box component="span" sx={{ color: C.vibrant }}>customized for CUNY</Box>
            </Typography>
            <Typography sx={{ color: C.gray600, lineHeight: 1.75, mb: 2 }}>
              This platform is adapted from the{' '}
              <Link
                href="https://github.com/ASUCICREPO/PDF_Accessibility"
                target="_blank"
                rel="noopener"
                sx={{ color: C.vibrant, textDecoration: 'none', fontWeight: 500, '&:hover': { textDecoration: 'underline' } }}
              >
                PDF Accessibility tool
              </Link>{' '}
              originally built by the ASU Cloud Innovation Center, and
              customized by the CUNY AI Lab. With the Department of Justice's
              April 2024 updates to ADA regulations for digital content,
              accessible PDFs are more important than ever.
            </Typography>
            <Typography sx={{ color: C.gray600, lineHeight: 1.75 }}>
              This tool automates the remediation process, including structural
              tagging, alt-text generation, and accessibility reporting.
            </Typography>
          </Box>

          <Box sx={{ flex: 1 }}>
            <Typography
              sx={{
                fontFamily: '"Outfit", system-ui, sans-serif',
                fontSize: '0.75rem',
                fontWeight: 600,
                letterSpacing: '0.12em',
                textTransform: 'uppercase',
                color: C.vibrant,
                mb: 1.5,
              }}
            >
              The CUNY AI Lab
            </Typography>
            <Typography
              component="h2"
              sx={{
                fontFamily: '"Outfit", system-ui, sans-serif',
                fontSize: { xs: '1.75rem', md: '2.25rem' },
                fontWeight: 700,
                color: C.indigo,
                lineHeight: 1.2,
                mb: 2.5,
              }}
            >
              AI tools for{' '}
              <Box component="span" sx={{ color: C.vibrant }}>teaching and research</Box>
            </Typography>
            <Typography sx={{ color: C.gray600, lineHeight: 1.75, mb: 2 }}>
              The CUNY AI Lab is a faculty- and staff-led initiative at the
              Graduate Center, City University of New York, that develops and
              maintains AI tools for teaching, learning, and research. The Lab
              prioritizes privacy, transparency, and thoughtful integration of AI
              into academic work.
            </Typography>
            <Typography sx={{ color: C.gray600, lineHeight: 1.75 }}>
              We are guided by four principles: privacy by design, transparency
              through open-weight models, environmental accountability, and
              fostering AI literacy over AI dependency.
            </Typography>
          </Box>
        </Container>
      </Box>

      {/* ── Footer ── */}
      <Box
        sx={{
          borderTop: `1px solid ${C.border}`,
          backgroundColor: C.white,
          py: 3.5,
        }}
      >
        <Container maxWidth="lg">
          <Box
            sx={{
              display: 'flex',
              flexDirection: { xs: 'column', sm: 'row' },
              justifyContent: 'space-between',
              alignItems: { xs: 'flex-start', sm: 'center' },
              gap: 1.5,
            }}
          >
            <Typography sx={{ fontSize: '0.85rem', color: C.gray400 }}>
              Have questions?{' '}
              <Link
                href="mailto:ailab@gc.cuny.edu"
                sx={{ color: C.vibrant, textDecoration: 'none', fontWeight: 500, '&:hover': { textDecoration: 'underline' } }}
              >
                ailab@gc.cuny.edu
              </Link>
            </Typography>
            <Typography sx={{ fontSize: '0.85rem', color: C.gray400 }}>
              <Link
                href="https://ailab.gc.cuny.edu"
                target="_blank"
                rel="noopener"
                sx={{ color: C.vibrant, textDecoration: 'none', fontWeight: 500, '&:hover': { textDecoration: 'underline' } }}
              >
                ailab.gc.cuny.edu
              </Link>
            </Typography>
          </Box>
        </Container>
      </Box>

      {/* ── Remediation Dialog ── */}
      <Dialog
        open={openDialog}
        onClose={() => setOpenDialog(false)}
        aria-labelledby="remediation-dialog-title"
        PaperProps={{ sx: { borderRadius: '12px', maxWidth: '520px' } }}
      >
        <DialogTitle
          id="remediation-dialog-title"
          sx={{
            pr: 6,
            position: 'relative',
            fontFamily: '"Outfit", system-ui, sans-serif',
            fontWeight: 700,
            fontSize: '1.25rem',
            color: C.indigo,
            pb: 1,
          }}
        >
          How it works
          <IconButton
            aria-label="close"
            onClick={() => setOpenDialog(false)}
            sx={{ position: 'absolute', right: 8, top: 8, color: C.gray400 }}
          >
            <CloseIcon />
          </IconButton>
        </DialogTitle>

        <DialogContent dividers sx={{ borderColor: C.border }}>
          <Typography sx={{ color: C.gray600, mb: 3 }}>
            Three steps to an accessible PDF:
          </Typography>

          {[
            { title: 'Upload a Document', desc: 'Once you are logged in, select a PDF to upload for remediation.' },
            { title: 'Remediation', desc: 'AI-powered analysis fixes missing tags, incorrect reading order, alt text, and more.' },
            { title: 'Download', desc: 'Receive your remediated PDF and accessibility reports ready to share.' },
          ].map((item, i) => (
            <Box key={i} sx={{ display: 'flex', gap: 2, mb: 2.5 }}>
              <Box
                sx={{
                  width: 28,
                  height: 28,
                  borderRadius: '50%',
                  backgroundColor: '#e8f4fc',
                  color: C.vibrant,
                  fontSize: '0.8rem',
                  fontWeight: 700,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                  mt: 0.3,
                }}
              >
                {i + 1}
              </Box>
              <Box>
                <Typography sx={{ fontWeight: 600, color: C.indigo, fontSize: '0.9rem', mb: 0.3 }}>
                  {item.title}
                </Typography>
                <Typography variant="body2" sx={{ color: C.gray600 }}>
                  {item.desc}
                </Typography>
              </Box>
            </Box>
          ))}

          <Box sx={{ mt: 3, pt: 2.5, borderTop: `1px solid ${C.border}` }}>
            <Typography sx={{ fontWeight: 600, color: C.indigo, fontSize: '0.9rem', mb: 1.5 }}>
              Restrictions
            </Typography>
            {[
              'Each user is limited to 100 PDF document uploads.',
              'Documents cannot exceed 50 pages.',
              'Documents must be smaller than 500 MB.',
              'Do not upload documents containing sensitive information.',
              'Only PDF documents are accepted.',
              'Fillable forms and color contrast are not remediated.',
            ].map((text, i) => (
              <Typography key={i} variant="body2" sx={{ color: C.gray600, mb: 0.75, pl: 0.5 }}>
                {text}
              </Typography>
            ))}
          </Box>
        </DialogContent>
      </Dialog>
    </Box>
  );
};

export default LandingPage;
