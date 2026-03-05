// import React, { useState, useEffect } from 'react';
// import { Box, TextField, Button, Typography, Link } from '@mui/material';

// const UpdateAdobeAPICredentials = () => {
//   const [clientId, setClientId] = useState('');
//   const [clientSecret, setClientSecret] = useState('');
//   const [loading, setLoading] = useState(false);
//   const [errorMessage, setErrorMessage] = useState('');
//   const [showFields, setShowFields] = useState(false);

//   useEffect(() => {
//     // Delay the rendering of the input fields
//     setTimeout(() => {
//       setShowFields(true);
//     }, 100);
//   }, []);

//   const handleUpdate = async () => {
//     setErrorMessage('');

//     const payload = {
//       client_id: clientId,
//       client_secret: clientSecret,
//     };

//     const apiUrl = process.env.REACT_APP_API_GATEWAY_INVOKE_URL;

//     try {
//       setLoading(true);
//       const response = await fetch(apiUrl, {
//         method: 'POST',
//         headers: {
//           'Content-Type': 'application/json',
//         },
//         body: JSON.stringify(payload),
//       });

//       if (!response.ok) {
//         const errorText = await response.text();
//         throw new Error(`Failed to update credentials: ${errorText}`);
//       }

//       alert('Credentials successfully updated in AWS Secrets Manager!');
//     } catch (error) {
//       console.error('Error:', error);
//       setErrorMessage('Failed to update credentials: ' + error.message);
//     } finally {
//       setLoading(false);
//     }
//   };

//   const handleFocus = (e) => {
//     e.target.removeAttribute('readonly');
//   };

//   return (
//     <Box
//       sx={{
//         width: 250,
//         margin: '0 auto',
//         textAlign: 'center',
//         padding: '20px',
//       }}
//       role="form"
//       aria-labelledby="form-title"
//     >
//       <Typography variant="h6" gutterBottom id="form-title">
//         Adobe API Credentials
//       </Typography>

//       <Link
//         href="https://acrobatservices.adobe.com/dc-integration-creation-app-cdn/main.html?api=pdf-services-api"
//         target="_blank"
//         rel="noopener"
//         sx={{ display: 'block', marginBottom: 2 }}
//         aria-label="Link to Adobe API credentials and usage documentation"
//       >
//         Click here to get Adobe API credentials and usage
//       </Link>

//       <form autoComplete="off" aria-labelledby="form-title">
//         {showFields && (
//           <>
//             <label htmlFor="client-id" className="visually-hidden">Client ID</label>
//             <TextField
//               label="Client ID"
//               id="client-id"
//               name="clientIdField"
//               value={clientId}
//               onChange={(e) => setClientId(e.target.value)}
//               fullWidth
//               autoComplete="off"
//               onFocus={handleFocus}
//               InputProps={{
//                 readOnly: true,
//               }}
//               sx={{ marginBottom: 2 }}
//               aria-required="true"
//             />

//             <label htmlFor="client-secret" className="visually-hidden">Client Secret</label>
//             <TextField
//               label="Client Secret"
//               id="client-secret"
//               name="clientSecretField"
//               value={clientSecret}
//               onChange={(e) => setClientSecret(e.target.value)}
//               fullWidth
//               onFocus={handleFocus}
//               InputProps={{
//                 readOnly: true,
//               }}
//               sx={{ marginBottom: 2 }}
//               aria-required="true"
//             />
//           </>
//         )}

//         {errorMessage && (
//           <Typography
//             variant="body2"
//             color="error"
//             sx={{ marginBottom: 2 }}
//             role="alert"
//             aria-live="assertive"
//           >
//             {errorMessage}
//           </Typography>
//         )}

//         <Button
//           variant="contained"
//           color="primary"
//           onClick={handleUpdate}
//           disabled={!clientId || !clientSecret || loading}
//           aria-label="Update Adobe API Credentials"
//         >
//           {loading ? 'Updating...' : 'Update'}
//         </Button>
//       </form>
//     </Box>
//   );
// };

// export default UpdateAdobeAPICredentials;
