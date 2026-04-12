# APrender — functional test in Docker

Functional testing of APrender (Album Player DLNA/UPnP renderer) without real audio hardware.

## Setup

1. **Download APrender** for your platform:
   - Go to <https://albumplayer.ru/linux/>
   - Download the **x64** archive (for Docker on x86/macOS) or **ARM** (for ARM hosts)
   - Extract and copy `ap2renderer` binary into `./bin/`:

   ```bash
   mkdir -p bin
   # Example for x64:
   wget -O /tmp/ap2renderer.tar.gz "https://albumplayer.ru/linux/ap2renderer_x64.tar.gz"
   tar xzf /tmp/ap2renderer.tar.gz -C bin/
   ```

2. **Start the container:**
   ```bash
   docker compose up --build
   ```

3. **Open the web UI:**
   ```
   http://localhost:7779
   ```

## How it works

- Uses `snd-dummy` kernel module (Linux host) or ALSA null output (macOS Docker Desktop) — no real sound card needed.
- The container runs `ap2renderer` which exposes a web UI on port 7779.
- UPnP/DLNA discovery works on the Docker network; use `network_mode: host` if you need LAN discovery.

## Notes

- **macOS Docker Desktop**: `snd-dummy` won't load (kernel modules not available). The entrypoint falls back to ALSA null output — enough for UI/API testing.
- **Linux host**: `--privileged` allows `modprobe snd-dummy` to create a virtual sound card. Full functional testing possible.
- **Real audio testing**: mount a USB DAC via host passthrough instead of using this Docker setup.

## LAN discovery (optional)

To make APrender visible to DLNA control points on your local network:

```yaml
services:
  aprender:
    network_mode: host   # add this
```
