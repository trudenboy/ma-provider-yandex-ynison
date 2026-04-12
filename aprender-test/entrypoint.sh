#!/bin/bash
set -e

echo "=== APrender functional test container ==="

HAVE_CARD=false

# Try to load virtual sound card (Linux host with --privileged)
modprobe snd-dummy 2>/dev/null && { echo "[*] snd-dummy loaded."; HAVE_CARD=true; } || \
modprobe snd-aloop 2>/dev/null && { echo "[*] snd-aloop loaded."; HAVE_CARD=true; } || \
echo "[!] No kernel audio modules available."

if [ "$HAVE_CARD" = false ]; then
    echo "[*] Mounting fake /proc/asound + ALSA null config..."

    # Mount fake /proc/asound over the real (empty) one
    mkdir -p /proc/asound
    mount --bind /fake-asound /proc/asound 2>/dev/null || {
        echo "[!] bind mount failed, trying tmpfs..."
        mount -t tmpfs none /proc/asound
        cp -r /fake-asound/* /proc/asound/ 2>/dev/null || true
    }

    # Create fake /dev/snd device nodes
    mkdir -p /dev/snd
    [ -e /dev/snd/controlC0 ] || mknod /dev/snd/controlC0 c 116 0 2>/dev/null || true
    [ -e /dev/snd/pcmC0D0p ] || mknod /dev/snd/pcmC0D0p c 116 16 2>/dev/null || true
    [ -e /dev/snd/timer ] || mknod /dev/snd/timer c 116 33 2>/dev/null || true
    chmod 666 /dev/snd/* 2>/dev/null || true

    cat > /etc/asound.conf <<'EOF'
pcm.!default {
    type null
}
pcm.hw {
    type null
}
pcm.plughw {
    type null
}
ctl.!default {
    type null
}
ctl.hw {
    type null
}
EOF
    echo "[*] Fake audio environment ready."
fi

echo "[*] /proc/asound/cards:"
cat /proc/asound/cards 2>&1 || echo "(missing)"
echo "[*] /dev/snd/:"
ls -la /dev/snd/ 2>&1 || echo "(empty)"
echo "[*] ALSA devices:"
aplay -l 2>&1 || echo "(no hardware — using null)"

# Find binary
BINARY=""
for f in /opt/aprender/ap2renderer /opt/aprender/aprenderer/ap2renderer; do
    [ -f "$f" ] && BINARY="$f" && break
done

if [ -z "$BINARY" ]; then
    echo " ap2renderer binary not found!"
    exec sleep infinity
fi

chmod +x "$BINARY"
cd "$(dirname "$BINARY")"

echo "[*] Starting APrender on port 7779..."
exec "$BINARY"
