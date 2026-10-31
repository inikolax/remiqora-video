// «Модели и лицензии» in the footer (after Remiqora's composables/credits.ts): every model the studio runs and the
// programs that run them - what it does here, where it comes from, under which license. The video models first; LTX
// asks for a published video to be labelled as made by AI (`disclosure`). The writer's GGUF is the user's own pick:
// the footer names it from the header's list. Not shown for now (2026-10-24, the user: «убери пока модели из подвала»).
import { t } from '../i18n'

export interface Credit {
  name: string
  url: string
  license: string
  licenseUrl?: string
  role: string
  group: 'video' | 'model' | 'tool'
  disclosure?: boolean
}

const APACHE = 'https://www.apache.org/licenses/LICENSE-2.0'
const MIT = 'https://opensource.org/license/mit'
const LTX = 'https://github.com/Lightricks/LTX-2/blob/main/LICENSE-2_x'

// a function: the roles follow the interface's language
export const credits = (): Credit[] => [
  // the video models («Модели и настройки» has each one's weights)
  { group: 'video', name: 'MiniMax H3', url: 'https://huggingface.co/MiniMaxAI/MiniMax-H3', license: t('misc.credit.h3License'),
    licenseUrl: 'https://huggingface.co/Comfy-Org/MiniMax-H3', role: t('misc.credit.h3') },
  { group: 'video', name: 'LTX-2.5', url: 'https://huggingface.co/Lightricks/LTX-2.5', license: 'LTX-2 Community License', licenseUrl: LTX,
    role: t('misc.credit.ltx25'), disclosure: true },
  { group: 'video', name: 'LTX-2.3', url: 'https://huggingface.co/Lightricks/LTX-2.3', license: 'LTX-2 Community License', licenseUrl: LTX,
    role: t('misc.credit.ltx23'), disclosure: true },
  { group: 'video', name: 'Wan 2.2 TI2V-5B', url: 'https://huggingface.co/Wan-AI/Wan2.2-TI2V-5B', license: 'Apache-2.0', licenseUrl: APACHE,
    role: t('misc.credit.wan') },
  // pictures, encoders, helpers
  { group: 'model', name: 'Krea 2 Turbo', url: 'https://huggingface.co/krea/Krea-2-Turbo', license: 'Krea 2 Community License',
    licenseUrl: 'https://huggingface.co/krea/Krea-2-Turbo/blob/main/LICENSE.pdf', role: t('misc.credit.krea') },
  { group: 'model', name: 'FastWan 2.2 TI2V-5B', url: 'https://huggingface.co/FastVideo/FastWan2.2-TI2V-5B-FullAttn-Diffusers', license: 'Apache-2.0', licenseUrl: APACHE,
    role: t('misc.credit.fastwan') },
  { group: 'model', name: 'Qwen3-VL-32B-Instruct', url: 'https://huggingface.co/Qwen/Qwen3-VL-32B-Instruct', license: 'Apache-2.0', licenseUrl: APACHE,
    role: t('misc.credit.qwen32') },
  { group: 'model', name: 'Gemma 4 12B', url: 'https://huggingface.co/google/gemma-4-12B-it', license: 'Apache-2.0', licenseUrl: 'https://ai.google.dev/gemma/docs/gemma_4_license',
    role: t('misc.credit.gemma4') },
  { group: 'model', name: 'Gemma 3 12B', url: 'https://huggingface.co/google/gemma-3-12b-it', license: 'Gemma Terms of Use', licenseUrl: 'https://ai.google.dev/gemma/terms',
    role: t('misc.credit.gemma3') },
  { group: 'model', name: 'umT5-XXL', url: 'https://huggingface.co/google/umt5-xxl', license: 'Apache-2.0', licenseUrl: APACHE, role: t('misc.credit.umt5') },
  { group: 'model', name: 'Qwen3-VL-4B-Instruct', url: 'https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct', license: 'Apache-2.0', licenseUrl: APACHE, role: t('misc.credit.qwen4') },
  { group: 'model', name: 'ID-LoRA TalkVid', url: 'https://huggingface.co/AviadDahan/LTX-2.3-ID-LoRA-TalkVid-3K', license: t('misc.credit.onPage'),
    role: t('misc.credit.idlora') },
  { group: 'model', name: 'Demucs (htdemucs)', url: 'https://github.com/facebookresearch/demucs', license: 'MIT', licenseUrl: MIT,
    role: t('misc.credit.demucs') },
  { group: 'model', name: 'Whisper large-v3', url: 'https://huggingface.co/openai/whisper-large-v3', license: 'Apache-2.0', licenseUrl: APACHE,
    role: t('misc.credit.whisper') },
  { group: 'model', name: 'WeSpeaker ResNet34', url: 'https://github.com/wenet-e2e/wespeaker', license: 'Apache-2.0', licenseUrl: APACHE,
    role: t('misc.credit.wespeaker') },
  { group: 'model', name: 'YuNet + SFace', url: 'https://github.com/opencv/opencv_zoo', license: 'Apache-2.0', licenseUrl: APACHE,
    role: t('misc.credit.yunet') },
  { group: 'model', name: 'RIFE v4.6', url: 'https://github.com/hzwer/Practical-RIFE', license: 'MIT', licenseUrl: MIT, role: t('misc.credit.rife') },
  // the programs
  { group: 'tool', name: 'ComfyUI', url: 'https://github.com/Comfy-Org/ComfyUI', license: 'GPL-3.0', licenseUrl: 'https://www.gnu.org/licenses/gpl-3.0.html',
    role: t('misc.credit.comfy') },
  { group: 'tool', name: 'PyTorch', url: 'https://pytorch.org', license: 'BSD-3-Clause', licenseUrl: 'https://github.com/pytorch/pytorch/blob/main/LICENSE', role: t('misc.credit.torch') },
  { group: 'tool', name: 'llama.cpp (llama-server)', url: 'https://github.com/ggml-org/llama.cpp', license: 'MIT', licenseUrl: MIT, role: t('misc.credit.llama') },
  { group: 'tool', name: 'faster-whisper', url: 'https://github.com/SYSTRAN/faster-whisper', license: 'MIT', licenseUrl: MIT, role: t('misc.credit.fwhisper') },
  { group: 'tool', name: 'OpenCV', url: 'https://opencv.org', license: 'Apache-2.0', licenseUrl: APACHE, role: t('misc.credit.opencv') },
  { group: 'tool', name: 'rife-ncnn-vulkan', url: 'https://github.com/nihui/rife-ncnn-vulkan', license: 'MIT', licenseUrl: MIT, role: t('misc.credit.rifeNcnn') },
  { group: 'tool', name: 'NVIDIA RTX Video', url: 'https://developer.nvidia.com/rtx-video-sdk', license: 'NVIDIA RTX Video SDK License',
    licenseUrl: 'https://developer.nvidia.com/rtx-video-sdk', role: t('misc.credit.rtx') },
  { group: 'tool', name: 'FFmpeg', url: 'https://ffmpeg.org', license: 'LGPL / GPL', licenseUrl: 'https://ffmpeg.org/legal.html', role: t('misc.credit.ffmpeg') },
]
