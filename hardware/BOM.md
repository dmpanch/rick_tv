# Bill of materials

[Project overview](../README.md) · [Wiring](README.md) · [Enclosure](enclosure/README.md)

Parts for one Rick TV using the USB DAC audio profile. Quantities refer to
individual components, even when a linked listing sells an assortment or pack.

## Computer, display, and power

- **U1 · 1 × Raspberry Pi Zero W.**
  [Raspberry Pi product page](https://www.raspberrypi.com/products/raspberry-pi-zero-w/).
  Fit a 2×20, 2.54 mm GPIO header if the board has none.
- **DS1 · 1 × Waveshare 2.8inch DPI LCD with capacitive touch.**
  Native resolution 480×640, used in landscape orientation by Rick TV.
  [Waveshare product page](https://www.waveshare.com/2.8inch-dpi-lcd.htm).
  Use the DPI version and its matching 40-pin connector.
- **1 × microSD card.** At least 8 GB; allow extra space for the local video
  library and the flashed image.
- **PS1 · 1 × regulated 5 V USB power supply and cable.**
  A 2 A supply is a reasonable build target; check voltage under load with the
  display and audio running. The current build enters through the Pi's PWR IN.
- **J1 · 1 × micro-USB female breakout board.**
  [Supplied Amazon link](https://www.amazon.co.uk/Breakout-Female-Socket-Adapter-Connector/dp/B07R9SMJKF).
  Its VBUS and GND feed the Pi through the internal cable CBL1.
- **CBL1 · 1 × internal micro-USB power cable.**
  [Supplied Amazon link](https://www.amazon.co.uk/Micro-Charger-Cable-Braided-Cables/dp/B08XQRV5W1).
  Connects the breakout board to the Pi's **PWR IN** socket:
  **J1 breakout → CBL1 cable → Pi PWR IN**. Insulate the solder joints.

## Audio

- **U2 · 1 × USB Audio Class DAC with a 3.5 mm stereo output.**
  The exact adapter model is not specified. It must be recognized by the Pi's
  playback image. The current power-control service expects ALSA card `1`
  with a `PCM` mute control.
- **1 × micro-USB OTG adapter or cable.** Connects the DAC to the Pi's **USB**
  data port. Choose its other connector to match the DAC.
- **J2 · 1 × 3.5 mm TRS plug or breakout lead.** Tip = left, ring = right,
  sleeve = ground.
- **U3 · 1 × Adafruit PAM8302A mono amplifier module.**
  [Adafruit #2130](https://www.adafruit.com/product/2130).
  Rated up to 2.5 W into 4 Ω at 5 V; this is separate from the speaker rating.
- **LS1 · 1 × 40 mm, 4 Ω, 5 W speaker.**
  [Adafruit #3968](https://www.adafruit.com/product/3968).
  Adafruit identifies the current revision as 5 W. The supplied enclosure has
  a larger 77.5 mm pocket, so this speaker needs an adapter or a revised mount.
- **RV1 · 1 × P102 / 1 kΩ trimmer potentiometer.**
  [Supplied Amazon link](https://www.amazon.co.uk/HELLOYEE-Breadboard-Trim-Potentiometer-Arduino/dp/B0777J1618).
  Use the 1 kΩ part from the assortment. Check the wiper with a multimeter and
  verify the body fits the printed knob and pocket.
- **R1, R2 · 2 × 470 Ω resistors, ¼ W.** One for each stereo channel before
  they join at the mono node.

## Controls and enclosure

- **SW1 · 1 × screen/audio on-off switch.**
  [Supplied Amazon link](https://www.amazon.co.uk/gp/product/B00R1LI06W).
  The service reads a maintained contact: closed to GND means on, open means
  off. Select a latching variant. For a six-pin switch, identify one pole's
  common and switched terminals by continuity; the other pole is unused.
- **1 × printed enclosure set.** Front, back, volume knob, button cap, and two
  decorative antennas. [STL and OpenSCAD files](enclosure/).
- **4 × case screws sized to the model.** The source has 2.5 mm pilot holes,
  3.2 mm clearance holes, and 6.5 mm counterbores. Check screw length and thread
  against the print before assembly.
- **As needed:** insulated hookup wire, heat-shrink tubing, solder, and mounting
  adhesive or suitable standoffs. Use adequately sized wire for the 5 V power
  path and keep audio leads short.

## Part verification

The Amazon links above are the builder's supplied references. The micro-USB
breakout listing was accessible and supplied its diagram photograph. The switch
and potentiometer listings could not be verified, so their mechanism, resistance,
and dimensions must be checked on the actual parts. The DAC model and final case
screw specification are also unspecified.

Component references: [PAM8302 pinout](https://learn.adafruit.com/adafruit-pam8302-mono-2-5w-class-d-audio-amplifier/pinouts),
[speaker specifications](https://www.adafruit.com/product/3968), and
[Waveshare display guide](https://www.waveshare.com/wiki/2.8inch_DPI_LCD).
