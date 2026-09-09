# Development and Testing

## Primary Development Commands

To check and resolve linting issues in the codebase, run:

```console
uv run ruff check --fix
```

To check and resolve formatting issues in the codebase, run:

```console
uv run ruff format
```

To check the unit tests in the codebase, run:

```console
uv run pytest
```

To check the typing in the codebase, run:

```console
uv run mypy
```

To generate a code coverage report after testing locally, run:

```console
uv run coverage html
```

To check the lock file is up to date:

```console
uv lock --check
```

The lock file is resolved without any user-level uv configuration, which is how CI resolves it. If your `~/.config/uv/uv.toml` sets `exclude-newer` or similar, uv will want to re-resolve and will rewrite `uv.lock`. Set `UV_NO_CONFIG=1` in your shell while working here to match CI; the environment variable matters because `poe` runs each task through its own `uv run`, which a `--no-config` flag on the outer command does not reach.

## Shortcut Task Commands

###### For Running Individual Checks

```console
uv run poe check-format
uv run poe check-lint
uv run poe check-tests
uv run poe check-typing
```

###### For Running All Checks

```console
uv run poe check-all
```

###### For Running Individual Fixes

```console
uv run poe fix-format
uv run poe fix-lint
```

###### For Running All Fixes

```console
uv run poe fix-all
```

###### For Running All Fixes and Checks

```console
uv run poe fix-and-check-all
```

## Trying a change against a real report

Point MultiQC at any directory of QC outputs with a config that has a `sample_pivot` block. The
plugin is picked up automatically once the package is installed in the same environment:

```console
uv run multiqc --config my_config.yml ./path-to-data
```

## Creating a release on PyPI

> [!NOTE]
> This project follows [Semantic Versioning](https://semver.org/), aka SemVer. In brief:
>
> - MAJOR version when you make incompatible API changes
> - MINOR version when you add functionality in a backwards compatible manner
> - PATCH version when you make backwards compatible bug fixes

> [!IMPORTANT]
> Consider editing the changelog if there are any errors or necessary enhancements.

1. Clone the repository, ensure you are on the main branch, and that the working directory is clean.
2. Check out a new branch to prepare the library for release.
3. Bump the version of the library to the desired SemVer, e.g.:
    ```console
    # Increment the minor segment
    uv version --bump minor

    # Update to a specific version number
    uv version 0.2.0
    ```
4. Commit the version bump changes with a Git commit message like `chore(release): bump to #.#.#`.
5. Push the commit, open a PR, ensure tests pass, and seek reviews.
6. Squash merge the PR into the `main` branch.
7. Tag the new commit on the main branch with the bumped version number.

> [!WARNING]
> The tag **must** be a valid SemVer version number and **must** match the version set in (3). The [publishing GitHub Action](.github/workflows/publish_multiqc_pivot.yml) is activated by a new tag on the `main` branch containing a valid SemVer version.

GitHub Actions will take care of the remainder of the deployment and release process:

1. Unit tests will be re-run.
2. A source distribution will be built.
3. A wheel distribution will be built.
4. Assets will be deployed to PyPI with the new version.
5. A [Conventional Commit](https://www.conventionalcommits.org/en/v1.0.0/)-aware changelog will be drafted.
6. A GitHub release will be created with the new version tag and the drafted changelog.
