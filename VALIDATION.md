# Validation of the upload repair

Prepared 2026-10-23. The repair passed 26 automated tests under Python 3.12.14 with Git 2.51.1. Tests cover real local Git transfer of a 48,000,016-byte HTML fixture, exact byte recovery, preservation of unrelated files, rejection of a concurrent branch update, credential-helper cleanup, redacted HTTP diagnostics, interrupted push/upload recovery, and the existing packaging checks. The GitHub release API is simulated in those tests.

The repair installer was also applied locally to the supplied 44 MB snapshot. The resulting candidate was checksum-verified; its browser bytes match the original candidate and the original build remains unchanged. This does not establish success of an authenticated GitHub push, a release upload, or Pages deployment.

No fresh source acquisition, independent scientific verification, or full notebook dependency installation was performed. The project-license and third-party-notice limitations in THIRD_PARTY_NOTICES.md still apply. Original validation records remain in the preserved original frozen candidate.

The publisher uses Python 3.10 or later plus the Git executable. Repeat the tests after modifying code; these results apply to the delivered repair.
