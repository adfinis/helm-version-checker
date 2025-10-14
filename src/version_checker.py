#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
This script checks for new versions of Helm charts defined in various values.yaml
files and creates GitHub issues if a new version is available.

Requirements:
- Python 3.6+
- requests: pip install requests
- PyYAML:   pip install pyyaml
"""

import argparse
import os
import sys
import json
from pathlib import Path
from typing import List, Optional, Dict, Any, TypedDict
import requests
import yaml

REPO: Optional[str] = os.getenv("GITHUB_REPOSITORY")
API_URL: str = "https://api.github.com"
CHARTS_PATH: str = "charts"

class AppDetails(TypedDict):
    repoURL: str
    targetRevision: str
    chart: str

def get_maintainers(file_path: str, app_group: str) -> List[str]:
    """Loads maintainers from the YAML file for a specific app group."""
    try:
        with open(file_path, 'r') as f:
            maintainers_data: Dict[str, List[str]] = yaml.safe_load(f)
            assignees: List[str] = maintainers_data.get(app_group, [])
            if not assignees:
                print(f"No specific maintainers found for '{app_group}'. Looking for 'default' maintainers.")
                assignees = maintainers_data.get('default', [])
            return assignees

    except FileNotFoundError:
        print(f"Error: Maintainers file not found at {file_path}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"Error reading or parsing maintainers file: {e}", file=sys.stderr)
        return []

def get_latest_helm_version(repo_url: Optional[str], chart_name: str, repoPath: str) -> Optional[str]:
    """Fetches the latest chart version from a Helm repository's index.yaml."""
    if not repo_url or repo_url == "null":
        print(f"Warning: Invalid or missing repoURL for chart '{chart_name}'. Skipping.", file=sys.stderr)
        return None

    index_url: str = f"{repo_url.rstrip('/')}/index.yaml"
    try:
        response: requests.Response = requests.get(index_url, timeout=10)
        response.raise_for_status()
        index_data: Any = yaml.safe_load(response.content)
        latest_version: str = index_data['entries'][chart_name][0]['version']
        return latest_version
    except requests.exceptions.RequestException as e:
        print(f"Error: Failed to download index.yaml from {index_url}. Details: {e}", file=sys.stderr)
    except (KeyError, IndexError, TypeError) as e:
        print(f"Error: Could not parse version for chart '{chart_name}' from {index_url}. Details: {e}", file=sys.stderr)
    return None

def check_existing_issue(repo: str, token: str, title: str) -> Optional[int]:
    """
    Checks if a GitHub issue with the exact same title already exists,
    handling pagination and providing debug output.
    """
    headers: Dict[str, str] = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    params: Dict[str, Any] = {"state": "open", "per_page": 100}
    url: Optional[str] = f"{API_URL}/repos/{repo}/issues"

    page_num: int = 1
    while url:
        try:
            response: requests.Response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            issues: List[Dict[str, Any]] = response.json()

            for issue in issues:
                if issue.get("title") == title:
                    return issue.get("number")

            if 'next' in response.links:
                url = response.links['next']['url']
                params = {}
                page_num += 1
            else:
                url = None

        except requests.exceptions.RequestException as e:
            error_details = e.response.text if e.response else str(e)
            print(f"Error checking for existing GitHub issues: {error_details}", file=sys.stderr)
            return None

    return None

def create_github_issue(repo: str, token: str, title: str, body: str, assignees: List[str]) -> None:
    """Creates a new GitHub issue."""
    headers: Dict[str, str] = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    payload: Dict[str, Any] = {
        "title": title,
        "body": body,
        "assignees": assignees
    }
    issues_url: str = f"{API_URL}/repos/{repo}/issues"
    try:
        response: requests.Response = requests.post(issues_url, headers=headers, data=json.dumps(payload), timeout=10)
        response.raise_for_status()
        print(f"Successfully created issue '{title}' and assigned to: {', '.join(assignees)}")

    except requests.exceptions.RequestException as e:
        if e.response is not None:
            error_details = e.response.text
        else:
            error_details = str(e)
        
        print(f"Error creating GitHub issue '{title}': {error_details}", file=sys.stderr)

def parse_args() -> argparse.Namespace:
    """Parses command-line arguments."""
    parser = argparse.ArgumentParser(description="Helm Version Checker")
    parser.add_argument("--token", required=True, help="GitHub token")
    parser.add_argument("--charts-path", default="./charts", help="Path to charts directory")
    parser.add_argument("--maintainers-file", default="MAINTAINERS.yaml", help="Path to maintainers file")
    return parser.parse_args()

def main() -> None:
    """Main execution function."""
    args: argparse.Namespace = parse_args()

    github_token: str = args.token
    maintainers_file_path: str = args.maintainers_file
    charts_dir_path: str = args.charts_path

    if not REPO or not github_token:
        print("Error: GITHUB_REPOSITORY environment variable and --token argument must be set.", file=sys.stderr)
        sys.exit(1)

    if not Path(maintainers_file_path).is_file():
        print(f"Error: {maintainers_file_path} not found.", file=sys.stderr)
        sys.exit(1)

    print(f"Running on repository: {REPO}")

    values_files: List[Path] = list(Path(charts_dir_path).glob("*/values.yaml"))
    if not values_files:
        print(f"No 'values.yaml' files found in subdirectories of '{charts_dir_path}'. Exiting.")
        return

    for value_file in values_files:
        print(f"\n--- Processing file: {value_file} ---")
        app_group: str = value_file.parent.name

        try:
            with open(value_file, 'r') as f:
                apps_data: Optional[Dict[str, AppDetails]] = yaml.safe_load(f)
        except Exception as e:
            print(f"Error reading or parsing YAML file {value_file}: {e}", file=sys.stderr)
            continue

        if not apps_data:
            continue

        for name, details in apps_data.items():

            if not isinstance(details, dict): # type: ignore
                print(f"Warning: Skipping '{name}' in {value_file} because its value is not a dictionary.", file=sys.stderr)
                continue
            
            repo_url: Optional[str] = details.get("repoURL")
            target_revision: str = str(details.get("targetRevision", ""))
            chart: Optional[str] = details.get("chart")
            repoPath: Optional[str] = details.get("chart")

            if not chart or not repoPath:
                print(f"Warning: Missing 'chart' key for '{name}' in {value_file}. Skipping.")
                continue

            latest_version: Optional[str] = get_latest_helm_version(repo_url, chart, repoPath)

            if not latest_version:
                continue

            print("----------------------------------------")
            print(f"Checking: {name} (from {app_group})")
            print(f"  -> Your Version (targetRevision): {target_revision}")
            print(f"  -> Latest Version Available:      {latest_version}")
            print("----------------------------------------")

            if latest_version != target_revision and target_revision:
                title: str = f"New Version Available: {name} {latest_version}"

                existing_issue_number: Optional[int] = check_existing_issue(REPO, github_token, title)

                if not existing_issue_number:
                    print(f"Found new version for {name}! Creating issue...")

                    assignees: List[str] = get_maintainers(maintainers_file_path, app_group)

                    if assignees:
                        print(f"Found maintainers for '{app_group}': {', '.join(assignees)}")

                    body: str = (
                        f"New version available for **{name}**!\n\n"
                        f"Current `targetRevision` set: `{target_revision}`\n"
                        f"New version available: `{latest_version}`\n\n"
                        f"Please consider creating a PR to update the `targetRevision` in this file: "
                        f"[{value_file}](https://github.com/{REPO}/blob/main/{value_file})\n\n"
                        "Thanks."
                    )

                    create_github_issue(REPO, github_token, title, body, assignees)
                else:
                    print(f"Issue #{existing_issue_number} for '{title}' already exists. Skipping.")

    print("\nScript finished.")

if __name__ == "__main__":
    main()