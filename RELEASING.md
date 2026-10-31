# Releasing a beta

1. Run the tests and `tools/build_release.py` on Windows x64.
2. Test the installer on a clean supported Windows/NVIDIA PC without Python or development tools. Exercise interrupted setup, resumed downloads, model repair, storyboard editing, a complete render, voice changes, upgrades and uninstall. Test that projects survive uninstall.
3. Inspect the source diff and scan the source archive for private files, tokens, local user paths and personal generated projects.
4. Verify the exact model/runtime licenses and included notices for the released versions.
5. Sign the installer if you have an appropriate code-signing certificate; compute checksums after signing.
6. Create a repository and push the source. The source archive deliberately excludes virtual environments, model weights, comics and build caches.
7. Create a version tag such as `v0.1.0-beta.1`. The workflow produces artifacts and a draft release. Review the installer, notices, requirements and release notes before publishing the draft.

The initial local build verifies packaging and runs on the developer's machine. It is not a substitute for the clean-machine test in step 2. Use a private repository or an explicitly labeled early beta until that test is complete.
