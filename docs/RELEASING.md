# Releasing Harpy

Harpy releases are wheel and source archives attached to a GitHub Release.
They are not published to PyPI.

## Prepare the version

1. Create a pull request that updates `project.version` in `pyproject.toml`.
   Use `X.Y.Z` for a stable release or a PEP 440 prerelease such as
   `X.Y.Zrc1`.
2. Run `uv lock` and commit the resulting `uv.lock` change when it changes.
3. Run `make check`.
4. Merge the pull request after its required check passes.

`pyproject.toml` is the only version literal. `harpy.__version__` reads the
installed package metadata.

## Create the release

In GitHub, open **Actions → release → Run workflow**:

- select the `main` branch;
- enter the exact version from `pyproject.toml`, without a leading `v`;
- select **prerelease** only for an `a`, `b`, or `rc` version.

The equivalent CLI command is:

```bash
gh workflow run release.yml --ref main \
  -f version=0.1.0 \
  -f prerelease=false
```

The workflow rejects non-`main` commits, mismatched or malformed versions, and
existing tags. It runs `make check`, builds one wheel and one source archive,
attests both artifacts, creates `v<version>`, and generates release notes.

## Verify

```bash
gh run watch
gh release view v0.1.0
mkdir -p dist
gh release download v0.1.0 --dir dist
gh attestation verify dist/* --repo NDobrev/harpy
```

Install the wheel in a clean environment and run `harpy --help` before
announcing the release. Harpy still requires `git`, authenticated `gh`, and,
for semantic analysis, `cursor-agent`.

## Failure recovery

If the workflow fails before creating the GitHub Release, fix the cause through
a pull request and dispatch it again. If the release or tag already exists, do
not replace it; prepare a new patch or prerelease version.
