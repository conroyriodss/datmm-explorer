# Publish DATMM on GitHub

## This repaired candidate

The original frozen build remains at `/content/datmm-release/dist/v0.1.0`. The repaired project is `/content/datmm-release-gitfix`. The candidate is `v0.1.1`. In the existing notebook publication cell, set `PROJECT_DIR` to the repaired directory, `VERSION = "v0.1.1"`, and `ACTION = "publish"`. Do not rerun acquisition or prepare merely to apply this transport repair. The prepared package is already available for review. This step has not read a token or contacted GitHub.


## 1. Create the repository

In GitHub, create a repository such as `datmm-explorer` under the intended account or organization. Choose **Public**, initialize it with a README, and use `main` as its default branch. Initialization matters: the publisher needs an existing branch. If your organization requires pull requests or restricts direct branch updates, use that required workflow; do not disable its rules for this notebook.

The publisher updates its explicit file paths and preserves other repository files. It does not delete retired exports from previous versions. Remove any obsolete repository files in a separate reviewed commit. The release ZIP and manifest are the authoritative inventory for each packaged version.

Choose the project license based on actual ownership and reuse rights; this package does not invent a federal ownership determination, clearance, or license. Adding a public repository does not resolve those questions. The embedded cohort and HTML contain source metadata as well as code, so include them in your publication review.

## 2. Create GITHUB_DATMM

In GitHub, open **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**.

- Token name: `GITHUB_DATMM` (a label; the secret name must separately match).
- Resource owner: the account or organization owning this repository.
- Repository access: **Only select repositories**, then select this repository.
- Repository permissions: **Contents → Read and write**. Metadata read access accompanies repository access.
- Set an expiration. An organization may require token approval or restrict use.

This is a personal access token, not an SSH key. No Workflows permission is needed for the files in this package. Do not paste the token into chat, a notebook source cell, an output, or a Git URL.

In Colab, open the key-shaped **Secrets** panel, add a secret named `GITHUB_DATMM`, paste the token as its value, and allow this notebook to access it. Outside Colab, use a runtime environment variable with that name or accept the hidden prompt. Merely adding a GitHub repository Actions secret does not make it available inside Colab.

## 3. Put the package in the runtime

Download and unzip `datmm-github-release-starter.zip` on your computer. It contains a `datmm-release` directory. Open its notebook in Colab or Jupyter.

**Colab:** the notebook editor and runtime filesystem are separate. Opening an `.ipynb` does not copy its companion files into `/content`. In the final optional publishing cell set `ACTION = "prepare"`. If `/content/datmm-release` is missing, that cell asks you to upload the starter ZIP and extracts it safely. It can prepare the supplied snapshot without running any acquisition cells.

**Local Jupyter:** keep the extracted directory together. The cell locates it when started in the project root or `notebooks/`; otherwise set `PROJECT_DIR` explicitly.

The first release can use the notebook already in the package. If you edit the notebook in the Colab editor, **File → Download → Download .ipynb**, upload that saved file into the runtime using its Files panel, and set `NOTEBOOK_SOURCE` to its full runtime path. Publishing cannot capture unsaved editor changes. The selected notebook path is printed before preparing. Releasing a notebook different from the one that generated an HTML file is permitted for this starter but is not evidence of an exact computational rerun.

## 4. Prepare v0.1.1 offline

In the final cell set:

```python
ACTION = "prepare"
VERSION = "v0.1.1"
REPOSITORY = "YOUR_ACCOUNT/datmm-explorer"
```

Leave `BROWSER_SOURCE = None` to package the supplied `docs/index.html`. For a new acquisition run set it explicitly to, for example, `/content/datmm_next/consolidated/output/datmm_consolidated_browser.html`. The publisher never silently replaces the supplied snapshot with the latest runtime output.

Include associated files only if they actually exist and are intended for publication:

```python
EXTRA_FILES = {
    "exports/checks.csv": "/content/datmm_next/consolidated/output/checks.csv",
    "exports/manifest.json": "/content/datmm_next/consolidated/output/manifest.json",
    "exports/class_coverage.csv": "/content/datmm_next/consolidated/output/class_coverage.csv",
    # Add raw_triples.json or other evidence files explicitly if appropriate.
}
```

These examples are not claims that those files were supplied. The default mapping is empty. Directories, Drive trees, checkpoint ZIPs, and credential files are not automatically included. HTTP logs can contain request metadata; review them before selecting one. Each file must be under the publisher's 95,000,000-byte limit; large data archives need a separately designed asset workflow.

Set `RELEASE_NOTES` to describe the actual changes and whether the snapshot came from a new acquisition, a cached rebuild, or repackaging. Run the cell. Inspect `dist/v0.1.1/package/release-manifest.json`, the stripped notebook, browser, and any extra files. `SHA256SUMS.txt` hashes the packaged files; the ZIP has its own `.sha256` sidecar. The preparation step does not ask for a token or access GitHub.

The starter pins direct dependencies to requests 2.32.5, pandas 2.2.3, Plotly 5.24.1, and IPython 8.37.0. This is a proposed execution environment, not a reconstruction of the original run's environment. For a new evidentiary run, preserve the actual resolved environment and source responses alongside the run outputs. A file hash proves byte identity, not correctness, licensing, or completeness.

## 5. Publish the prepared package

Set `ACTION = "publish"` and run the same cell. The cell verifies the frozen package, asks you to type `YOUR_ACCOUNT/datmm-explorer@v0.1.1`, then reads `GITHUB_DATMM`.

The publisher:

1. Checks that the target repository is public, initialized, and not archived.
2. Uploads the frozen files, creates one commit, and advances the selected branch without forcing it.
3. Creates `v0.1.1` at that exact commit SHA.
4. Creates a draft release and attaches the release ZIP, ZIP checksum, manifest, and file checksum list.
5. Checks each uploaded asset's GitHub SHA-256 digest and size, then publishes the release.

Files become public when the public branch is updated, even while the release is still a draft. If Pages is enabled, that branch update can also deploy the website before asset upload completes. Review before using `publish`; draft release status does not make repository files private.

The script does not create the repository, change visibility, enable Pages, change branch protections, or overwrite old versions. It uses a native Git push for repository files and GitHub's API for release management. No token is stored in a Git URL or configuration file.

## 6. Enable the website once (optional)

After the first commit, open the repository's **Settings → Pages**. Under **Build and deployment**, select **Deploy from a branch**, then **main** and **/docs**, and save. GitHub displays the actual site URL, usually `https://YOUR_ACCOUNT.github.io/datmm-explorer/`.

Wait for the Pages job in **Actions** to succeed and open the displayed URL. Subsequent updates to `docs/index.html` on this branch will update the website. The website is a moving view; cite a versioned GitHub release and commit when a fixed snapshot matters.

## 7. Publish updates

Edit the notebook/source files, run acquisition or rebuild only as intended, update `CHANGELOG.md`, choose a new version, and set explicit notebook/browser/output paths. Use `prepare`, inspect the frozen files, then `publish`.

Suggested convention: `v0.1.1` for packaging or bug fixes; `v0.2.0` for meaningful feature or dataset-snapshot changes; `v1.0.0` when you consider the interface ready for a stable release. Write the snapshot change in the release notes; a version number alone does not describe the evidence.

Keep previous tags and assets fixed. The script rejects version reuse with different package bytes. GitHub administrators may still be able to change ordinary tags or releases; this script's refusal is not repository-enforced immutability. Configure suitable repository rules if stronger enforcement is needed.

## Interruptions and limits

- Keep `dist/<version>/publish-state.json` and the frozen package after interruption. Rerun `publish` for that exact build. This receipt has commit/release identifiers, not the token.
- An expired token can be replaced in the secret store and the same frozen build retried.
- HTTP 403/404: check owner, selected repository, token approval, and Contents permission. An empty repository has no `main` reference; initialize it first.
- A concurrently advanced or protected branch is not force-updated. Inspect the current repository state and use a new build or the organization's pull-request workflow.
- If the runtime is lost after a partial publication, inspect the remote tag, draft release, and files before choosing a new version. The script refuses to adopt an existing tag without its local matching receipt. Recover manually rather than deleting history blindly.
- If an asset is incomplete or its digest cannot be verified, publication stops. Inspect the draft and failed asset. No existing asset is deleted automatically.
- The credential pattern check is a basic safeguard, not a complete secret or confidentiality audit. Notebook outputs and nonessential metadata are removed automatically.
- Offline tests cover packaging and simulated GitHub responses. No authenticated GitHub write, real token, or live Pages deployment was used to validate this starter.

## GitHub documentation

- [Fine-grained personal access tokens](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
- [Git database: blobs](https://docs.github.com/en/rest/git/blobs), [trees](https://docs.github.com/en/rest/git/trees), [commits](https://docs.github.com/en/rest/git/commits), [references](https://docs.github.com/en/rest/git/refs)
- [Release API](https://docs.github.com/en/rest/releases/releases) and [release assets](https://docs.github.com/en/rest/releases/assets)
- [GitHub Pages publishing source](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)
