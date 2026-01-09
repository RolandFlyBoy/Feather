"""
Domain Validation
=================

Email domain validation for multi-tenant applications.

In multi-tenant mode, tenants are identified by email domain.
Public email domains (Gmail, Outlook, etc.) are blocked to ensure
users sign up with their work email.

Functions
---------
- **extract_domain(email)**: Get domain from email address
- **is_public_email_domain(domain)**: Check if domain is a public provider
- **get_tenant_slug_from_domain(domain)**: Convert domain to tenant slug

Usage
-----
Validate email domain during signup::

    from feather.auth.domains import (
        extract_domain,
        is_public_email_domain,
        get_tenant_slug_from_domain
    )

    email = "bob@acme.com"
    domain = extract_domain(email)  # "acme.com"

    if is_public_email_domain(domain):
        # Reject signup with toast notification
        session["_pending_toast"] = {"message": "Please use your work email", "type": "error"}
        return None

    slug = get_tenant_slug_from_domain(domain)  # "acme"

Note:
    Public email blocking only applies in multi-tenant mode.
    Single-tenant apps (FEATHER_MULTI_TENANT=False) allow all domains.
"""

from typing import Set


# Common public email providers
# Users must sign up with work email in multi-tenant mode
PUBLIC_EMAIL_DOMAINS: Set[str] = {
    # Google
    "gmail.com",
    "googlemail.com",
    # Microsoft
    "outlook.com",
    "hotmail.com",
    "live.com",
    "msn.com",
    "hotmail.co.uk",
    "live.co.uk",
    # Yahoo
    "yahoo.com",
    "yahoo.co.uk",
    "yahoo.com.au",
    "ymail.com",
    "rocketmail.com",
    # Apple
    "icloud.com",
    "me.com",
    "mac.com",
    # Other major providers
    "aol.com",
    "protonmail.com",
    "proton.me",
    "tutanota.com",
    "zoho.com",
    "mail.com",
    "gmx.com",
    "gmx.net",
    "yandex.com",
    "fastmail.com",
    "hushmail.com",
    # Regional providers
    "qq.com",
    "163.com",
    "126.com",
    "sina.com",
    "sohu.com",
    "naver.com",
    "daum.net",
    "web.de",
    "t-online.de",
    "orange.fr",
    "free.fr",
    "libero.it",
    "virgilio.it",
    "rediffmail.com",
}


def extract_domain(email: str) -> str:
    """Extract domain from an email address.

    Args:
        email: Email address (e.g., "bob@acme.com").

    Returns:
        Domain part of the email, lowercased (e.g., "acme.com").

    Raises:
        ValueError: If email format is invalid.

    Example::

        extract_domain("Bob@Acme.com")  # "acme.com"
        extract_domain("user@sub.example.org")  # "sub.example.org"
    """
    if not email or "@" not in email:
        raise ValueError("Invalid email format")

    _, domain = email.rsplit("@", 1)
    return domain.lower().strip()


def is_public_email_domain(domain: str) -> bool:
    """Check if a domain is a public email provider.

    Args:
        domain: Email domain (e.g., "gmail.com").

    Returns:
        True if domain is a known public email provider.

    Example::

        is_public_email_domain("gmail.com")  # True
        is_public_email_domain("acme.com")   # False
    """
    return domain.lower() in PUBLIC_EMAIL_DOMAINS


def get_tenant_slug_from_domain(domain: str) -> str:
    """Convert an email domain to a tenant slug.

    Extracts the tenant name from the domain for use as a
    human-friendly tenant identifier.

    Args:
        domain: Email domain (e.g., "acme.com", "corp.acme.com").

    Returns:
        Slug suitable for tenant identification (e.g., "acme", "corp-acme").

    Example::

        get_tenant_slug_from_domain("acme.com")       # "acme"
        get_tenant_slug_from_domain("corp.acme.com")  # "corp-acme"
        get_tenant_slug_from_domain("my-company.io")  # "my-company"
    """
    # Remove common TLDs
    parts = domain.lower().split(".")

    # Handle common TLD patterns
    if len(parts) >= 2:
        # Remove last part (TLD like .com, .io, .org)
        parts = parts[:-1]

        # If still multiple parts (subdomain), join with hyphen
        if len(parts) > 1:
            return "-".join(parts)

        return parts[0]

    return domain.replace(".", "-")
