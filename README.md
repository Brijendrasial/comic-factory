# Comic Factory — Windows / NVIDIA beta

Turn a comic idea or panel script into a lettered comic page and a voiced MP4, using local AI models. Character dialogue supports separate stock voices and per-line emotional direction.

**Version:** 0.1.0-beta.1. This is an early beta, not a guarantee of publication-ready stories or perfect anatomy. Inspect the storyboard, drawings and balloon placement before sharing a comic.

## Install

1. Download `ComicFactory-Setup-0.1.0-beta.1.exe` from this repository's **Releases** page.
2. Run the installer, then open Comic Factory.
3. Click **Set up my PC**. The wizard checks the hardware, installs private runtimes, downloads models with integrity verification, and runs readiness checks.
4. Click **Open Comic Factory**, enter an idea, and choose **Plan story first** or **Make one comic**.

No Python, pip, Git, terminal commands or paid API key are needed by the end user. Initial setup needs internet and approximately 20 GB of downloads, depending on the GPU-package downloads. Keep **60 GB free**. Interrupted model downloads resume on retry. Once installed, the generation pipeline runs locally.

### Supported beta hardware

- Windows 10/11, x64 Intel/AMD PC.
- NVIDIA Ampere or newer GPU, for example RTX 30/40/50 series, with at least 8 GB VRAM.
- Current NVIDIA driver, Microsoft Visual C++ x64 runtime, at least 24 GB RAM; **32 GB RAM recommended**. Setup checks these prerequisites before downloading models. Missing system drivers/runtimes may require administrator approval to install from their vendors.
- At least 60 GB free disk space, plus room for your exported comics.

AMD, Intel-only, Apple Silicon and CPU-only machines are not supported by this beta. Hardware detection checks the reported GPU, not every possible laptop power/driver configuration. A separate clean-machine installation test is still required before calling a release broadly supported.

## Use

Short idea example: “Create a four-panel action comic about a rescue pilot saving a stranded engineer. Use speech balloons and different emotional voices.”

For precise scripts, use TITLE, CHARACTER REFERENCES, SETTING, PANEL 1 … PANEL 4, a Visual description and named dialogue. Give each character a distinct visual profile including age and male/female casting. Example dialogue:

```
ASHA: [worried] The cable is breaking!
ROWAN: [reassuring] Hold the railing. I’m coming.
```

Emotion cues affect speech and are not printed or spoken. Use angry, worried, urgent, reassuring, relieved, warm, happy, sad or calm. The model controls delivery probabilistically; speech-recognition checks can assess words, not whether an acting performance is convincing.

In **Review storyboard**, edit dialogue, regenerate a defective panel, and choose a speaker then click their mouth to adjust balloon tails. **Resume saved comic** continues an unfinished job. **Upgrade voices and video** reuses its drawings.

The MP4 is a voiced comic presentation; it does not animate character bodies or lip movements.

## Storage and privacy

Default storage is `%LOCALAPPDATA%\ComicFactory`. Models, virtual environments, settings, logs and the project library stay there. The app code is installed separately under `%LOCALAPPDATA%\Programs\ComicFactory`. No global Python installation or PATH change is required. Uninstall removes the app and shortcuts while preserving your comics and model downloads. There is no telemetry or hosted inference in the application; setup contacts upstream package/model hosts.

Repair setup from the Start menu or run `ComicFactory.exe --setup`. Diagnostic logs are in the chosen storage folder's `logs` directory. Project errors and replaced assets are saved with the project. Do not post logs publicly without checking them for personal paths and story text.

## Build from source

On Windows x64 with Python 3.12:

```powershell
python tools/build_release.py
```

The build creates a frozen launcher, a native 64-bit per-user installer and SHA256SUMS.txt under `release`. The installer verifies its embedded application payload before installing it. It needs internet for build tools, but does not download model weights or copy your own model cache.

`model-manifest.json` pins upstream revisions, URLs, expected sizes and SHA-256 hashes. Maintainers can refresh it with `python tools/refresh_manifest.py` after reviewing the changes and applicable licenses. `constraints-engine.txt` and `constraints-voice.txt` lock the tested headless inference environments; the voice environment shares the private GPU runtime while keeping its Transformers version separate.

## Publish

Upload the source files listed in `.gitignore`-filtered Git tracking, not your installed application/data folders. Use GitHub **Releases** for the installer. The included Windows build workflow creates build artifacts and a **draft** release for version tags, allowing review before publication. See `RELEASING.md`.

The beta installer is unsigned unless a maintainer supplies a code-signing certificate. Windows may identify it as an unrecognized publisher. Do not describe it as signed or as a clean-machine-tested commercial release without completing those steps.

## Licenses

Application code: MIT. Downloaded models and dependencies retain their own licenses; see `THIRD_PARTY_NOTICES.md`. No model weights or copyrighted-character demo artwork are included in this repository.
