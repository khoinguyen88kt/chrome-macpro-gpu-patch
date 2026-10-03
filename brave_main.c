#include <unistd.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <libgen.h>
#include <mach-o/dyld.h>
#include <dlfcn.h>

static const char *kInjectedFlags[] = {
    "--use-angle=gl",
    "--ignore-gpu-blocklist",
    "--disable-features=SkiaGraphite,MediaGmbVideoFramePoolMappableSI",
    "--disable-zero-copy",
    "--ui-disable-zero-copy",
    "--disable-gpu-memory-buffer-compositor-resources",
    "--disable-gpu-memory-buffer-video-frames",
    "--disable-accelerated-video-decode",
    "--disable-accelerated-2d-canvas",
    "--disable-partial-raster",
};
#define NUM_INJECTED_FLAGS (sizeof(kInjectedFlags) / sizeof(kInjectedFlags[0]))

int main(int argc, char *argv[]) {
    char exec_path[1024];
    uint32_t size = sizeof(exec_path);
    if (_NSGetExecutablePath(exec_path, &size) != 0) return 1;

    char *dir = dirname(exec_path);
    char fw_path[1024];
    snprintf(fw_path, sizeof(fw_path), 
        "%s/../Frameworks/Brave Browser Framework.framework/Brave Browser Framework", dir);

    void *lib = dlopen(fw_path, RTLD_LAZY | RTLD_LOCAL | RTLD_FIRST);
    if (!lib) {
        fprintf(stderr, "Failed to dlopen %s: %s\n", fw_path, dlerror());
        return 1;
    }

    int (*chrome_main)(int, const char **) = (int (*)(int, const char **))dlsym(lib, "ChromeMain");
    if (!chrome_main) {
        fprintf(stderr, "Failed to dlsym ChromeMain: %s\n", dlerror());
        return 1;
    }

    /* Track which flags to inject */
    const char *to_add[NUM_INJECTED_FLAGS];
    int add_count = 0;

    for (size_t f = 0; f < NUM_INJECTED_FLAGS; f++) {
        const char *flag = kInjectedFlags[f];
        size_t prefix_len = strcspn(flag, "=");
        int found = 0;
        for (int i = 1; i < argc; i++) {
            if (strncmp(argv[i], flag, prefix_len) == 0) {
                found = 1;
                break;
            }
        }
        if (!found) {
            to_add[add_count++] = flag;
        }
    }

    int new_argc = argc + add_count;
    const char **new_argv = malloc((new_argc + 1) * sizeof(char *));
    new_argv[0] = argv[0];
    int idx = 1;

    for (int i = 0; i < add_count; i++) {
        new_argv[idx++] = to_add[i];
    }

    for (int i = 1; i < argc; i++) {
        new_argv[idx++] = argv[i];
    }
    new_argv[idx] = NULL;

    exit(chrome_main(idx, new_argv));
}
