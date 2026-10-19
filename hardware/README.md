# Hardware and wiring

[Project overview](../README.md) · [Bill of materials](BOM.md) · [Enclosure](enclosure/README.md)

This guide documents the USB DAC build: Raspberry Pi Zero W, Waveshare 2.8inch
DPI LCD, PAM8302A, mono speaker, volume control, and a combined screen/audio
switch. Power enters through the Pi's **PWR IN** micro-USB connector.

[![Rick TV wiring with photographs of the Pi, switch, micro-USB breakout, volume potentiometer, and PAM8302A](wiring.png)](wiring.png)

[Open SVG](wiring.svg) · [Download PNG](wiring.png)

The diagram uses **physical header numbers** alongside **BCM GPIO names**.
For example, GPIO26 is physical pin 37, not pin 26. The Raspberry Pi is shown
from the solder side using a real board photograph. Pin 1 is the square pad;
the numbering follows that rear view, with pin 2 beside it in the outer row. The display mounts on the opposite
side through the 40-pin header. External connections are drawn as continuous
wires without crossings. Dots mark joined branches.

## Power and display

1. Connect the enclosure micro-USB breakout **J1** to the Pi through the
   internal micro-USB power cable **CBL1** listed in the [BOM](BOM.md).
   The power path is **J1 breakout → CBL1 cable → Pi PWR IN**. Connect VBUS
   and GND through the cable.
2. Fit the Waveshare **DPI** display to the 40-pin header, aligning pin 1.
   Use an appropriate pass-through connection or solder access for the audio
   supply and switch.
3. Take amplifier **VIN / 2–5VDC** from Pi physical pin **2** (+5 V).
   Pin 4 is an alternative on the same rail. Take amplifier **GND** from
   physical pin **6**.

Use a single regulated 5 V supply through PWR IN. The 5 V rail powers the
amplifier directly.

## USB audio to mono speaker

1. Plug the DAC into the Pi's **USB** data socket through a micro-USB OTG
   adapter.
2. Connect the DAC's 3.5 mm **tip (L)** through **R1, 470 Ω** and **ring (R)**
   through **R2, 470 Ω**. Join the two resistor outputs to make the mono node.
3. Connect the mono node to one outer terminal of **RV1, 1 kΩ**. Connect the
   other outer terminal to GND, and the **wiper** to amplifier **A+ / Audio In+**.
   Identify the wiper by measurement; swap the outer terminals if the rotation
   direction is reversed.
4. Join the DAC **sleeve**, RV1 ground terminal, amplifier **A− / Audio In−**,
   and amplifier **GND** to the common ground net.
5. Wire the speaker only between amplifier **SP+** and **SP−**.
6. Leave **SD / Shutdown** unconnected on the Adafruit module in this build.
   The software mutes the USB DAC when the screen is off.

Do not join the DAC's L and R outputs directly. The two resistors isolate the
outputs before summing. Start at low playback volume and raise it while checking
for clipping.

## Screen and sound switch

**SW1 connects GPIO26 (physical pin 37) to GND (physical pin 39 is convenient).**
The runtime enables the Pi's internal pull-up. A closed contact turns the screen
and sound on; an open contact turns them off.

For a six-pin switch, use one common/switched pair from a single pole.
The diagram shows all six contacts by pole: A1/C1/B1 and A2/C2/B2.
C identifies the common contact; A and B identify the two throws without
assuming which one closes in the pressed state. Confirm the corresponding pair on the actual switch by continuity.

Set `RICK_TV_AUDIO_PROFILE=usb-dac`. The service mutes/unmutes ALSA card `1`,
control `PCM`, and controls the display backlight. It also switches GPIO18
(physical pin 12) between input and output-low as part of the existing display
control.
The Pi remains powered when the screen and sound are off.

## References and scope

- [Underside photograph: Pi Australia / Little Bird](https://piaustralia.com.au/products/raspberry-pi-zero-w)
- [Photo source and local asset](assets/README.md)
- [Official Pi Zero W revision 1.1 schematic](https://pip-assets.raspberrypi.com/categories/592-raspberry-pi-zero-w/documents/RP-008368-DS-1-raspberry-pi-zero-w-reduced-schematics.pdf)
- [Adafruit PAM8302 pinouts](https://learn.adafruit.com/adafruit-pam8302-mono-2-5w-class-d-audio-amplifier/pinouts)
- [Raspberry Pi GPIO documentation](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#gpio)
- [Waveshare 2.8inch DPI LCD guide](https://www.waveshare.com/wiki/2.8inch_DPI_LCD)
- [Power-control implementation](../rick-tv-pi/src/rick_tv_pi/power_button.py)
- [Packaged display configuration](../rick-tv-pi/provisioning/display/config.txt.waveshare-28dpi-legacy)

## Updating the drawing

Run `python3 hardware/render_wiring.py` from the repository root to rebuild
`hardware/wiring.svg`. Rasterize that SVG at its native 3750×2310 dimensions to
update `hardware/wiring.png`. The README displays the PNG for consistent image
support; the SVG embeds every photograph and does not depend on remote images.
