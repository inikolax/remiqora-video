// rtx_vsr: raw RGBA frames on stdin -> RTX Video Super Resolution (NVIDIA RTX Video SDK, CUDA host-pointer API) ->
// raw RGBA frames on stdout. usage: rtx_vsr <in_w> <in_h> <out_w> <out_h> [quality 1-4] [hdr <max nits>]
// hdr: TrueHDR after VSR - the output is then R10G10B10A2 (ffmpeg x2bgr10le), PQ (ST.2084), BT.2020, full range.
// Meant to sit between two ffmpeg processes:
//   ffmpeg -i in.mp4 -f rawvideo -pix_fmt rgba - | rtx_vsr 704 1280 1056 1920 4 | ffmpeg -f rawvideo -pix_fmt rgba -s 1056x1920 ...
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
#include <io.h>
#include <fcntl.h>
#include <cuda.h>
#include "rtx_video_api.h"

static bool read_all(void* buf, size_t n) {
    char* p = static_cast<char*>(buf);
    while (n) { size_t r = fread(p, 1, n, stdin); if (!r) return false; p += r; n -= r; }
    return true;
}

static void say(const char* s) { fputs(s, stderr); fputc('\n', stderr); fflush(stderr); }

// The NGX loader lib (nvsdk_ngx_d.lib) calls three CUDA runtime functions to find the GPU's LUID. It was built
// against CUDA 12's cudaDeviceProp; CUDA 13's cudart writes a different struct into its stack buffer and the
// process dies with 0xC0000409. So these three come from the driver API instead, filling only the head of the
// struct (name[256], uuid[16], luid[8], luidDeviceNodeMask) - the same offsets in every CUDA since 10.
extern "C" int cudaGetDevice(int* device) {
    CUdevice d;
    if (cuCtxGetDevice(&d) != CUDA_SUCCESS) return 1;
    *device = (int)d;
    return 0;
}
extern "C" int cudaGetDeviceProperties(void* prop, int device) {
    char* p = static_cast<char*>(prop);
    CUdevice d;
    if (cuDeviceGet(&d, device) != CUDA_SUCCESS) return 1;
    cuDeviceGetName(p, 256, d);
    cuDeviceGetUuid(reinterpret_cast<CUuuid*>(p + 256), d);
    return cuDeviceGetLuid(p + 272, reinterpret_cast<unsigned int*>(p + 280), d) == CUDA_SUCCESS ? 0 : 1;
}
extern "C" const char* cudaGetErrorString(int) { return "CUDA runtime error"; }

int main(int argc, char** argv) {
    if (argc < 5) { say("usage: rtx_vsr in_w in_h out_w out_h [quality 1-4] [hdr max_nits]"); return 2; }
    const uint32_t iw = atoi(argv[1]), ih = atoi(argv[2]), ow = atoi(argv[3]), oh = atoi(argv[4]);
    const uint32_t q = argc > 5 ? atoi(argv[5]) : 4;
    const bool hdr = argc > 6 && !strcmp(argv[6], "hdr");
    const uint32_t nits = argc > 7 ? atoi(argv[7]) : 1000;
    _setmode(_fileno(stdin), _O_BINARY);
    _setmode(_fileno(stdout), _O_BINARY);
    say("rtx_vsr: start");
    CUdevice dev; CUcontext ctx;
    if (cuInit(0) != CUDA_SUCCESS || cuDeviceGet(&dev, 0) != CUDA_SUCCESS ||
        cuDevicePrimaryCtxRetain(&ctx, dev) != CUDA_SUCCESS || cuCtxSetCurrent(ctx) != CUDA_SUCCESS) {
        say("rtx_vsr: CUDA init failed"); return 3;
    }
    say("rtx_vsr: cuda ok");
    if (rtx_video_api_cuda_create(ctx, nullptr, 0, hdr ? API_BOOL_SUCCESS : API_BOOL_FAIL, API_BOOL_SUCCESS) != API_BOOL_SUCCESS) {
        say("rtx_vsr: VSR create failed"); return 3;
    }
    say("rtx_vsr: vsr created");
    std::vector<unsigned char> in((size_t)iw * ih * 4), out((size_t)ow * oh * 4);
    API_RECT ir{0, 0, iw, ih}, orr{0, 0, ow, oh};
    API_VSR_Setting vsr{q};
    API_THDR_Setting thdr{100, 100, 50, nits};  // the SDK demo's defaults: contrast, saturation, middle gray
    long frames = 0;
    while (read_all(in.data(), in.size())) {
        if (rtx_video_api_cuda_evaluate_hostptr(in.data(), out.data(), ir, orr, &vsr, hdr ? &thdr : nullptr) != API_BOOL_SUCCESS) {
            fprintf(stderr, "rtx_vsr: evaluate failed at frame %ld\n", frames); return 4;
        }
        if (fwrite(out.data(), 1, out.size(), stdout) != out.size()) { say("rtx_vsr: write failed"); return 5; }
        if (++frames % 100 == 0) fprintf(stderr, "rtx_vsr: %ld frames\n", frames);
    }
    fflush(stdout);
    rtx_video_api_cuda_shutdown();
    fprintf(stderr, "rtx_vsr: done, %ld frames\n", frames);
    return 0;
}
