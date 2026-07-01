"""
Pytest bootstrap.

MYSTUDIO_COMPANY_ID / MYSTUDIO_USER_ID are required from .env (no code default,
so a misconfigured center can't silently hit Eastvale's data). Tests run without
a real .env, so provide Eastvale's known IDs here before settings is imported.
Runs before any test module, so settings + site modules see these values.
"""
import os

os.environ.setdefault("MYSTUDIO_COMPANY_ID", "578")
os.environ.setdefault("MYSTUDIO_USER_ID", "9901")

# Belt-and-suspenders: if settings was already imported by a plugin before this
# ran, patch the singleton directly so the values are guaranteed present.
from config.settings import settings  # noqa: E402

settings.MYSTUDIO_COMPANY_ID = settings.MYSTUDIO_COMPANY_ID or "578"
settings.MYSTUDIO_USER_ID = settings.MYSTUDIO_USER_ID or "9901"
