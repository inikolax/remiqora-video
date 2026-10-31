# Security Policy

## Supported versions

Remiqora Video is in active development and has no tagged releases yet. Security fixes are made on the latest `master` only.

## Reporting a vulnerability

Please **do not open a public issue** for security problems.

Report them privately through GitHub: go to the [Security tab](https://github.com/inikolax/remiqora-video/security) and choose **Report a vulnerability** (or use [this direct link](https://github.com/inikolax/remiqora-video/security/advisories/new)). Include what you found, how to reproduce it, and the impact you see. If private reporting is not available there, contact me privately through my GitHub profile, <https://github.com/inikolax>, and keep the details out of public issues.

This is a solo, spare-time project, so I can't promise a fixed response time, but I will read every report and reply as soon as I can.

## Scope and deployment notes

- Remiqora Video is designed to run **locally**. It binds to `127.0.0.1:8810` by default (`HOST` and `PORT` in `.env`), and the app has **no authentication**. Do not expose its port to a network or the internet.
- A Hugging Face token, if you add one, is stored only in the app folder (`data\hf_token`) and is sent only to huggingface.co.
- Vulnerabilities in the underlying projects ([ComfyUI](https://github.com/Comfy-Org/ComfyUI), [llama.cpp](https://github.com/ggml-org/llama.cpp), [FFmpeg](https://ffmpeg.org/security.html)) should be reported to those projects. Problems with model weights go to their authors on Hugging Face. If you're unsure where a problem belongs, report it here and I'll help route it.
