# Changelog

## 0.1.1 — repository upload repair

- Replace REST base64 blob creation with native Git object creation and non-force push.
- Preserve server error messages while redacting credentials.
- Add real local Git integration tests for a 48 MB file, concurrent updates, and credential handling.
- Preserve the prior candidate browser and explicit exports without new acquisition.


## 0.1.0 — initial release candidate

- Package the supplied notebook and exact supplied HTML snapshot.
- Clear stored notebook outputs and make Drive/download behavior Colab-aware.
- Pin direct notebook dependencies; do not assert reconstruction of the original environment.
- Add explicit offline release preparation, per-file SHA-256 manifests, and an opt-in publisher using GITHUB_DATMM.
- Record original input hashes and missing acquisition evidence.
- Add offline packaging and simulated GitHub tests.

No fresh source acquisition or independent scientific validation was performed for this package. This entry describes the prepared candidate; it does not claim a public release has occurred.
