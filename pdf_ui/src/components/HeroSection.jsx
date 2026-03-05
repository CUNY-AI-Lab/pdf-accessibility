import React from 'react';

const HeroSection = () => {
  const heroSectionStyle = {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '80px 20px 20px 20px',
    textAlign: 'center'
  };

  const heroContentStyle = {
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
    alignItems: 'center',
    maxWidth: '480px'
  };

  const heroTitleStyle = {
    fontFamily: "'Geist', sans-serif",
    fontWeight: '600',
    fontSize: '28px',
    lineHeight: '36px',
    color: '#020617',
    margin: '0',
    whiteSpace: 'nowrap'
  };

  const heroDescriptionStyle = {
    fontFamily: "'Geist', sans-serif",
    fontWeight: '400',
    fontSize: '20px',
    lineHeight: '30px',
    color: '#1e293b',
    margin: '0',
    maxWidth: '480px',
    width: '100%'
  };

  return (
    <div style={heroSectionStyle}>
      <div style={heroContentStyle}>
        <h1 style={heroTitleStyle}>PDF Remediation</h1>
        <p style={heroDescriptionStyle}>
          Artificial intelligence-powered open-source solution designed to
          improve digital accessibility for everyone.
        </p>
      </div>
    </div>
  );
};

export default HeroSection;
