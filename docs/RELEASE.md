# ScoreSight Release Guide

This repository already contains GitHub Actions workflows for cross-platform builds and releases:

- `.github/workflows/build.yaml`
- `.github/workflows/release.yaml`

They build artifacts for:

- macOS (`macos-x86`, `macos-arm64`)
- Windows
- Linux

## 1. Prerequisites

1. Push your latest code to GitHub.
2. Make sure the default branch is `main`.
3. (Optional, for better macOS distribution) configure Apple signing/notarization secrets in GitHub repository settings.

## 2. Create a Release Tag

Use a valid release tag format:

- Stable: `1.2.3`
- Pre-release: `1.2.3-beta1` or `1.2.3-rc1`

Commands:

```bash
git tag 1.2.3
git push origin 1.2.3
```

## 3. What GitHub Actions Does

After pushing the tag:

1. Runs cross-platform build workflow.
2. Builds platform artifacts:
   - macOS: `.dmg`
   - Windows: installer zipped as `.zip` (containing `.exe`)
   - Linux: `.tar`
3. Generates checksums.
4. Creates a **draft GitHub Release** and uploads all artifacts.

## 4. Publish the Release

1. Open GitHub -> **Releases**.
2. Open the newly created draft release.
3. Check version text and files.
4. Click **Publish release**.

## 5. Troubleshooting

- If no release appears, check **Actions** tab for failed jobs.
- If tag is rejected by workflow, verify tag format (`1.2.3`, `1.2.3-beta1`, `1.2.3-rc1`).
- If macOS notarization/signing fails, verify Apple secrets used by `.github/workflows/build.yaml`.

## 6. Local macOS Build (Fast Test Loop)

For local development/testing, use the macOS app bundle directly (no DMG required):

```bash
pyinstaller --clean --noconfirm scoresight.spec -- --mac_osx
rm -rf /Applications/scoresight.app
cp -R dist/scoresight.app /Applications/
xattr -dr com.apple.quarantine /Applications/scoresight.app
open /Applications/scoresight.app
```

This is faster than rebuilding/re-mounting DMGs for each test iteration.
