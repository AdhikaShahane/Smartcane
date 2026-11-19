# Camera over WiFi — making it automatic

There are **three devices** in this rig, not two:

```
   PHONE                    RASPBERRY PI                 LAPTOP
   IP Webcam app  ──wifi──>  smartcane          <──wifi──  ssh / PowerShell
   serves the video          consumes it                    runs commands
```

The camera is not plugged into the Pi. It is a **web stream on the network**.
Everything fragile about this setup comes from that one fact.

---

## Why it breaks on its own

`10.126.242.147` is a **DHCP address**. The network hands it out and takes it
back. Reconnect the phone, reboot the router, wait a day — the number changes.

A service with a hardcoded URL then starts, finds nothing, and the cane runs
with no vision. **This is the number one thing that will bite you.**

---

## The fix: make the phone the hotspot

This is the recommendation. One change and the whole problem disappears.

**On the phone:** turn on Mobile Hotspot **and** run IP Webcam at the same time.
The phone is now both the network and the camera, so its address is fixed by
the hotspot design:

| Phone | Camera URL |
|---|---|
| Android hotspot | `http://192.168.43.1:8080/video` |
| iPhone hotspot | `http://172.20.10.1:8080/video` |

Those addresses **do not change.** Same every boot, every day.

Then:

1. **Pi** joins the phone's hotspot
2. **Laptop** joins the same hotspot
3. The laptop finds the Pi with `ping raspberrypi.local` (or check the phone's
   hotspot client list for its IP)
4. Install the service with the camera URL, because now it is stable:

```bash
bash tools/install_service.sh \
  --camera "http://192.168.43.1:8080/video" \
  --mic 1
```

That is fully automatic from then on. Plug in the Pi → joins the hotspot →
opens the stream → starts guiding.

### Why not stay on college WiFi?

| | Phone hotspot | College / shared WiFi |
|---|---|---|
| Phone IP | **fixed** | changes constantly |
| Can the Pi reach the phone? | yes | **often no** — many campus networks enable *client isolation*, which blocks device-to-device traffic |
| Works with no internet | **yes** | no |
| Setup time | 30 seconds | variable |

Client isolation is the killer: the Pi and phone can both be "connected" and
still unable to see each other. A hotspot always works.

---

## What is already automatic (no work for you)

| Behaviour | Where |
|---|---|
| Remembers the last working camera URL | `~/.smartcane_camera` |
| If the cached URL fails, **scans the subnet** for a webcam | `camera.discover_ip_webcams()` |
| Remembers whatever it discovered | same cache file |
| **Reopens the camera when WiFi drops** | `Camera._note_grab_failure()` |
| Refuses to fake the picture when a real camera is lost | `CAM_SYNTHETIC_ON_LOSS = False` |
| Starts at boot, restarts on crash | systemd unit |

That last one matters: before, a dropped WiFi made the cane switch to a
**synthetic moving block**. The detector would happily report that fake block as
an obstacle. Now it says nothing and keeps reconnecting, and the log shows:

```
WARNING camera  camera lost (15 dead frames) - reconnecting
INFO    camera  camera reconnected: cv2:http://192.168.43.1:8080/video
```

---

## One-time setup on the Pi

```bash
# join the hotspot once; NetworkManager remembers it forever
sudo nmcli device wifi connect "MyPhoneHotspot" password "thepassword"
```

That persists across reboots. The systemd unit waits for
`network-online.target` before starting, so the cane never races the WiFi.

---

## Degrading the video so it actually streams

Their log showed this on every frame:

```
[mjpeg @ 0x2d0ab350] overread 8
```

That is the MJPEG stream arriving damaged — normal for a phone on WiFi. In the
**IP Webcam app**, lower these:

| Setting | Set to |
|---|---|
| Video resolution | **640 × 480** (not 1080p) |
| Video quality | 50–60 % |
| FPS | 15 |

The detector runs at 320 px anyway. A smaller stream is not a quality loss — it
is a latency and reliability **gain**, and it stops the overread errors.

---

## Things that still need a human

| Situation | Why it cannot be automated |
|---|---|
| Phone reboots or kills IP Webcam | the Pi can retry, but nothing on the network can restart the app for you |
| Phone screen locks and the app is suspended | disable battery optimisation for IP Webcam |
| Hotspot off | no network, no camera, no SSH |
| A different phone | new URL; delete `~/.smartcane_camera` so it rescans |

**One tip:** put the phone on a charger and set IP Webcam to keep the screen on.
A phone that sleeps is the most common cause of a dead demo.

---

## Checklist before the demo

```bash
# on the Pi
ip a | grep 192.168.43          # is it on the hotspot?
curl -sI http://192.168.43.1:8080/ | head -1   # does the phone answer?
ls -l ~/.smartcane_camera       # what URL does it remember?
systemctl status smartcane      # is the service running?
journalctl -u smartcane -n 30   # what did it say at boot?
```

If `curl` fails, the problem is the network or the phone — **not the code**.
That distinction saves hours.
