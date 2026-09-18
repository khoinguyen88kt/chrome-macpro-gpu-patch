# Google Chrome Hardware Acceleration Patch for Legacy Mac GPUs
### Optimized for Mac Pro 6,1 (Dual AMD FirePro D700 / D500 / D300) on macOS Sequoia & Sonoma via OCLP

[![Platform](https://img.shields.io/badge/Platform-macOS%20Sequoia%20%7C%20Sonoma%20(OCLP)-blue.svg)](#)
[![Hardware](https://img.shields.io/badge/Hardware-Mac%20Pro%206%2C1%20(Late%202013)-lightgrey.svg)](#)
[![GPU](https://img.shields.io/badge/GPU-AMD%20FirePro%20D700%20%2F%20D500%20%2F%20D300-red.svg)](#)
[![Chrome](https://img.shields.io/badge/Chrome-130%2B%20(Verified%20on%20153.x)-green.svg)](#)
[![License](https://img.shields.io/badge/License-MIT-purple.svg)](LICENSE)

---

🌐 **Languages / Ngôn ngữ:** **English** | [Tiếng Việt](README.vi.md)

---

## 📖 Overview

Starting with **Chromium 130+**, Google officially deprecated and disabled the ANGLE OpenGL backend on macOS, mandating modern **Metal / Skia Graphite**. For legacy Mac hardware running modern macOS through **OpenCore Legacy Patcher (OCLP)** — notably the **Mac Pro 6,1 (Late 2013 "Trash Can")** equipped with **Dual AMD FirePro D700 / D500 / D300 (GCN 1.0 architecture)** — these GPUs lack support for modern Metal features (Metal 2.4/3, ray-tracing, modern shader tile memory). Consequently:

1. **OpenGL is completely disabled**: Chrome falls back to Software Rendering, causing severe lag, UI stutter, and massive CPU usage. Moving the mouse over UI elements or navigating to YouTube crashes the GPU process immediately.
2. **Checkerboard / Black Grid Tiles**: Toolbars, bookmarks, tabs, and web pages are corrupted with repeating black rectangular grid artifacts due to Zero-Copy texture coordinate mismatches.
3. **YouTube Video Green Screen**: Software-decoded video frames fail to map properly onto multi-plane YUV IOSurfaces, turning the video player into a solid green box or stuck thumbnail.
4. **Ambient Mode Ghost Thumbnail Leak**: YouTube's Ambient Mode (cinematics canvas) leaks cached recommendation thumbnails behind and beneath the video player due to dirty OpenGL texture recycling.
5. **Search Bar Background Flicker**: Hovering over video thumbnails on YouTube triggers inline thumbnail playback; partial tile rasterization updates cause gamma/sRGB state bleeding that makes the search bar background flicker continuously.

This repository provides an **automated, clean, and 100% stable solution** that restores full GPU hardware acceleration (**Compositing, Rasterization, OpenGL, WebGL, WebGPU**) on Google Chrome without visual artifacts or crashes.

---

## 🛠️ Prerequisites & Dependencies

Before running the patcher, ensure your system has the following:

1. **Xcode Command Line Tools** (provides the `clang` compiler and macOS SDK headers):
   ```bash
   xcode-select --install
   ```
2. **Python 3**:
   * Built-in on macOS or installed via Homebrew (`brew install python3`).
   * Only utilizes Python standard libraries (`os`, `sys`, `shutil`, `subprocess`, `glob`). **No external `pip` packages required**.
3. **macOS System Security Utilities**:
   * `/usr/bin/codesign`, `/usr/bin/security`, and `/usr/bin/openssl` (standard on all macOS installations).
4. **Local Self-Signed Certificate (`LocalCodeSigner`)**:
   * An automated setup script is included in this repository.

---

## 🚀 Quick Start Guide

### Step 1: Clone the Repository
```bash
git clone https://github.com/<your-username>/chrome-macpro-gpu-patch.git
cd chrome-macpro-gpu-patch
```

### Step 2: Set up the Local Code Signing Certificate (One-time only)
Run the automated script to generate and install the `LocalCodeSigner` certificate into your macOS Keychain:
```bash
bash setup_certificate.sh
```

### Step 3: Run the Automated Patcher
Make sure Google Chrome is completely closed, then run:
```bash
python3 auto_patch_chrome.py
```
*The script will automatically copy clean ANGLE dylibs, scan and patch the Chrome Framework binary, compile the optimized native C launcher, and re-sign the entire Chrome application bundle.*

### Step 4: Launch Chrome & Verify
1. Launch Google Chrome from `/Applications/Google Chrome.app`.
2. *(If prompted)* macOS Keychain will show a dialog: *"Google Chrome wants to access key 'Chrome Safe Storage' in your keychain"*. Enter your macOS user password and click **"Always Allow"** to preserve your profile logins and cookies.
3. Navigate to `chrome://gpu` to verify:
   * **Compositing**: Hardware accelerated
   * **Rasterization**: Hardware accelerated (Multiple Raster Threads: Enabled)
   * **OpenGL**: **Enabled** (`ANGLE (ATI Technologies Inc., AMD Radeon HD - FirePro D700 OpenGL Engine, OpenGL 4.1 ATI-4.8.101)`)
   * **WebGL / WebGL 2**: Hardware accelerated
   * **WebGPU**: Hardware accelerated
   * **GPU Process Crash Count**: **0**

---

## 🔬 Technical Deep Dive

### 1. Bypassing macOS OpenGL Disablement (Binary Patching)
The [`auto_patch_chrome.py`](auto_patch_chrome.py) script uses **Pattern Scanning** to locate and patch 7 critical code locations in `Google Chrome Framework`:

| # | Chromium Target Function | Original Byte Sequence | Patched Byte Sequence | Technical Purpose |
| :---: | :--- | :--- | :--- | :--- |
| **1** | `GetAllowedGLImplementation` | `84 c0 74 0f ...` | `84 c0 90 90 ...` | NOPs out the conditional jump that forbids ANGLE OpenGL on macOS. |
| **2** | `GetDisplayInitializationParams` | `84 c0 0f 85 06 06 00 00 ...` | `84 c0 e9 07 06 00 00 90 ...` | Forces `supports_angle_opengl` check to pass (`jmp +0x607`). |
| **3** | `InitializeGpuModes` | `c7 45 ac 03 00 00 00` | `c7 45 ac 01 00 00 00` | Forces GPU fallback mode to `GpuMode::HARDWARE_GL` (1) instead of `DISABLED` (3). |
| **4** | `GpuMain` Seatbelt Sandbox | `85 c0 0f 84 ed 00 00 00` | `85 c0 90 90 90 90 90 90` | NOPs out `CHECK(Seatbelt::IsSandboxed())` abort during CGL window initialization. |
| **5** | `IOSurfaceImageBackingFactory` | `48 8d b5 78 ... 89 44 24 10` | `48 8d b5 78 ... 41 b8 f5 84 00 00` | Sets IOSurface texture target to `GL_TEXTURE_RECTANGLE` (`0x84f5`). |
| **6** | `ScopedEGLSurfaceIOSurface::ValidateTarget` | `55 48 89 e5 41 56 ...` | `b0 01 c3 90 ...` | Patches validation to always return `true` (`mov al, 1; ret`). |
| **7** | `IOSurfaceImageBacking` constructor | `8b 45 d0 89 83 88 01 00 00` | `c7 83 88 01 00 00 f5 84 00 00` | Forces `gl_target_ = 0x84f5` across all IOSurface backing instances. |

---

### 2. Native C Launcher & Flag Injection (`chrome_main.c`)
Rather than using a fragile shell script wrapper, the main executable `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome` is replaced by a native C binary compiled with Clang. It dynamically loads `Google Chrome Framework` via `dlopen` and invokes `ChromeMain` with the exact rendering flags required:

```c
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
```

#### Why Each Flag is Required:
* `--disable-zero-copy`, `--ui-disable-zero-copy`, `--disable-gpu-memory-buffer-compositor-resources`:
  * **Root Cause**: In Zero-Copy rasterization, tiles are backed by `IOSurface` (`GL_TEXTURE_RECTANGLE`). Chromium's compositor quad fragment shaders expect `sampler2D` with normalized $[0.0, 1.0]$ coordinates. Sampling rectangle textures with $[0..1]$ reads only the top-left $1\times 1$ pixel, creating repeating black square grids.
  * **Fix**: Switches to **One-Copy Rasterization**, uploading tiles into standard `GL_TEXTURE_2D` textures with $[0.0, 1.0]$ coordinates, **completely eliminating black grid tiles**.
* `--disable-gpu-memory-buffer-video-frames`, `--disable-features=MediaGmbVideoFramePoolMappableSI`, `--disable-accelerated-video-decode`:
  * **Root Cause**: Decoded YUV video frames wrapped in multi-plane IOSurfaces fail shader mapping on Apple CGL ($U=0, V=0 \to$ solid green).
  * **Fix**: Performs clean software decode (dav1d/libgav1) and transfers standard YUV textures directly to the GPU, **fixing green screen playback**.
* `--disable-accelerated-2d-canvas`:
  * **Root Cause**: YouTube Ambient Mode draws onto a `<canvas>` behind the player. On legacy CGL drivers, GPU texture recycling fails to clear previous thumbnail textures from the pool.
  * **Fix**: Forces 2D canvas to render via CPU Skia in RAM with 0% memory leaks, while 3D, WebGL, WebGPU, and Compositing stay fully accelerated on the GPU.
* `--disable-partial-raster`:
  * **Root Cause**: Top-row compositor tiles cover both the masthead (search bar) and video thumbnails. Sub-texture updates (`glTexSubImage2D`) at 60 FPS cause texture cache and gamma/sRGB state bleeding into neighboring static UI pixels.
  * **Fix**: Forces full clean tile rasterization on damage, **eliminating search bar background flicker**.

---

## 🔄 Maintaining Patches Across Chrome Updates

### How easy is it when Chrome updates?
**Extremely easy and completely automated!**

1. **Robust Pattern Scanning**:
   * The script does not rely on hardcoded memory addresses. As Chrome updates through point releases (e.g. `153.0.8010.50` $\to$ `153.0.8010.60`), the assembly opcode signatures remain identical.
   * Re-patching takes approximately **2 to 3 seconds**.
2. **Re-patch Command**:
   Whenever Chrome auto-updates or is updated, simply run:
   ```bash
   python3 auto_patch_chrome.py
   ```
3. **(Optional) Prevent Unwanted Background Updates**:
   To prevent Google Keystone from updating Chrome in the background without your knowledge:
   ```bash
   defaults write com.google.Keystone.Agent checkInterval 0
   ```
   *(To re-enable automatic updates later: `defaults delete com.google.Keystone.Agent checkInterval`).*

---

## 📂 Repository Structure

```
chrome-macpro-gpu-patch/
├── README.md               # English documentation (default)
├── README.vi.md            # Vietnamese documentation (Tiếng Việt)
├── auto_patch_chrome.py    # Automated pattern-scanning patcher and codesigner
├── chrome_main.c           # Native C launcher with optimal injected flags
├── setup_certificate.sh    # Script to create and install LocalCodeSigner certificate
├── angle_dylibs/           # Pre-extracted clean ANGLE dylibs (libEGL.dylib, libGLESv2.dylib)
├── .gitignore              # Ignores build artifacts and temporary files
└── LICENSE                 # MIT Open Source License
```

---

## 📄 License

This project is licensed under the **MIT License**. Feel free to use, modify, and distribute it to help the legacy Mac and OpenCore Legacy Patcher community!
