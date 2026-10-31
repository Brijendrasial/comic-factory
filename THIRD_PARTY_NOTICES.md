# Third-party components

The MIT license in this repository covers Comic Factory's application code. It does not replace the licenses of downloaded models, Python, CUDA components, dependencies, fonts or third-party runtimes.

The installer contains a PyInstaller-frozen standard-library/Tk launcher, the application scripts and model download metadata. It does not bundle model weights, GPU libraries, the author's environments, personal projects or credentials. First-run setup retrieves dependencies from their original distribution services.

| Component | License / upstream |
|---|---|
| Python | PSF license and bundled third-party notices; https://www.python.org/psf/license/ |
| Python standalone distributions | https://github.com/astral-sh/python-build-standalone â€” preserves upstream distribution licenses |
| Tk / Tcl | Tcl/Tk BSD-style terms, included with the Python launcher |
| PyInstaller bootloader | GPL with a distribution exception; https://pyinstaller.org/en/stable/license.html |
| PyTorch / TorchVision | BSD-style; https://github.com/pytorch/pytorch |
| NVIDIA CUDA runtime libraries | NVIDIA component-specific terms, supplied through the upstream PyTorch wheels |
| Diffusers / Transformers / Accelerate | Apache-2.0; https://github.com/huggingface |
| bitsandbytes | MIT; https://github.com/bitsandbytes-foundation/bitsandbytes |
| Story model | Qwen3-4B-Instruct-2507, Apache-2.0; quantization: https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-bnb-4bit |
| Artwork model | FLUX.2 Klein **4B**, Apache-2.0; quantization: https://huggingface.co/hlhc/FLUX.2-klein-4B-bnb-4bit |
| Expressive speech | Qwen3-TTS-12Hz-1.7B-CustomVoice, Apache-2.0; https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice |
| Artwork-review model | Qwen3-VL, Apache-2.0; pinned Ollama registry layers |
| Ollama | MIT and bundled third-party component notices; https://github.com/ollama/ollama |
| FFmpeg | License depends on the upstream imageio-ffmpeg binary configuration, including codec terms; https://ffmpeg.org/legal.html |
| Pillow, NumPy, SciPy, librosa, soundfile and other Python libraries | Their individual upstream licenses, installed in each environment's package metadata |

The pinned files and model revisions are recorded in model-manifest.json. Model license/readme files are downloaded with the corresponding model when provided upstream. The registered model descriptions and model weights remain the property of their respective authors.

Windows fonts are read from the user's Windows installation, not redistributed. The README gallery includes user-created AI fan-art demonstrations featuring Superman and Batman. These characters and related marks belong to their respective rights holders; no affiliation or endorsement is implied. The MIT license for application code does not grant rights to those characters, marks or demo artwork. The Windows installer does not bundle the gallery. Users are responsible for rights to their own inputs and exported projects.
