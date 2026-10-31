// «First run»: the engine (install.bat), the launcher (dev.bat), the weights and the writer on «Models and settings»
import { scenario, steps, step, go, see, tip, meta, GROUP_EN } from '../kit'

export default scenario('first-run', 'First run',
  'From an empty folder to a studio that sees its video model, the writer and the tools. At the end, every «Models and settings» section has a green dot next to the models you will shoot with.',
  meta('Most of the time goes into downloads: the engine environment is about 5 GB, model weights are tens of GB. You need an NVIDIA graphics card, git, uv and Node.js.')
  + steps(
    step('Install the engine',
      '<p>Run <code>install.bat</code> in the program folder. It checks for git and uv (if missing, it suggests <code>winget install Git.Git</code> and <code>winget install astral-sh.uv</code>), installs Python 3.13 from python.org, downloads the ComfyUI core into <code>engine\\ComfyUI</code> and the environment into <code>engine\\.venv</code>: torch for CUDA 13, Demucs, and Whisper for song lyrics.</p>',
      'At the end it checks that torch sees the graphics card and prints «Done. Start Remiqora Video with dev.bat». You no longer need Comfy Desktop after that.'),
    step('Start the studio',
      '<p>Run <code>dev.bat</code>. The first time, it installs the page packages (Node.js needed), then builds the page, opens the «Remiqora Video» window with the server, and a browser at <code>http://127.0.0.1:8810</code>.</p>',
      'Closing the «Remiqora Video» window stops the studio. The video model starts by itself on the first shoot; its log is <code>data\\h3worker.log</code>.'),
    step('Open «Models and settings»',
      '<p>The «Models» button in the header. Sections on the left: «Video H3», «Ref2VA», «LTX 2.5», «LTX 2.3», «WAN 2.2 5B», «Krea 2 — pictures», «Writer», «LoRA», «Tools». The dot next to a section shows whether everything is in place; next to it, how much disk space it takes.</p>'
      + go('/models', 'Open «Models and settings»')),
    step('Download your model\'s weights',
      '<p>A model\'s section lists its weights by role: H3 has «Main model», «Text encoder», «Video VAE», «Audio VAE»; LTX 2.5 also has «Latent upscale ×2»; LTX 2.3 has the main model, the encoder, «Distilled-LoRA» and the upscaler; WAN has the main model, the encoder, the VAE and «LoRA FastWan» for FastWan. «Ref2VA» is only needed for «Keep the face from the photo», «Krea 2» for «Draw from description» and the «Picture» node. Click «Download» next to every file without a dot.</p>',
      'Files download in the background one at a time; «Stop» and «Resume» continue from the same point, and at the end the size is checked against Hugging Face. A file you put into the folder by hand shows up by itself.'),
    step('If a file is gated, enter a token',
      'The «Hugging Face token» field in the «Video H3» section is only needed for gated models. Enter the token and click «Save»: it is stored in <code>data\\hf_token</code>; «Remove» erases it.'),
    step('Connect the writer',
      '<p>The «Writer» section: GGUF models from LM Studio downloads and from folders listed on the page; mark the default model. No model of your own? Paste a file link into «Download GGUF from Hugging Face». For a hero photo you need a model labeled «sees photos».</p>'
      + '<p>The script is written by llama-server. It is looked up in this order: the path from the settings, <code>tools\\llama</code>, the engine of an installed LM Studio. If none is found, the section shows «No llama-server».</p>'
      + go('/models/llm', 'Open «Writer»'),
      'You don\'t need to run LM Studio itself: the studio only takes llama-server from it.'),
    step('Check «Tools»',
      '<p>ComfyUI core, «Python for H3», llama-server, ffmpeg, ffprobe, RIFE and RTX Video each have a dot: «found» or «not found». Wrong path? Use «Choose…» (a Windows dialog) or «As in .env». RIFE is only needed for 48 frames per second, RTX Video for 1080p, 4K and HDR10.</p>'
      + go('/models/tools', 'Open «Tools»')),
    step('Look at the status bar',
      'The bar under the header shows what the graphics card is doing: a purple dot means the video model is shooting, green means the writer is working, gray means it is free. A click opens the task, the queue and «Stop»; when free, «Unload model». On the right: «RAM» and «VRAM».',
      'The first scene after startup or after the writer takes longer: the model loads for up to half a minute.'),
  )
  + tip('Windows may refuse to run an unsigned llama-server: «Smart App Control» is on. Don\'t turn the protection off; install LM Studio instead: the studio will find its signed llama-server by itself.')
  + tip('You don\'t need every model at once. Download one; a model without files shows «no weights» in the «Model» list.')
  + `<p class="note">Next: ${see('tut-idea', 'A video from an idea')} · ${see('models', 'Models and settings')} · ${see('env', 'Settings in .env')}</p>`, GROUP_EN)
