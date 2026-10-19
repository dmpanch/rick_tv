# Hardware photo references

[pi-zero-w-back.jpg](pi-zero-w-back.jpg) is the Raspberry Pi Zero W underside
product photograph from [Pi Australia / Little Bird](https://piaustralia.com.au/products/raspberry-pi-zero-w).
It was retrieved on 19 September 2026 from the store's
[image CDN](https://piaustralia.com.au/cdn/shop/products/LB-00152_Raspberry_Pi_Zero_W_5_213585b2-8b5a-494f-b85c-f2c31634c2e2.jpg?v=1573165058&width=1500).
The photo is third-party material; its rights remain with its respective owner.

The wiring SVG embeds the photograph, clips its white margins, and rotates it
90 degrees counterclockwise. It does not mirror the image. GPIO annotations
are aligned to the photographed solder pads, with the square pad identifying
physical pin 1. Pin names follow the
[official Pi Zero W schematic](https://pip-assets.raspberrypi.com/categories/592-raspberry-pi-zero-w/documents/RP-008368-DS-1-raspberry-pi-zero-w-reduced-schematics.pdf).

The following real product photographs are also embedded in the diagram:

- [pam8302a.jpg](pam8302a.jpg): the top view of
  [Adafruit PAM8302A #2130](https://www.adafruit.com/product/2130), from
  [Adafruit's image CDN](https://cdn-shop.adafruit.com/970x728/2130-08.jpg).
  The drawing marks the photographed solder pads. This is the blue PCB revision.
- [micro-usb-breakout.jpg](micro-usb-breakout.jpg): the board from the builder's
  [Amazon listing, B07R9SMJKF](https://www.amazon.co.uk/dp/B07R9SMJKF), from its
  [product image](https://m.media-amazon.com/images/I/61bJ5oj8VZL._AC_SL1002_.jpg).
  The board is rotated 90 degrees counterclockwise in the drawing.
- [p102-potentiometer.webp](p102-potentiometer.webp): the
  [FlyRobo 3386P-1 102, 1 kΩ potentiometer with knob](https://www.flyrobo.in/102-1k-dip-adjustable-potentiometer-with-knob),
  from its [front photograph](https://www.flyrobo.in/image/cache/wp/ge/102-1k-dip-adjustable-potentiometer-with-knob/102-1k-dip-adjustable-potentiometer-with-knob-3-550x550.webp).
  [p102-potentiometer.png](p102-potentiometer.png) is a pixel-preserving format
  conversion for SVG renderers that do not support embedded WebP.
- [dpdt-switch.jpg](dpdt-switch.jpg): a six-pin 7×7 mm latching switch from
  [ePartners](https://epartners.co.nz/products/mp8005), from its
  [product photograph](https://epartners.co.nz/cdn/shop/files/tactile-push-button-dpdt-mini-push-button-self-locking-switch-7x7x12mm-6-pin-551052.jpg?v=1726591938).
  The SVG crops to the one switch with all six leads visible and rotates it
  180 degrees. The photo's promotional text and second switch are outside the crop.

These photographs were retrieved on 19 September 2026. The switch and
potentiometer photos show the specified component types; their identity with
the parts in the builder's Amazon listings has not been verified. Photographs
remain third-party material. Cropping and rotation are SVG transforms, with no
generated replacement details or mirroring.

[render_wiring.py](../render_wiring.py) rebuilds the SVG from these local assets.
The DAC, speaker, power adapter, connectors, and resistors use vector drawings.
