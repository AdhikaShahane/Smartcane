# Start automatically when the Pi gets power

You want: plug in the USB-C, walk away, come back — the cane is running.

That is exactly what **systemd** does. It is the standard way to run anything at
boot on Linux. No login, no desktop, no terminal window.

---

## The blunt version

**The Pi 4 has no power button.** "Plugging it in" *is* turning it on. The board
starts booting the instant power arrives.

Boot takes roughly **30–45 seconds** on a Pi 4. Your program is not the slow
part — the kernel and networking are. If the camera is a phone on WiFi, the
program must also wait for the network to come up before it can find it.

---

## Install it (one command)

```bash
cd ~/Smartcane
source ~/cane/bin/activate
bash tools/install_service.sh --mic 1
```

That writes `/etc/systemd/system/smartcane.service`, enables it, and prints how
to test it.

Start it now without rebooting:

```bash
sudo systemctl start smartcane
journalctl -u smartcane -f
```

Reboot to prove it:

```bash
sudo reboot
```

---

## ⚠️ Do NOT pass `--camera` in the service

This is the single most important detail.

Your phone's IP is `10.126.242.147` today. It is handed out by DHCP, so **it will
change** — next week, next reboot, or when the phone reconnects. A service with a
hardcoded URL will start and find nothing.

Leave `--camera` off. The cane already handles this:

1. it tries the **last URL that worked**, cached in `~/.smartcane_camera`
2. if that fails it **scans your WiFi for anything serving a webcam** on the
   usual port
3. it remembers whatever it finds

So `bash tools/install_service.sh --mic 1` — no camera URL — is the correct form.
It boots, finds the phone by itself.

If you *do* want a fixed URL, give the phone a **static IP** in the hotspot
settings first, then pass `--camera`.

---

## The other things that change between boots

**Microphone index.** `--mic 1` refers to the *second* capture device the system
happened to list. Plug in a different headset and the index moves.

Safer: omit `--mic` and let it pick the first real capture device, then check the
log line `microphone: device=N` after a reboot. If it picked wrong, set the index.

**The demo flag.** `install_service.sh` puts `--demo` in the service by default
because this is a demo build — the SOS alarm will say the location was shared.
Pass `--no-demo` if you want the honest alarm at boot instead.

---

## Managing it

| Task | Command |
|---|---|
| Start now | `sudo systemctl start smartcane` |
| Stop now | `sudo systemctl stop smartcane` |
| Restart | `sudo systemctl restart smartcane` |
| Status | `systemctl status smartcane` |
| Live log | `journalctl -u smartcane -f` |
| Log, today only | `journalctl -u smartcane --since today` |
| **Stop starting at boot** | `sudo systemctl disable smartcane` |
| **Remove completely** | `sudo systemctl disable --now smartcane && sudo rm /etc/systemd/system/smartcane.service` |

`systemctl stop` is temporary — a reboot brings it back. `systemctl disable` is
permanent.

---

## What can still go wrong (blunt)

| Problem | Why | Fix |
|---|---|---|
| Silence after boot | no audio device, or the wrong one | `journalctl -u smartcane -n 50` and look for `microphone:` / `TTS:` |
| Runs but sees nothing | phone not connected to the same WiFi | check `camera backend:` in the log |
| Restart loop | bad path or import error | `journalctl -u smartcane -n 100`, systemd retries 5 times then gives up |
| **SD card corrupted** | yanking power while writing | **use a power bank / UPS HAT.** Unplugging a running Pi is the #1 way to destroy the card |

That last one is not a software problem and no code fixes it. If this is a
portable cane, the Pi will get unplugged while running. Fit a small power bank
so it shuts down cleanly, or keep a spare SD card imaged.

---

## Why systemd and not the other options

| Method | Verdict |
|---|---|
| **systemd service** | ✅ correct tool. Starts at boot, restarts on crash, logs to journald |
| `crontab @reboot` | ❌ no restart on crash, no log capture, poor device access |
| `~/.bashrc` | ❌ only runs when you open a terminal — useless for a standalone device |
| Desktop autostart | ❌ needs a graphical login; slow, fragile on a headless cane |

Use systemd.
