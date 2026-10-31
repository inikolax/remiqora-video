# Contributing to Remiqora Video

Thanks for your interest! Bug reports and ideas are welcome. Issues can be written in **English or Russian**.

## Issues only, for now

Remiqora Video is a solo project in active development, and **pull requests are not accepted yet**. If you found a bug or have an idea, please [open an issue](https://github.com/inikolax/remiqora-video/issues/new/choose) using a template instead: a clear report helps more than a patch at this stage. This may change later; this file will say so.

For security problems, see [SECURITY.md](SECURITY.md). Please don't report them as public issues.

## A good bug report

- **Where it happens:** the screen or node (Idea, Storyboard, Film, Montage, Graph, Lab, Models page), the installer or the setup scripts.
- **The model:** MiniMax H3, LTX 2.5, LTX 2.3, WAN 2.2 5B, Krea 2 or the writer, and whether you use the official weights or your own file.
- **Steps to reproduce**, what you expected and what happened. Screenshots are welcome.
- **Your system:** the GPU and its memory, the RAM, the NVIDIA driver version.
- **The version:** from source, the commit shown at the bottom of the app (or `git rev-parse --short HEAD` in the repository folder); with the installer, the version shown for Remiqora Video in Windows Settings → Apps → Installed apps (or in the setup file's name, `Remiqora-Video-Setup-<version>.exe`).
- **Logs**, trimmed to the relevant part, from the app's `data\` folder: `h3worker.log` (the video worker), `llama-server.log` (the writer), `comfy.log`. With the installer the app lives in `%LOCALAPPDATA%\RemiqoraVideo\app`; also attach `%LOCALAPPDATA%\RemiqoraVideo\logs\app-server.log` (the app's server) and, for install problems, `setup.log` from the same folder.

Please don't attach model weights, your `.env` file or `data\hf_token`.

## Ideas

Describe the problem or the use case rather than the solution: what you are trying to make, and where the app gets in the way.

## Running from source

Follow the [installation steps in the README](README.md#way-2-from-source) (`setup_prereqs` and `setup_models`), then start everything with `dev.bat`. The API and the built page run on port 8810, the Vite development page on port 5173.

## Third-party models

Remiqora Video is a studio around third-party models: it installs only their official weights and doesn't ship them in this repository. Each model has its own license, listed in the [README](README.md#license--liability-for-generated-content). A video you make falls under the license of the model that made it, and making sure a model is legal to use where you live is your responsibility.

## License

Remiqora Video's own code is licensed under [GPL-3.0](LICENSE). If you fork it or build on it, keep the credit to this repository and its author, as the README asks.
