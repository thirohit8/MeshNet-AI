[app]

# ── Application identity ───────────────────────────────────────────────────────
title        = MeshNet-AI
package.name = meshnetai
package.domain = org.meshnetai

# Source directory (relative to this file)
source.dir   = .

# Entry point
source.main  = main.py

# Include all Python source files and assets shipped with the APK
source.include_exts = py,kv,png,jpg,jpeg,atlas,json,enc
source.include_patterns = assets/*,tiles/**,logs/.gitkeep,data/.gitkeep

# ── Version ───────────────────────────────────────────────────────────────────
version      = 1.0.0

# ── Python requirements ────────────────────────────────────────────────────────
# All packages must be available as pre-compiled Android wheels or
# buildable from source via p4a recipes.
requirements = python3,\
               kivy==2.3.0,\
               kivymd==1.2.0,\
               kivy_garden.mapview,\
               pyjnius,\
               

# Garden packages loaded at build time by the kivy-garden tool
# Run:  garden install mapview  (before buildozer android debug)
garden_requirements = mapview

# ── Android target & build settings ───────────────────────────────────────────
android.api          = 33
android.minapi       = 26
android.ndk          = 25c
android.sdk          = 33
android.ndk_path     =
android.sdk_path     =
android.ant_path     =

# ABI targets — arm64-v8a for modern devices, armeabi-v7a for legacy
android.archs        = arm64-v8a, armeabi-v7a

# Enable AndroidX support (required by KivyMD 1.x)
android.enable_androidx = True

# ── Permissions ────────────────────────────────────────────────────────────────
# Declared here so the APK manifest includes them.
# Runtime dangerous-permission requests are handled in main.py
android.permissions = \
    BLUETOOTH,\
    BLUETOOTH_ADMIN,\
    BLUETOOTH_SCAN,\
    BLUETOOTH_CONNECT,\
    BLUETOOTH_ADVERTISE,\
    ACCESS_WIFI_STATE,\
    CHANGE_WIFI_STATE,\
    ACCESS_FINE_LOCATION,\
    ACCESS_COARSE_LOCATION,\
    READ_EXTERNAL_STORAGE,\
    WRITE_EXTERNAL_STORAGE,\
    INTERNET,\
    ACCESS_NETWORK_STATE,\
    FOREGROUND_SERVICE,\
    WAKE_LOCK,\
    RECEIVE_BOOT_COMPLETED

# ── Manifest meta-data ────────────────────────────────────────────────────────
android.meta_data =

# Extra uses-features for BT & Wi-Fi hardware requirements
android.add_manifest_xml = \
    <uses-feature android:name="android.hardware.bluetooth" android:required="true" />,\
    <uses-feature android:name="android.hardware.wifi"      android:required="true" />

# ── Application flags ─────────────────────────────────────────────────────────
android.add_flags = FLAG_KEEP_SCREEN_ON

# ── p4a bootstrap ─────────────────────────────────────────────────────────────
p4a.bootstrap    = sdl2
p4a.branch       = master
p4a.source_dir   =

# ── Icons & splash ───────────────────────────────────────────────────────────
icon.filename      = %(source.dir)s/assets/icon.png
presplash.filename = %(source.dir)s/assets/presplash.png
android.presplash_color = #1A1A20

# ── Orientation ───────────────────────────────────────────────────────────────
orientation = landscape

# ── Fullscreen ────────────────────────────────────────────────────────────────
fullscreen = 0

# ── Log level ─────────────────────────────────────────────────────────────────
log_level    = 2

# ── Build output ──────────────────────────────────────────────────────────────
android.release_artifact = apk

[buildozer]

# Buildozer working directory
build_dir   = ./.buildozer

# Output directory for compiled APK/AAB
bin_dir     = ./bin

# Log level: 0=error 1=info 2=debug
log_level   = 2

warn_on_root = 1
