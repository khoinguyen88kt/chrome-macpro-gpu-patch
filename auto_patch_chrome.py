#!/usr/bin/env python3
"""
Automated GPU patcher and codesigner for Google Chrome on legacy Mac GPUs
Optimized for Mac Pro 6,1 (Dual AMD FirePro D700) running macOS Sequoia / Sonoma (OCLP).
"""
import os
import sys
import shutil
import subprocess
import glob

import time
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def get_base_app():
    for path in ["/Applications/Google Chrome.app", os.path.expanduser("~/Applications/Google Chrome.app")]:
        if os.path.exists(path):
            return path
    return "/Applications/Google Chrome.app"

BASE_APP = get_base_app()
FRAMEWORK_DIR = os.path.join(BASE_APP, "Contents/Frameworks/Google Chrome Framework.framework")
VERSIONS_DIR = os.path.join(FRAMEWORK_DIR, "Versions")
CURRENT_LINK = os.path.join(VERSIONS_DIR, "Current")
REF_ANGLE_LIB = os.path.join(SCRIPT_DIR, "angle_dylibs")
LAUNCHER_SRC = os.path.join(SCRIPT_DIR, "chrome_main.c")

def notify(title, message):
    try:
        subprocess.run([
            "osascript", "-e",
            f'display notification "{message}" with title "{title}" sound name "Glass"'
        ], capture_output=True)
    except Exception:
        pass

def run(cmd):
    print(f"[RUN] {cmd}")
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if res.returncode != 0 and res.stderr:
        print(f"[ERR] {res.stderr.strip()}")
    return res

def is_already_patched(current_ver):
    ver_dir = os.path.join(VERSIONS_DIR, current_ver)
    fw_bin = os.path.join(ver_dir, "Google Chrome Framework")
    lib_egl = os.path.join(ver_dir, "Libraries/libEGL.dylib")
    launcher_dst = os.path.join(BASE_APP, "Contents/MacOS/Google Chrome")

    if not os.path.exists(fw_bin) or not os.path.exists(lib_egl) or not os.path.exists(launcher_dst):
        return False

    p1_patched = bytes.fromhex("84 c0 90 90 80 7d b8 00 74 cd 48 8b 45 b0")
    try:
        with open(fw_bin, "rb") as f:
            f.seek(0x4000)
            data = f.read(0x10051c10)
            return data.find(p1_patched) != -1
    except Exception:
        return False

def main():
    parser = argparse.ArgumentParser(description="Automated Chrome GPU patcher for legacy Mac GPUs")
    parser.add_argument("--check", action="store_true", help="Check if Chrome is already patched")
    parser.add_argument("--auto", action="store_true", help="Background watcher mode (checks and patches only if needed)")
    parser.add_argument("--notify", action="store_true", help="Send macOS notification on completion")
    args = parser.parse_args()

    if not os.path.exists(CURRENT_LINK):
        print(f"[!] Error: Chrome framework not found at {CURRENT_LINK}")
        print("    Please make sure Google Chrome is installed in /Applications.")
        return 1

    current_ver = os.path.basename(os.path.realpath(CURRENT_LINK))
    print(f"[*] Detected Chrome Framework version: {current_ver}")

    if args.check:
        patched = is_already_patched(current_ver)
        if patched:
            print(f"[+] Chrome {current_ver} is ALREADY patched.")
            return 0
        else:
            print(f"[-] Chrome {current_ver} is NOT patched.")
            return 1

    if args.auto:
        # Give GoogleUpdater a moment to finish file writing
        time.sleep(4)
        # Re-check current version after potential update completes
        current_ver = os.path.basename(os.path.realpath(CURRENT_LINK))
        if is_already_patched(current_ver):
            print(f"[*] Chrome {current_ver} is already patched. Nothing to do.")
            return 0
        print(f"[!] New/unpatched Chrome detected ({current_ver})! Commencing automatic patch...")

    ver_dir = os.path.join(VERSIONS_DIR, current_ver)
    lib_dir = os.path.join(ver_dir, "Libraries")
    os.makedirs(lib_dir, exist_ok=True)

    # 1. Copy ANGLE dylibs
    for dylib in ["libEGL.dylib", "libGLESv2.dylib"]:
        src = os.path.join(REF_ANGLE_LIB, dylib)
        dst = os.path.join(lib_dir, dylib)
        if os.path.exists(src):
            print(f"[*] Copying clean {dylib} to {current_ver}...")
            shutil.copy2(src, dst)
        else:
            print(f"[!] Warning: Reference dylib not found: {src}")

    # 2. Patch Google Chrome Framework binary
    fw_bin = os.path.join(ver_dir, "Google Chrome Framework")
    bak_bin = fw_bin + ".bak"
    if not os.path.exists(bak_bin):
        print("[*] Creating backup Google Chrome Framework.bak...")
        shutil.copy2(fw_bin, bak_bin)
    else:
        print("[*] Restoring clean binary from Google Chrome Framework.bak...")
        shutil.copy2(bak_bin, fw_bin)

    with open(fw_bin, "r+b") as f:
        slice_off = 0x4000
        f.seek(slice_off)
        data = f.read(0x10051c10)

        # Patch 1: GetAllowedGLImplementation (Allow ANGLE GL on macOS)
        p1 = bytes.fromhex("84 c0 74 0f 80 7d b8 00 74 cd 48 8b 45 b0")
        p1_patched = bytes.fromhex("84 c0 90 90 80 7d b8 00 74 cd 48 8b 45 b0")
        idx1 = data.find(p1)
        if idx1 != -1:
            print(f"[*] Found Pattern 1 at 0x{idx1:x}, applying patch (90 90)...")
            f.seek(slice_off + idx1 + 2)
            f.write(b"\x90\x90")
            print("[+] Pattern 1 patched successfully!")
        elif data.find(p1_patched) != -1:
            print("[+] Pattern 1 already patched.")
        else:
            print("[!] Warning: Pattern 1 not found in binary!")

        # Patch 2: GetDisplayInitializationParams (supports_angle_opengl)
        p2 = bytes.fromhex("84 c0 0f 85 06 06 00 00 48 b8 09 00 00 00 03 00 00 00")
        p2_patched = bytes.fromhex("84 c0 e9 07 06 00 00 90 48 b8 09 00 00 00 03 00 00 00")
        idx2 = data.find(p2)
        if idx2 != -1:
            print(f"[*] Found Pattern 2 at 0x{idx2:x}, applying patch (jmp +0x607)...")
            f.seek(slice_off + idx2 + 2)
            f.write(bytes.fromhex("e9 07 06 00 00 90"))
            print("[+] Pattern 2 patched successfully!")
        elif data.find(p2_patched) != -1:
            print("[+] Pattern 2 already patched.")
        else:
            print("[!] Warning: Pattern 2 not found in binary!")

        # Patch 3: InitializeGpuModes (force GpuMode::HARDWARE_GL fallback on macOS)
        p3 = bytes.fromhex("84 c0 0f 84 8b 00 00 00 c7 45 ac 03 00 00 00 48 8b 83 38 07 00 00")
        p3_patched = bytes.fromhex("84 c0 90 90 90 90 90 90 c7 45 ac 01 00 00 00 48 8b 83 38 07 00 00")
        idx3 = data.find(p3)
        if idx3 != -1:
            print(f"[*] Found Pattern 3 at 0x{idx3:x}, applying patch (force HARDWARE_GL)...")
            f.seek(slice_off + idx3)
            f.write(p3_patched)
            print("[+] Pattern 3 patched successfully!")
        elif data.find(p3_patched) != -1:
            print("[+] Pattern 3 already patched.")
        else:
            print("[!] Warning: Pattern 3 not found in binary!")

        # Patch 4: Prevent sandbox_check abort in GpuMain (CHECK(Seatbelt::IsSandboxed()))
        p4 = bytes.fromhex("89 c7 31 f6 31 d2 31 c0 e8 80 c4 f8 0b 85 c0 0f 84 ed 00 00 00")
        p4_patched = bytes.fromhex("89 c7 31 f6 31 d2 31 c0 e8 80 c4 f8 0b 85 c0 90 90 90 90 90 90")
        idx4 = data.find(p4)
        if idx4 != -1:
            print(f"[*] Found Pattern 4 at 0x{idx4:x}, applying patch (NOP out je abort)...")
            f.seek(slice_off + idx4 + 15)
            f.write(b"\x90\x90\x90\x90\x90\x90")
            print("[+] Pattern 4 patched successfully!")
        elif data.find(p4_patched) != -1:
            print("[+] Pattern 4 already patched.")

        # Patch 5: IOSurfaceImageBackingFactory::CreateSharedImageGMBs (texture_target = GL_TEXTURE_RECTANGLE 0x84f5)
        p5 = bytes.fromhex("488db578feffff488906418b4720458b47384c896c2418894424100fb645cc89442408c7042401000000")
        p5_patched = bytes.fromhex("488db578feffff488906418b472041b8f58400004c896c2418894424108904240fb645cc894424086690")
        idx5 = data.find(p5)
        if idx5 != -1:
            print(f"[*] Found Pattern 5 (IOSurface texture_target) at 0x{idx5:x}, patching to 0x84f5...")
            f.seek(slice_off + idx5)
            f.write(p5_patched)
            print("[+] Pattern 5 patched successfully!")
        elif data.find(p5_patched) != -1:
            print("[+] Pattern 5 already patched.")
        else:
            print("[!] Warning: Pattern 5 not found in binary!")

        # Patch 6: ScopedEGLSurfaceIOSurface::ValidateTarget -> return true (mov al, 1; ret)
        p6 = bytes.fromhex("55 48 89 e5 41 56 53 48 81 ec 30 01 00 00 81 fe e1 0d 00 00")
        p6_patched = bytes.fromhex("b0 01 c3 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90")
        idx6 = data.find(p6)
        if idx6 != -1:
            print(f"[*] Found Pattern 6 (ValidateTarget) at 0x{idx6:x}, patching to return true...")
            f.seek(slice_off + idx6)
            f.write(p6_patched)
            print("[+] Pattern 6 patched successfully!")
        elif data.find(p6_patched) != -1:
            print("[+] Pattern 6 already patched.")

        # Patch 7: IOSurfaceImageBacking constructor -> force gl_target_ = 0x84f5 (GL_TEXTURE_RECTANGLE_ARB)
        p7 = bytes.fromhex("8b 45 d0 89 83 88 01 00 00 8b 45 cc 88 83 8c 01 00 00 45 31 f6 44 89 b3 90 01 00 00 66 c7 83 94 01 00 00 00 00")
        p7_patched = bytes.fromhex("c7 83 88 01 00 00 f5 84 00 00 8a 45 cc 88 83 8c 01 00 00 45 31 f6 44 89 b3 90 01 00 00 66 44 89 b3 94 01 00 00")
        idx7 = data.find(p7)
        if idx7 != -1:
            print(f"[*] Found Pattern 7 (IOSurfaceImageBacking gl_target_) at 0x{idx7:x}, patching to 0x84f5...")
            f.seek(slice_off + idx7)
            f.write(p7_patched)
            print("[+] Pattern 7 patched successfully!")
        elif data.find(p7_patched) != -1:
            print("[+] Pattern 7 already patched.")
        else:
            print("[!] Warning: Pattern 7 not found in binary!")

    # 3. Compile and install custom launcher
    launcher_dst = os.path.join(BASE_APP, "Contents/MacOS/Google Chrome")
    if os.path.exists(LAUNCHER_SRC):
        print("[*] Compiling chrome_main.c into Google Chrome launcher...")
        res = run(f'clang -O2 "{LAUNCHER_SRC}" -o "{launcher_dst}"')
        if res.returncode == 0:
            print("[+] Google Chrome launcher installed successfully!")
        else:
            print("[!] Failed to compile Google Chrome launcher!")
            return 1
    else:
        print(f"[!] Error: Launcher source not found at {LAUNCHER_SRC}")
        return 1

    # 4. Code signing
    print("[*] Re-signing Chrome binaries with LocalCodeSigner...")
    for dylib in ["libEGL.dylib", "libGLESv2.dylib"]:
        dylib_path = os.path.join(lib_dir, dylib)
        if os.path.exists(dylib_path):
            run(f'codesign --force --sign "LocalCodeSigner" "{dylib_path}"')
    
    helpers_dir = os.path.join(ver_dir, "Helpers")
    if os.path.isdir(helpers_dir):
        for h in glob.glob(os.path.join(helpers_dir, "*.app")):
            run(f'codesign --force --deep --sign "LocalCodeSigner" "{h}"')

    run(f'codesign --force --sign "LocalCodeSigner" "{fw_bin}"')
    run(f'codesign --force --sign "LocalCodeSigner" "{ver_dir}"')
    run(f'codesign --force --sign "LocalCodeSigner" "{FRAMEWORK_DIR}"')
    run(f'codesign --force --sign "LocalCodeSigner" "{launcher_dst}"')
    run(f'codesign --force --deep --sign "LocalCodeSigner" "{BASE_APP}"')
    
    print("[*] Verifying signature...")
    v = run(f'codesign -v "{BASE_APP}"')
    if v.returncode == 0:
        print("[+] Signature VALID! Google Chrome is ready to run.")
        if args.notify or args.auto:
            notify("Chrome GPU Patch", f"Google Chrome {current_ver} has been patched successfully for your AMD GPU!")
    else:
        print("[!] Codesign verification warning:", v.stderr.strip())

    return 0

if __name__ == "__main__":
    sys.exit(main())
