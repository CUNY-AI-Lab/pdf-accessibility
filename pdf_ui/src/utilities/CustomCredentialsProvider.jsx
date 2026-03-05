import { CognitoIdentity } from '@aws-sdk/client-cognito-identity';
import { IndentityPoolId,region } from './constants';

const cognitoidentity = new CognitoIdentity({
  region: region,
});

class CustomCredentialsProvider {
  constructor() {
    this.federatedLogin = undefined;
  }

  loadFederatedLogin(login) {
    this.federatedLogin = login;
  }

  async getCredentialsAndIdentityId(getCredentialsOptions) {
    try {
      const getIdResult = await cognitoidentity.getId({
        IdentityPoolId: IndentityPoolId,
        Logins: { [this.federatedLogin.domain]: this.federatedLogin.token },
      });

      const cognitoCredentialsResult = await cognitoidentity.getCredentialsForIdentity({
        IdentityId: getIdResult.IdentityId,
        Logins: { [this.federatedLogin.domain]: this.federatedLogin.token },
      });

      const credentials = {
        credentials: {
          accessKeyId: cognitoCredentialsResult.Credentials?.AccessKeyId,
          secretAccessKey: cognitoCredentialsResult.Credentials?.SecretKey,
          sessionToken: cognitoCredentialsResult.Credentials?.SessionToken,
          expiration: cognitoCredentialsResult.Credentials?.Expiration,
        },
        identityId: getIdResult.IdentityId,
      };
      return credentials;
    } catch (e) {
      console.log('Error getting credentials: ', e);
    }
  }

  clearCredentialsAndIdentityId() {
    // Implement clearing logic here if needed
  }
}



export default CustomCredentialsProvider;
