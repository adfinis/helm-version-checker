# Helm Chart Version Checker

This tool automatically checks for new Helm chart versions and creates GitHub issues for available updates.

## Usage

### Standalone (Local Execution)

1. **Install Dependencies**:

    ```bash
    pip install -r scripts/requirements.txt
    ```

2. **Set Environment Variables**: The script requires two **environment variables** to function correctly.

      * `GITHUB_REPOSITORY`: The owner and repository name (e.g., `my-org/my-repo`).
      * `GITHUB_TOKEN`: A **Personal Access Token (PAT)** with permissions to read the repository and write issues. You can create one at `Settings > Developer settings > Personal access tokens`.

3. **Run the Script**: Execute the script from the root of the repository.

    ```bash
    GITHUB_REPOSITORY="owner/repo" GITHUB_TOKEN="your_personal_access_token" python scripts/version_checker.py
    ```

-----

### Inside GitHub Actions

```yaml
# .github/workflows/version-check.yml
name: Helm Version Checker

on:
  workflow_dispatch:
  schedule:
    - cron: '0 8 * * *' # Runs daily at 08:00 UTC

jobs:
  check_versions:
    name: Check for new Helm chart versions
    runs-on: ubuntu-latest
    permissions:
      contents: read # To check out the repository's code
      issues: write    # Required to create GitHub issues

    steps:
      - name: Checkout Repository
        uses: actions/checkout@v4

      - name: Run Helm Version Checker
        uses: adfinis/helm-version-checker@v2.0.1
        with:
          # The GITHUB_TOKEN is required to create issues.
          token: ${{ secrets.GITHUB_TOKEN }}

          # --- Optional: Customize paths ---
          # Path to the directory containing your app groups.
          # charts_path: './charts'

          # Path to the maintainers file.
          # maintainers_file: 'MAINTAINERS.yaml'
```

## Configure `MAINTAINERS.yaml` to assign issues

This file, located in your repository's root, maps chart groups to GitHub usernames. Keys must match the *apps names inside your `charts/` directory (e.g., `monitoring-apps`). Use `default` as a fallback.

Example `MAINTAINERS.yaml`:

```yaml
    # Assignees for charts in 'charts/monitoring-apps'
    monitoring-apps:
      - 'github-username-1'
      - 'github-username-2'

    # Fallback assignees
    default:
      - 'Xelef2000'
```

## TODO
- [] Branch and Tag Protections rules on the repo
- [] Type Hints
- [] PyTest framework
- [] Automated Tests