A generic document detailing design choices, threat models etc
---

## Multi-Factor Authentication (MFA)

- MFA is currently designed to use TOTP & recovery codes
  - A user can only have one TOTP setup at a time
    - Users must explicitly delete this to configure a new one
      - In order to delete MFA, the user must have authenticated with some form of MFA
  - A user can have a maximum of `EIGHT` recovery codes at once

#### Threat modeling

The MFA form takes username and password therefore any responses are allowed to 'leak' 'authenticated' messages because technically the user would be password authenticated any who

We also:
  Ask for username and password to save needing to check if sessions are MFA authenticated or not. By doing it all in one form it is easier for our existing authentication model

In saying that:
  We do render templates based on currently authed users if that extra context is available

Further to this:
  An authenticated session is created on `POST /mfa/totp` even though this route returns the registration details. This is because we need user details to check the code against, and *technically* MFA has been set up in the servers eyes.

  We accept the risk that this action soft locks accounts out. To help mitigate however, `POST /mfa/totp/confirm` will also redirect to the MFA deletion page if it fails