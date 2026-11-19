# EventPics Photobooth

Software for a self-built photo booth on the Raspberry Pi: live view and
countdown in full screen, a single picture or a collage with frames and
lettering, printing on a Canon Selphy, a backup copy on a USB stick and, if you
want it, upload to EventPics with a QR code for every picture. It is operated on
a touchscreen; the settings sit behind a PIN.

The interface is a program of its own (Qt), not a browser and not a web server.
The live image goes straight from the camera onto the GPU. The box can only be
operated at its own screen — nobody on the network can trigger it, delete from
it or print from it. The interface is built for 1920 × 1200 and scaled as a
whole on any other screen.

*Diese Datei auf Deutsch: [README.de.md](README.de.md).*
Build guide and bill of materials (German):
<https://event.pics/de/fotobox-selber-bauen.html>

## On the Raspberry Pi

**Raspberry Pi OS Lite (64-bit)** is recommended, written with the Raspberry Pi
Imager.

```bash
sudo apt update && sudo apt install -y git
git clone https://github.com/eventpics/photobooth.git
cd photobooth
bash install-pi.sh          # packages, SPI
bash autostart/setup.sh     # start at power-on, touch, USB stick, PIN
sudo reboot
```

After the reboot the booth is on the screen. You reach the settings through the
gear icon with the PIN that `setup.sh` asked for. Forgotten the PIN?
`bash set-pin.sh` sets a new one without knowing the old one.

Everything comes from the Raspberry Pi OS package sources, nothing through pip,
and there is no virtualenv: picamera2 and the Qt bindings (PySide6) are built
there to fit the Pi.

Useful while it runs:

```bash
systemctl status photobooth
journalctl -t photobooth -f        # the app's own messages
sudo systemctl restart photobooth
```

## Developing on a desktop

Runs on macOS and Linux with a simulated camera and GPIO in memory. Mock mode is
detected automatically (`config.json` → `app.mock: "auto"`).

```bash
cp config.example.json config.json
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python photobooth.py --window --scale 0.5
```

`--window` opens a window instead of full screen, `--scale` shrinks the stage to
fit a laptop. Esc quits.

### Stress test

`tools/stress_test.py` operates the real app the way guests at a wedding would:
single pictures, series of three and four, a hectic block with changing layouts,
with retries and discards in between. Every series lands in `/tmp/stress.jsonl`
with its duration, capture time, memory, temperature and upload queue. How to
start it on the Pi is documented at the top of the file. The pictures really are
saved and uploaded.

On a Pi 4 with 1 GB (September 2026): 40 hectic series without a failure, median
0.27 s and at most 0.36 s from the shutter to the next step, 290 to 360 MB of
memory, never above 63 °C.

### System monitoring

The dot at the top left of the screen opens the status: camera, USB stick,
printer, network, gallery, temperature, memory, processor and free space. It
answers the question that otherwise comes up on the night of the event: does the
box get too hot inside a closed enclosure?

The processor clock is always shown next to its ceiling. Far below it means the
Pi is throttling — because of heat or because of **under-voltage**. That is by
far the commonest reason a Raspberry Pi behaves strangely for no apparent
reason: usually a weak power supply, a bad USB-C cable, or a screen drawing
power from the Pi through its touch cable.

The Pi throttles from about 80 °C. Up to 70 °C nothing is unusual.

### Watchdog

If the app crashes, systemd restarts it three seconds later. For the harder case
— still running but no longer doing anything, because the camera stopped
answering, say — it writes a timestamp to `/dev/shm/photobooth-alive` every five
seconds, from its own interface tick. If that is more than a minute old,
`photobooth-watchdog.service` restarts it.

### Start and shutdown screen

From power-on to a working interface takes about thirty seconds on a Pi 4, and
the console is deliberately silent (`quiet`, `logo.nologo`). Left alone the
screen stays black for all of it, which from the outside looks exactly like a
box that is not starting at all.

So `photobooth-splash.service` draws straight into the framebuffer within the
first second of userspace: white, black mark, "EventPics Fotobox wird
gestartet", a moving bar underneath. On the way down
`photobooth-shutdown.service` puts up the same screen with the line **"Gleich
kannst du den Strom trennen"**. The booth has no clean power switch, and
cutting power too early is exactly what leaves a filesystem needing repair.

The picture is rendered beforehand, not at boot. The first version built it
with Pillow and reached the screen 20 seconds into a 23 second boot: fourteen
of those went on importing numpy and Pillow while udev and the journal were
saturating the same SD card. Now `boot-splash.py --render` writes raw
framebuffer dumps to `/var/cache/photobooth` and `boot-splash.sh` pushes one
out with `dd`, no Python involved. Both colour depths are rendered, because
the framebuffer reports 32 bits early in the boot and 16 a moment later.

Keeping the shutdown screen up took two more changes, both of them found by
measuring on the booth rather than by reasoning: systemd writes its
"Stopped ..." lines to the console while the machine goes down, and that
console lands on whichever terminal is being displayed. The picture vanished
under a wall of text.

- `cmdline.txt` says `console=tty3` instead of `console=tty1`, so nothing of
  the console is visible while terminal 1 is on screen.
- `boot-splash.sh shutdown` unbinds the text console from the framebuffer
  (`vtcon*/bind`) before it draws. Nothing writes over the picture after
  that. It lasts until the next boot and the journal still gets everything.

`systemd.show_status=error` on its own is not enough; the status lines come
back during shutdown regardless. All of this was checked by having the booth
save its own screen contents at the very end of a shutdown: 44 % covered in
text before, 98.6 % white after.

### Copying to the booth

With `tools/deploy.sh`, never with a hand-typed `rsync`. The booth holds files
that exist nowhere else and are all in `.gitignore`: the lamp's mesh keys, the
configuration with the PIN and the API key, the journal database, the
captures. A plain `rsync --delete` wipes them without a word. That happened
once, and the lamp had to be provisioned again afterwards.

The script carries the exclude list, compares before and after that the
irreplaceable files are still there, pre-renders the splash screens and only
then restarts. `tools/deploy.sh --dry-run` shows what would happen first.

### Wi-Fi

The box joins a wireless network from its own screen: **Einstellungen → WLAN**,
pick a network, type the key on the on-screen keyboard. No cable, no keyboard,
no SSH. That matters at a venue, where the network is never the one from home.

It works without any extra privilege, which is worth knowing because it looks
like it should not. The booth runs under cage in a real local login session on
seat0 — that is what `PAMName=login` and `TTYPath=/dev/tty1` in
`photobooth.service` are for — and polkit grants an active local session
`network-control` and `settings.modify.system` by default. Checked with
`pkcheck` against the running process: allowed. The same `nmcli` command over
SSH is refused with "System policy prevents control of network connections", so
this cannot be tested remotely; it has to be tried on the box.

Two things block the radio on a fresh Raspberry Pi OS, and both are easy to
miss because neither reports an error:

```bash
sudo raspi-config nonint do_wifi_country AT     # your country, or the radio stays blocked
sudo rfkill unblock wifi
sudo nmcli radio wifi on
```

The key never travels in `argv`, where every local process could read it out of
`ps`: `nmcli --ask` takes it on standard input instead. A failed attempt
deletes the profile it would otherwise leave behind, so a mistyped key does not
haunt the box on every boot.

### Little memory (1 GB)

Raspberry Pi OS reserves a fixed 512 MB for camera and graphics on devices with
1 GB; about 390 MB are left for everything else. If that gets tight, halve the
reservation in `/boot/firmware/config.txt`:

```
dtoverlay=vc4-kms-v3d,cma-256
```

Then reboot.

### Camera

Configured for the **Raspberry Pi Camera Module 3 Standard** (IMX708 sensor,
76° diagonal). The sensor delivers 4608×2592 in 16:9; for a 10×15 cm print that
is cropped to 3:2 — in the live view exactly as in the photograph, so the screen
shows what gets printed.

```bash
rpicam-hello --list-cameras
```

If no camera is found it is usually the ribbon cable or the way round it sits.
The 15-pin cable fits a Pi 3 and Pi 4, the 15-to-22-pin cable a Pi 5. Cameras
usually ship with both.

**Calibrating.** Put somebody at the real standing distance, darken the room and
tap **Automatisch einmessen** in the settings. The box first finds the **capture
light** by itself: not the brightest, but the dimmest that still freezes
movement (target 1/125 s). Exposure, white balance and focus are then measured
under it and pinned down. Because an exposure only fits the brightness it was
measured under, the two are taken together — the result screen shows the value
it found and offers to keep the old light, which puts the previous value back
and measures again.

`LensPosition` is in dioptres, that is 1 divided by the distance in metres —
2.0 m is 0.5, and 2.5 m is 0.4.

### Sound

The box is silent. There were sounds once, over the screen's HDMI connection: a
counting countdown, a click at the shutter, a chord for the finished sheet. They
went again in October 2026 — nobody hears them at a party anyway, and what you
cannot hear you do not have to configure, explain or repair.

The countdown is large on the screen, and the flash says the shutter fired.

### Wiring

| Function | GPIO (BCM) | Header pin | Connection |
|---|---|---|---|
| Shutter button | 17 | 11 | to GND, internal pull-up |
| Button LED | 27 | 13 | through 330 Ω, through a MOSFET for a 12 V LED |
| Light (PWM) | 18 | 12 | to the gate of the MOSFET module |
| Ground | GND | 6, 9, 14 … | common ground with the 12 V supply |

### What the lamp hangs off

The box knows four kinds of light, set under `light.kind` or in the settings
under "Erweitert":

| `kind` | Lamp | Dimming |
|---|---|---|
| `pwm` | home-made 12 V panel on a MOSFET module | through the Pi's PWM |
| `dmx` | any fixture on a DMX bus | through DMX512 |
| `godox` | a Godox lamp | over Bluetooth, brightness and colour temperature |
| `none` | a bought lamp with no remote control | not at all |

If the box cannot change the brightness, the light buttons on the guest screen
and the light card in the settings disappear. If it cannot change the colour
temperature — everything except `godox` — that field disappears. A control that
does nothing confuses more than it helps.

**The colour temperature sits behind the PIN**, not on the guest screen. Anyone
may change the brightness of the modelling light; it has no influence on the
photograph. The colour does: the white balance is calibrated to it, and somebody
turning it in passing tints every picture of the evening.

**Godox over Bluetooth.** These lamps are nodes in a Bluetooth mesh, not simple
BLE devices. The protocol has been reverse engineered; `install-pi.sh` fetches
the library into `vendor/godox-mesh` (MIT). Setup happens once on the command
line, with the lamp in pairing mode:

```bash
cd vendor/godox-mesh
export PYTHONPATH=src
python3 -m godox_mesh_bt scan --timeout 10          # find the address

# Without --address: the command scans itself and connects straight afterwards.
python3 -m godox_mesh_bt provision --output ../../godox-mesh-state.json

# The next commands need a scan running alongside, or they fail with
# "device not found" - see below.
(timeout 30 bluetoothctl scan on >/dev/null &) ; sleep 6
python3 -m godox_mesh_bt rebind --device <address> --state ../../godox-mesh-state.json
python3 -m godox_mesh_bt set --device <address> --state ../../godox-mesh-state.json \
    --brightness 50 --cct 4000
```

Then set `light.kind` to `godox` and `light.address` to the address. This
**replaces the pairing with the Godox app** — the app sees the lamp again only
after a factory reset.

Three things we learned on the Pi, which the software handles:

- **Scan first, then connect.** BlueZ only resolves an address it has seen
  recently; without a scan every start fails with "Device not found".
- **The mesh counter must never fall back.** Every command consumes a sequence
  number, and the lamp silently discards anything it has seen before — no error,
  it simply does nothing. The counter is therefore advanced by 2000 at startup
  and saved immediately.
- **The key file is written atomically.** It holds the mesh keys; lose it and
  the lamp has to be provisioned again. A power cut in the middle of a write
  once truncated it to zero bytes on the Pi.

Bluetooth has to stay on for this — `optimize-boot.sh` therefore no longer
disables it.

**DMX.** DMX512 is the standard of the events industry; it drives practically
any fixture. The Pi needs a TTL to RS-485 converter: either a USB adapter with
an FTDI chip, which appears as `/dev/ttyUSB0` and leaves Bluetooth free, or a
MAX485 on `/dev/serial0`. The second is cheaper, but the Pi's mini UART is tied
to the core clock and does not hit 250000 baud reliably — that would mean
putting the full UART on the header, and it is reserved for Bluetooth out of the
box. Settings: `light.dmx_port`, `light.dmx_channel`, and for fixtures that want
a mode channel set before they dim, `light.dmx_extra` as `{"channel": value}`. A
background thread sends 30 packets a second, because a DMX receiver falls to
black after about a second without one. Needs `python3-serial`, which
`install-pi.sh` installs.

### Flicker and PWM frequency

Dimmed PWM light and a short exposure work against each other: if only a handful
of light pulses fall into one exposure, chance decides how many, and a sensor
that reads out line by line paints that into the picture as banding.

Measured on a Pi 4 with a D4184 module and 6.5 ms exposure, banding in the
picture at a 30 % dimming value:

| PWM | Banding at 30 % | Banding at 3 % | Dimming curve |
|---|---|---|---|
| 200 Hz | 19 % | 65 % | nearly linear |
| 1 kHz | 7 % | – | slightly compressed |
| **2 kHz** | **2.5 %** | **8.5 %** | 3 % dimming gives 20 % light |
| 5 kHz | 2.3 % | – | 30 % gives 68 % |
| 10 kHz | 2.9 % | – | 30 % gives 94 %, barely dimmable |

**2 kHz is the default.** Below it you see banding, above it the dimming falls
apart: the MOSFET's gate is discharged through a resistor, and the shorter the
period the less it manages to switch off completely. A module with a real gate
driver would be clean and linear at 10 kHz too. The dimming curve is compressed
as a result — 5 % dimming gives about 22 % light, 30 % gives 51 %.

### Hardware PWM instead of software PWM

The signal is generated by the chip's PWM block, not by lgpio. The difference
only shows under load: lgpio counts its edges on a thread, and when the cores
are busy they slip. Measured on a Pi 4, light at 5 %, brightness of the live
image over 60 seconds each:

| | idle | with four cores at full load |
|---|---|---|
| lgpio, in software | ±1.8 % | **jumps of up to +20 %, every 4 seconds** |
| the chip's PWM block | ±0.4 % | ±0.2 % |

You see that as the lamp flickering, several times a minute. It needs one line
in `config.txt`, which `autostart/setup.sh` adds:

```
dtoverlay=pwm,pin=18,func=2
```

**One trap:** the overlay puts the pin on its PWM function at boot. If anything
claims it as an ordinary output afterwards — the software fallback when a start
goes wrong, for instance — the PWM block keeps running but its signal no longer
reaches the pin: registers set cleanly, lamp dark, nothing in the log.
`HardwarePwm` therefore puts the pin back itself on every start
(`pinctrl set 18 a5`) and checks afterwards.

If the PWM block is not there, the light runs through gpiozero as before, and a
warning goes into the log.

The capture itself is not affected: a second before the shutter the light goes
to full power, and at 100 % there is no PWM any more. What is left measures
2.6 % of scatter, and that is image noise.

**Never 12 V on a GPIO pin.** The lamp is switched exclusively through the
MOSFET, and the 12 V supply's ground must be connected to the Pi's ground.

### Addressable LED strip (WS2812B)

Optional, for status and countdown light. **Not as the main light** — RGB pixels
mix white from three narrow spectral lines, under which skin tones look bad, and
their internal PWM works against short exposures.

Driven over SPI rather than the usual DMA library: that needs no root, does not
collide with the onboard audio output, and works on a Pi 5 as well.

| Signal | Connection |
|---|---|
| Data (DIN) | GPIO 10, pin 19 (SPI MOSI) |
| Ground | GND, common with the strip's power supply |
| 5 V | its own supply, **not** from the Pi beyond a few LEDs |

`install-pi.sh` enables SPI. **Level shifter:** WS2812B expect about 3.5 V on
the data line, the Pi delivers 3.3 V. Short strips often run anyway, longer ones
flicker. A 74AHCT125 as a level shifter makes it clean.

**Wrong colours?** If red comes out green, your strip has a byte order other
than GRB — then it is not a WS2812B but a relative.

### Setting up the printer

```bash
sudo lpinfo -v | grep -i canon          # the attached device and its serial
sudo lpinfo -m | grep -i selphy         # matching drivers
sudo lpadmin -p Selphy -E \
     -v "usb://Canon/SELPHY%20CP1500?serial=<serial>" \
     -m "gutenprint.5.3://canon-cp1300/expert"
sudo lpadmin -p Selphy -o PageSize=Postcard -o StpBorderless=True -o StpImageType=Photo
sudo lpadmin -d Selphy
lpstat -p -d
```

**The CP1500 is missing from Gutenprint 5.3.4** — the driver is older than the
printer. Use the **CP1300**: the same protocol family (`CMD:Raster3`), and the
CP1500 prints with it. `StpBorderless=True` is mandatory for photographs or a
white border is left; `StpImageType=Photo` switches the dithering.

**The trap that costs an hour:** `ipp-usb` grabs every USB printer as it is
plugged in and looks for IPP and a scanner. On a Selphy it finds neither, resets
the printer and occasionally leaves a connection open. Afterwards `lpinfo -v`
reports no USB device at all, the printer still shows in `lsusb`, and the log
only says `Failed to detach "usblp" module` — which points the wrong way,
because `usblp` is innocent. `install-pi.sh` therefore writes
`/etc/ipp-usb/quirks/photobooth.conf`:

```
[Canon SELPHY *]
  blacklist = true
```

After that `Device is blacklisted` appears in the ipp-usb log on plug-in, and
CUPS gets the printer.

The booth prints to the **default printer** of CUPS:

```bash
sudo lpadmin -d Selphy
```

`Postcard.Fullbleed` in `config.json` (`printer.media`) is the usual value for
10×15 cm borderless on a Selphy — if the print comes out cropped, start here.
To test it, take a photograph and tap "Drucken".

## Worth knowing

- **PWM light and short exposures work against each other.** A dimmed LED strip
  produces visible brightness differences from picture to picture at short
  exposures. That is why the light goes to 100 % duty for the capture, i.e.
  continuously on instead of dimmed.
- **No xenon flash.** The Pi sensors have a rolling shutter; a short flash
  exposes only part of the frame.
- **Captures are written in the background.** picamera2 handles a capture on the
  interface's thread. It used to encode and write the JPEG there too; if the SD
  card happened to be busy, the interface stalled with it, and every twentieth
  capture took up to 3.5 seconds. Now only the pixels are copied there, writing
  happens on a thread of its own, and anyone who needs the file waits for it
  with `wait_for_writes()`.

## Autostart

`bash autostart/setup.sh` installs everything a photo booth without a keyboard
needs. Undo it with `bash autostart/setup.sh --remove`. It also clears away the
services of an older version that used a browser kiosk.

| File | What for |
|---|---|
| `photobooth.service` | the booth full screen in cage, restarts on a crash |
| `photobooth-watchdog.service`, `watchdog.sh` | restarts the booth when the interface hangs |
| `hide-cursor.py` | invisible mouse pointer, for touchscreens that register as a mouse |
| `photobooth-touch.service`, `touch-bridge.py` | touchscreens that register as a mouse |
| `99-photobooth-usb.rules`, `usb-mount.sh` | mount a USB stick without a desktop |
| `50-photobooth-journal.conf` | the system journal survives a reboot |
| `optimize-boot.sh` | shorter boot, undo with `--undo` |

## Layout

```
photobooth.py               entry point
config.example.json         all adjustable values; copy to config.json
install-pi.sh               packages, SPI
set-pin.sh                  set a new PIN for the settings
booth/
  backend.py                wires camera, sequence, upload and backup together
  session.py                the sequence of one capture
  layouts.py, overlays.py   collages, frames, lettering
  eventpics.py              upload and a QR code per picture
  usb.py, journal.py        backup on the stick, the queue
  admin.py                  the PIN and the settings fields
  palette.py                colour roles and the ready-made schemes
  hardware/                 camera (picamera2), GPIO (gpiozero/lgpio), LED strip,
                            printer (CUPS), Wi-Fi (NetworkManager), system values -
                            each with a simulation
  ui/                       the interface: guests, settings, keyboard, PIN
autostart/                  autostart, watchdog, touch, USB, boot time
tools/stress_test.py        stress test with the real camera
docs/                       decisions and the reasons for them
```

RPi.GPIO is deliberately not used — it does not work on the Pi 5. gpiozero
reaches lgpio there.

## Language

Code, comments and file names are English. What guests and builders read is
German: the interface, the messages on screen, the settings labels and the build
guide. Stored values and option names are English, their labels German.

## Licence

GPL-3.0-or-later. See [LICENSE](LICENSE).

You may use this software for anything, commercial work included. If you change
it and pass it on, you have to make your source available under the same
licence. That is the point: a photo booth business can build on this, but cannot
turn it into a closed product with the EventPics upload quietly removed.

The library in `vendor/godox-mesh` is fetched by `install-pi.sh` and is not part
of this repository. It carries its own MIT licence.
