# DATMM consolidated research-graph explorer

> Upload fix (v0.1.1): repository files are now transferred with a normal Git push. Python uses its standard library; the Git executable must also be installed. The token stays in memory and a temporary child-process environment, never in a URL or saved credential file. This candidate preserves the previously frozen browser and selected exports.

A notebook for assembling a source-attributed research graph and a self-contained HTML explorer. The supplied snapshot contains 3,858 nodes and 7,667 evidence edges; these are counts inspected in the embedded payload, not independently validated scientific results.

## Use the supplied browser

Open `docs/index.html` in a desktop browser. Its graph and Plotly library are embedded; source links open external websites when clicked. The explorer preserves the original evidence layers, limitations, and application-specific Clinical study extension.

For a public website, configure GitHub Pages to deploy from `main` and `/docs`. The website shows the current branch version. For a fixed historical snapshot, download the ZIP from a specific GitHub release.

## Run the notebook

Open `notebooks/DATMM_Consolidated_Acquisition_Architecture_Explorer.ipynb` in Google Colab or Jupyter. The first code cell installs pinned direct dependencies. Colab offers optional Drive persistence; local Jupyter does not mount Drive. Read the acquisition configuration before running all cells: the normal `cache_first` mode can make requests to source services when caches are absent. To request no new source data, use `MODE='offline'`.

The original acquisition caches/checkpoint and source CSV were not supplied with this package. The embedded cohort is present, but an offline rebuild from it alone will not reproduce the enriched HTML snapshot. No fresh acquisition was used to produce this release starter.

## Version and publish

Read [RELEASE_GUIDE.md](RELEASE_GUIDE.md). The notebook's final optional cell has three actions:

- `off`: no packaging, credential access, or GitHub request.
- `prepare`: freeze explicit files, strip notebook outputs, reset the publication action to `off`, create SHA-256 inventories and a release ZIP. No network requests.
- `publish`: publish that already frozen package to a pre-existing public GitHub repository after a typed repository/version confirmation.

Authentication uses a fine-grained personal access token supplied through a Colab secret, environment variable, or hidden prompt named `GITHUB_DATMM`. This is not an SSH key. The repository needs Contents read/write permission. The publisher does not install or modify GitHub Actions workflows.

Publication uploads the reviewed files as one commit, makes a tag pointing to that commit, creates a draft release, uploads and verifies four assets, then publishes the release. It never force-updates a branch or overwrites an existing tag. GitHub Pages deployment runs separately if configured.

## Repository contents

| Path | Purpose |
|---|---|
| `notebooks/` | Output-cleared notebook with optional publishing cell |
| `docs/index.html` | Supplied browser bytes, unchanged in this starter |
| `scripts/datmm_release.py` | Python packaging, native Git transport, and GitHub release API client |
| `tests/test_release.py` | Offline packaging and simulated GitHub tests |
| `provenance/supplied-files.json` | Original attachment hashes and evidence limitations |
| `requirements.txt` | Pinned direct notebook dependencies; not an original-run lockfile |
| `THIRD_PARTY_NOTICES.md` | Bundled library notices and project-license decision |
| `dist/` | Local, ignored release builds and resume receipts |

Run the publisher tests from the project root:

```sh
python -m unittest discover -s tests -v
```

No license has been assigned to the DATMM project code or embedded source metadata. Before inviting reuse, choose the appropriate license and attribution with the relevant owner. Add an actual `LICENSE` file; the publisher includes it when present. Plotly's upstream licenses are preserved separately and do not license the DATMM project or source records.

This project preserves source associations; it does not establish reuse, causal funding, award-year resolution, or an independently validated coverage metric. Refer to source coverage and retrieval limitations when interpreting missing paths.
