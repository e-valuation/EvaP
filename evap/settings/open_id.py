from evap.settings_resolver import required

ACTIVATE_OPEN_ID_LOGIN = required()

# replace 'example.com', OIDC_RP_CLIENT_ID and OIDC_RP_CLIENT_SECRET with real values in localsettings when activating
OIDC_RENEW_ID_TOKEN_EXPIRY_SECONDS = 60 * 60 * 24 * 7  # one week
OIDC_RP_SIGN_ALGO = "RS256"
OIDC_USERNAME_ALGO = ""
OIDC_RP_SCOPES = "openid email profile"

OIDC_RP_CLIENT_ID = "evap"
OIDC_RP_CLIENT_SECRET = "evap-secret"  # nosec

OIDC_OP_AUTHORIZATION_ENDPOINT = "https://example.com/auth"
OIDC_OP_TOKEN_ENDPOINT = "https://example.com/token"  # nosec
OIDC_OP_USER_ENDPOINT = "https://example.com/me"
OIDC_OP_JWKS_ENDPOINT = "https://example.com/certs"

# Mapping of email domain transition which users may undergo during the lifetime of their account.
# Given an item (k, v) of the mapping, if an account with domain k would be created through OpenID,
# but an account with the same name at domain v exists, the existing account is migrated to the
# domain k instead.
OIDC_EMAIL_TRANSITIONS: dict[str, str] = {
    "institution.example.com": "student.institution.example.com",
}
