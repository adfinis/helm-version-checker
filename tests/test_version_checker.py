import argparse
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests
import yaml
from pyfakefs.fake_filesystem import FakeFilesystem


import version_checker


MAINTAINERS_CONTENT = """
default:
  - "gh-user1"

firsttest-apps:
  - "gh-user2"
"""

FIRSTTEST_VALUES_CONTENT = """
certManager:
  repoURL: https://charts.jetstack.io
  chart: cert-manager
  targetRevision: v1.18.2

invalidChart:
  repoURL: "https://charts.example.com"
  chart: "this-chart-does-not-exists"
  targetRevision: "1.1.1"

missingValues:
  name: no-repo-url
  chart: "this-chart-does-not-exists"
  targetRevision: "4.0.4"
"""

SECONDTEST_VALUES_CONTENT = """
argocd:
  repoURL: https://argoproj.github.io/argo-helm
  chart: argo-cd
  targetRevision: 8.5.8

dexK8sAuthenticator:
  repoURL: "https://github.com/mintel/dex-k8s-authenticator.git"
  chart: "dexK8sAuthenticator"
  targetRevision: "v1.4.0"
"""


@pytest.fixture
def cert_manager_index() -> str:
    """Mock response for charts.jetstack.io/index.yaml"""
    return """
apiVersion: v1
entries:
  cert-manager:
  - apiVersion: v2
    appVersion: v1.19.1
    created: "2025-10-15T14:58:20.519585686Z"
    description: A Helm chart for cert-manager
    name: cert-manager
    urls:
    - charts/cert-manager-v1.19.1.tgz
    version: v1.19.1
  - apiVersion: v2
    appVersion: v1.18.2
    created: "2025-07-02T12:13:05.061182646Z"
    description: A Helm chart for cert-manager
    name: cert-manager
    urls:
    - charts/cert-manager-v1.18.2.tgz
    version: v1.18.2
"""


@pytest.fixture
def argo_cd_index() -> str:
    """Mock response for argoproj.github.io/argo-helm/index.yaml"""
    return """
apiVersion: v1
entries:
  argo-cd:
  - apiVersion: v2
    appVersion: v3.1.8
    created: "2025-10-15T09:20:14.243509046Z"
    description: A Helm chart for Argo CD
    name: argo-cd
    urls:
    - https://github.com/argoproj/argo-helm/releases/download/argo-cd-8.6.2/argo-cd-8.6.2.tgz
    version: 8.6.2
  - apiVersion: v2
    appVersion: v3.1.8
    created: "2025-09-30T17:19:11.396988021Z"
    description: A Helm chart for Argo CD
    name: argo-cd
    urls:
    - https://github.com/argoproj/argo-helm/releases/download/argo-cd-8.5.8/argo-cd-8.5.8.tgz
    version: 8.5.8
"""


def test_get_maintainers_specific_group(tmp_path: Path):
    """Tests loading maintainers for a specific, defined app group."""
    p = tmp_path / "MAINTAINERS.yaml"
    p.write_text(MAINTAINERS_CONTENT)
    assignees = version_checker.get_maintainers(str(p), "firsttest-apps")
    assert assignees == ["gh-user2"]


def test_get_maintainers_fallback_to_default(tmp_path: Path):
    """Tests falling back to 'default' when an app group is not specified."""
    p = tmp_path / "MAINTAINERS.yaml"
    p.write_text(MAINTAINERS_CONTENT)
    assignees = version_checker.get_maintainers(str(p), "secondtest-apps")
    assert assignees == ["gh-user1"]


def test_get_maintainers_file_not_found(capsys):
    """Tests that an empty list is returned if the file doesn't exist."""
    assignees = version_checker.get_maintainers("nonexistent/file.yaml", "any-app")
    assert assignees == []
    captured = capsys.readouterr()
    assert "Error: Maintainers file not found" in captured.err


def test_get_latest_helm_version_success(requests_mock, cert_manager_index):
    """Tests a successful fetch of a chart version."""
    url = "https://charts.jetstack.io/index.yaml"
    requests_mock.get(url, text=cert_manager_index)
    version = version_checker.get_latest_helm_version(
        "https://charts.jetstack.io", "cert-manager"
    )
    assert version == "v1.19.1"


def test_get_latest_helm_version_http_error(requests_mock, capsys):
    """Tests a 404 error when fetching index.yaml."""
    url = "https://charts.example.com/index.yaml"
    requests_mock.get(url, status_code=404)
    version = version_checker.get_latest_helm_version(
        "https://charts.example.com", "this-chart-does-not-exists"
    )
    assert version is None
    captured = capsys.readouterr()
    assert "Error: Failed to download index.yaml" in captured.err


def test_get_latest_helm_version_parse_error(requests_mock, cert_manager_index, capsys):
    """Tests when index.yaml is fetched but the chart name isn't in it."""
    url = "https://charts.jetstack.io/index.yaml"
    requests_mock.get(url, text=cert_manager_index)
    version = version_checker.get_latest_helm_version(
        "https://charts.jetstack.io", "chart-does-not-exist"
    )
    assert version is None
    captured = capsys.readouterr()
    assert "Error: Could not parse version" in captured.err


def test_get_latest_helm_version_git_url(requests_mock, capsys):
    """Tests that a git URL (which can't have /index.yaml) fails gracefully."""
    url = "https://github.com/mintel/dex-k8s-authenticator.git/index.yaml"
    requests_mock.get(url, status_code=404)
    version = version_checker.get_latest_helm_version(
        "https://github.com/mintel/dex-k8s-authenticator.git", "dexK8sAuthenticator"
    )
    assert version is None
    captured = capsys.readouterr()
    assert "Error: Failed to download index.yaml" in captured.err


@pytest.mark.parametrize("url", [None, "null"])
def test_get_latest_helm_version_null_repo_url(url, capsys):
    """Tests that 'null' or None repoURL is skipped."""
    version = version_checker.get_latest_helm_version(url, "some-chart")
    assert version is None
    captured = capsys.readouterr()
    assert "Warning: Invalid or missing repoURL" in captured.err


def test_check_existing_issue_found(requests_mock):
    """Tests that an existing issue is found."""
    title = "New Version Available: my-chart 1.2.3"
    mock_response = [{"title": title, "number": 123}]
    requests_mock.get(
        "https://api.github.com/repos/test-owner/test-repo/issues",
        json=mock_response,
    )
    issue_num = version_checker.check_existing_issue(
        "test-owner/test-repo", "fake-token", title
    )
    assert issue_num == 123


def test_check_existing_issue_not_found(requests_mock):
    """Tests when no matching issue is found."""
    title = "New Version Available: my-chart 1.2.3"
    mock_response = [{"title": "Some other issue", "number": 124}]
    requests_mock.get(
        "https://api.github.com/repos/test-owner/test-repo/issues",
        json=mock_response,
    )
    issue_num = version_checker.check_existing_issue(
        "test-owner/test-repo", "fake-token", title
    )
    assert issue_num is None


def test_check_existing_issue_pagination(requests_mock):
    """Tests that the function follows pagination links."""
    title = "New Version Available: my-chart 1.2.3"
    page1_url = "https://api.github.com/repos/test-owner/test-repo/issues"
    page2_url = "https://api.github.com/repos/test-owner/test-repo/issues?page=2"

    # Page 1 response
    requests_mock.get(
        page1_url,
        json=[{"title": "Wrong issue", "number": 111}],
        headers={"Link": f'<{page2_url}>; rel="next"'},
    )
    # Page 2 response
    requests_mock.get(
        page2_url,
        json=[{"title": title, "number": 123}],
        headers={},
    )

    issue_num = version_checker.check_existing_issue(
        "test-owner/test-repo", "fake-token", title
    )
    assert issue_num == 123
    assert requests_mock.call_count == 2


def test_create_github_issue(requests_mock):
    """Tests the payload of the create issue POST request."""
    m = requests_mock.post(
        "https://api.github.com/repos/test-owner/test-repo/issues", status_code=201
    )
    version_checker.create_github_issue(
        "test-owner/test-repo",
        "fake-token",
        "Test Title",
        "Test Body",
        ["user1", "user2"],
    )
    assert m.called
    assert m.last_request.json() == {
        "title": "Test Title",
        "body": "Test Body",
        "assignees": ["user1", "user2"],
    }


def test_parse_args(monkeypatch):
    """Tests successful argument parsing."""
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "script_name",
            "--token",
            "my-token",
            "--charts-path",
            "/custom/charts",
            "--maintainers-file",
            "/custom/maintainers.yaml",
        ],
    )
    args = version_checker.parse_args()
    assert args.token == "my-token"
    assert args.charts_path == "/custom/charts"
    assert args.maintainers_file == "/custom/maintainers.yaml"


def test_parse_args_missing_token(monkeypatch):
    """Tests that argparse exits if the required --token is missing."""
    monkeypatch.setattr(sys, "argv", ["script_name"])
    with pytest.raises(SystemExit):
        version_checker.parse_args()


@patch("version_checker.create_github_issue")
@patch("version_checker.check_existing_issue")
@patch("version_checker.get_latest_helm_version")
def test_main_full_run(
    mock_get_version: MagicMock,
    mock_check_issue: MagicMock,
    mock_create_issue: MagicMock,
    fs: FakeFilesystem,
    monkeypatch: pytest.MonkeyPatch,
):
    """
    Tests the main() function

    This test will:
    1. Create a new version for 'certManager' and no existing issue.
       -> EXPECT: create_github_issue is called.
    2. Create a new version for 'argocd' but an issue already exists.
       -> EXPECT: create_github_issue is NOT called.
    3. Fail to find a version for 'invalidChart'.
       -> EXPECT: No call.
    4. Fail to find a version for 'dexK8sAuthenticator'.
       -> EXPECT: No call.
    """
    fs.create_file("MAINTAINERS.yaml", contents=MAINTAINERS_CONTENT)
    fs.create_file(
        "charts/firsttest-apps/values.yaml", contents=FIRSTTEST_VALUES_CONTENT
    )
    fs.create_file(
        "charts/secondtest-apps/values.yaml", contents=SECONDTEST_VALUES_CONTENT
    )

    monkeypatch.setenv("GITHUB_REPOSITORY", "test-owner/test-repo")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "script_name",
            "--token",
            "fake-token",
            "--charts-path",
            "charts",
            "--maintainers-file",
            "MAINTAINERS.yaml",
        ],
    )

    version_checker.REPO = "test-owner/test-repo"

    def get_version_side_effect(repo_url, chart_name):
        if chart_name == "cert-manager":
            return "v1.19.1"
        if chart_name == "argo-cd":
            return "8.6.2"
        return None 
    
    def check_issue_side_effect(repo, token, title):
        if "certManager" in title:
            return None
        if "argocd" in title:
            return 123
        return None

    mock_get_version.side_effect = get_version_side_effect
    mock_check_issue.side_effect = check_issue_side_effect

    version_checker.main()


    expected_title_cert = "New Version Available: certManager v1.19.1"
    mock_check_issue.assert_any_call(
        "test-owner/test-repo", "fake-token", expected_title_cert
    )
    mock_create_issue.assert_called_once()
    
    call_args = mock_create_issue.call_args[0]

    assert call_args[0] == "test-owner/test-repo"
    assert call_args[1] == "fake-token"
    assert call_args[2] == expected_title_cert
    assert "New version available for **certManager**!" in call_args[3] # This is the partial string check
    assert call_args[4] == ["gh-user2"]

    expected_title_argo = "New Version Available: argocd 8.6.2"
    mock_check_issue.assert_any_call(
        "test-owner/test-repo", "fake-token", expected_title_argo
    )
    
    # Assert create_github_issue was ONLY called once (for certManager)
    assert mock_create_issue.call_count == 1