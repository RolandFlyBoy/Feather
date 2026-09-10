# Changelog

Releases are tags (`vX.Y.Z`) published to PyPI by `.github/workflows/publish.yml`
(trusted publishing, no tokens). See "Releasing" in CLAUDE.md.

## Unreleased

## 0.9.5 (2026-09-10)

First release published through GitHub Actions. Everything below came out of
running OpenCVNGN on the framework in production.

Security
- `?next` on the Google OAuth routes only accepts site-relative paths.
- Logout clears the whole session and, since 0.9.5, does so before
  `logout_user()` so the remember-me cookie is actually deleted (previously
  the next request signed the user straight back in).
- `/health` no longer echoes database error text.
- Cookie flags on the session and remember cookies; configurable
  `FEATHER_PERMISSIONS_POLICY` (default denied camera/microphone, which broke
  in-browser recording).
- Google sign-in requires a verified email; emails are masked in logs.
- Local storage backend is contained to its upload directory; GCS signed URLs
  default to 15 minutes (V4).

Jobs
- `JOB_SERIALIZER=json` for RQ (opt-in; pickle payloads are code execution
  for anyone who can reach Redis).
- Thread backend accepts `job_timeout` (what `@job(timeout=...)` passes)
  instead of forwarding it to the job function.

Other
- `.env` is loaded from the current working directory, not the framework's.
