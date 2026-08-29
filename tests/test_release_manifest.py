#!/usr/bin/env python3
"""Release manifest consistency checks (NOT-43)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MANIFESTS = (
    (ROOT / ".claude-plugin" / "plugin.json", ("version",)),
    (ROOT / ".claude-plugin" / "marketplace.json", ("plugins", 0, "version")),
    (ROOT / ".cursor-plugin" / "plugin.json", ("version",)),
    (ROOT / ".cursor-plugin" / "marketplace.json", ("metadata", "version")),
    (ROOT / ".cursor-plugin" / "marketplace.json", ("plugins", 0, "version")),
    (ROOT / ".codex-plugin" / "plugin.json", ("version",)),
)


def _read_version(path: Path, keys: tuple) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    node = data
    for key in keys:
        node = node[key]
    version = str(node).strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError(f"{path}: invalid semver {version!r}")
    return version


def _release_doc_version() -> str | None:
    text = (ROOT / "docs" / "RELEASE.md").read_text(encoding="utf-8")
    match = re.search(r"currently `(\d+\.\d+\.\d+)`", text)
    return match.group(1) if match else None


class ReleaseManifestTests(unittest.TestCase):
    def test_five_manifest_versions_match(self):
        seen: dict[str, list[str]] = {}
        for path, keys in MANIFESTS:
            version = _read_version(path, keys)
            seen.setdefault(version, []).append(f"{path.relative_to(ROOT)} {'.'.join(str(k) for k in keys)}")

        self.assertEqual(
            len(seen),
            1,
            f"manifest versions diverged: {seen}",
        )

    def test_release_doc_matches_manifests(self):
        versions = {_read_version(path, keys) for path, keys in MANIFESTS}
        doc_version = _release_doc_version()
        self.assertIsNotNone(doc_version, "docs/RELEASE.md missing `currently X.Y.Z`")
        self.assertEqual(
            doc_version,
            versions.pop(),
            "docs/RELEASE.md version must match plugin manifests",
        )

    @unittest.skipUnless(
        os.environ.get("LENS_RELEASE_CHECK") == "1",
        "set LENS_RELEASE_CHECK=1 when cutting a release tag",
    )
    def test_git_tag_matches_manifest_at_head(self):
        version = _read_version(MANIFESTS[0][0], MANIFESTS[0][1])
        tag = f"v{version}"

        listed = subprocess.run(
            ["git", "tag", "-l", tag],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        self.assertEqual(listed, tag, f"missing git tag {tag} for manifest version {version}")

        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        tagged = subprocess.run(
            ["git", "rev-parse", tag],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        self.assertEqual(
            head,
            tagged,
            f"{tag} must point at HEAD when LENS_RELEASE_CHECK=1",
        )


if __name__ == "__main__":
    unittest.main()
