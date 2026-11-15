"""Generate cryptographically strong placeholder-free secrets for HydraJob .env.

Usage:
    python supporting_codes/generate_secrets.py

Prints ready-to-paste environment variable lines to stdout without writing
to disk, so secrets are never accidentally committed.
"""

import secrets


def main() -> None:
    """Generate and print strong random secrets for .env configuration."""
    app_secret_key = secrets.token_urlsafe(48)
    app_api_key = secrets.token_urlsafe(32)
    postgres_password = secrets.token_urlsafe(24)
    n8n_encryption_key = secrets.token_hex(32)

    print("# Paste these generated secrets into your local .env (never commit .env)")
    print(f"APP_SECRET_KEY={app_secret_key}")
    print(f"APP_API_KEY={app_api_key}")
    print(f"POSTGRES_PASSWORD={postgres_password}")
    print(f"N8N_ENCRYPTION_KEY={n8n_encryption_key}")


if __name__ == "__main__":
    main()
