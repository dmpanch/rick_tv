"""Build the wiring SVG from unmodified component photographs and vector wires.

Run with Python 3. Rasterize wiring.svg with an SVG renderer to update wiring.png.
Photo coordinates are measured on the source images; rotations never mirror them.
"""

from pathlib import Path
from html import escape
import base64

ROOT = Path(__file__).resolve().parent
OUT = []
INK, RED, GND, AUDIO, SWITCH = '#25313b', '#c63636', '#424b55', '#148377', '#8762b0'


def add(value):
    OUT.append(value)


def text(x, y, value, size=28, color=INK, weight=400, anchor='start'):
    add(f'<text x="{x}" y="{y}" font-family="Arial, Helvetica, sans-serif" '
        f'font-size="{size}" font-weight="{weight}" fill="{color}" '
        f'text-anchor="{anchor}">{escape(value)}</text>')


def rect(x, y, w, h, fill='#fff', stroke='none', r=0, sw=2):
    add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')


def circle(x, y, r=7, fill='#fff', stroke=INK, sw=3, ident=''):
    ident = f' id="{ident}"' if ident else ''
    add(f'<circle{ident} cx="{x}" cy="{y}" r="{r}" fill="{fill}" '
        f'stroke="{stroke}" stroke-width="{sw}"/>')


def wire(points, color=GND, width=5, ident=''):
    ident = f' id="{ident}"' if ident else ''
    add(f'<polyline{ident} points="' + ' '.join(f'{x},{y}' for x, y in points)
        + f'" fill="none" stroke="{color}" stroke-width="{width}" '
        'stroke-linecap="round" stroke-linejoin="round"/>')


def path(d, color=GND, width=5, ident=''):
    ident = f' id="{ident}"' if ident else ''
    add(f'<path{ident} d="{d}" fill="none" stroke="{color}" '
        f'stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round"/>')


def dot(x, y, color=GND):
    circle(x, y, 6, color, color, 1)


def nc(x, y):
    wire([(x-6, y-6), (x+6, y+6)], INK, 2)
    wire([(x-6, y+6), (x+6, y-6)], INK, 2)


def photo(name, filename, source_size, crop, x, y, scale, turn=0, radius=0):
    """Embed the original photo with a vector crop; return its coordinate mapping."""
    left, top, right, bottom = crop
    w, h = right-left, bottom-top
    rotations = {
        0: (f'translate({-left} {-top})', lambda a, b: (a-left, b-top)),
        90: (f'matrix(0 1 -1 0 {bottom} {-left})', lambda a, b: (bottom-b, a-left)),
        180: (f'matrix(-1 0 0 -1 {right} {bottom})', lambda a, b: (right-a, bottom-b)),
        270: (f'matrix(0 -1 1 0 {-top} {right})', lambda a, b: (b-top, right-a)),
    }
    transform, mapping = rotations[turn]
    dw, dh = (h, w) if turn in (90, 270) else (w, h)
    mime = 'image/png' if filename.endswith('.png') else 'image/jpeg'
    data = base64.b64encode((ROOT/'assets'/filename).read_bytes()).decode()
    add(f'<defs><clipPath id="{name}-clip"><rect x="{x}" y="{y}" '
        f'width="{dw*scale}" height="{dh*scale}" rx="{radius}"/></clipPath></defs>')
    add(f'<g clip-path="url(#{name}-clip)"><image id="{name}-photo" '
        f'width="{source_size[0]}" height="{source_size[1]}" '
        f'transform="translate({x} {y}) scale({scale}) {transform}" '
        f'href="data:{mime};base64,{data}"/></g>')

    def mapped(a, b):
        u, v = mapping(a, b)
        return round(x+u*scale, 2), round(y+v*scale, 2)

    return mapped


add('<svg xmlns="http://www.w3.org/2000/svg" width="3750" height="2310" '
    'viewBox="0 0 3750 2310" role="img" aria-labelledby="title desc">')
add('<title id="title">Rick TV wiring</title><desc id="desc">'
    'Photographs of Raspberry Pi Zero W, a six-contact switch, micro-USB breakout, '
    'P102 potentiometer and PAM8302A. All forty GPIO pads are labeled. '
    'Two separate 470 ohm resistors sum the DAC stereo outputs before the volume '
    'potentiometer. No external capacitors. One continuous connected drawing.'
    '</desc>')
rect(0, 0, 3750, 2310)

# Pi and the display fitted to its opposite side.
rect(340, 265, 635, 1238.5, '#edf4f7', '#9cb4c2', 18)
pi = photo('pi', 'pi-zero-w-back.jpg', (1500, 1500), (40, 410, 1450, 1110),
           360, 285, .85, 270)
text(657, 205, 'U1  Raspberry Pi Zero W', 34, weight=700, anchor='middle')
text(657, 245, 'DS1  Waveshare 2.8-inch DPI LCD', 26, '#52778b', anchor='middle')
odd = ['3V3', 'GPIO2 / SDA1', 'GPIO3 / SCL1', 'GPIO4', 'GND', 'GPIO17',
       'GPIO27', 'GPIO22', '3V3', 'GPIO10 / MOSI', 'GPIO9 / MISO',
       'GPIO11 / SCLK', 'GND', 'GPIO0 / ID_SD', 'GPIO5', 'GPIO6', 'GPIO13',
       'GPIO19', 'GPIO26', 'GND']
even = ['5V', '5V', 'GND', 'GPIO14 / TXD', 'GPIO15 / RXD', 'GPIO18', 'GND',
        'GPIO23', 'GPIO24', 'GND', 'GPIO25', 'GPIO8 / CE0', 'GPIO7 / CE1',
        'GPIO1 / ID_SC', 'GND', 'GPIO12', 'GND', 'GPIO16', 'GPIO20', 'GPIO21']
pins = {}
for row, (a, b) in enumerate(zip(odd, even)):
    source_x = 1262-row*(1262-243)/19
    for n, source_y, label in [(2*row+1, 533, a), (2*row+2, 480, b)]:
        x, y = pi(source_x, source_y)
        pins[n] = (x, y)
        color = RED if label == '5V' else GND if label == 'GND' else SWITCH if n == 37 else '#316c48'
        circle(x, y, 12, '#fff', color, 2.5, f'pi-pin-{n}')
        text(x, y+5, str(n), 14, color, 700, 'middle')
        if n % 2:
            rect(x+23, y-17, 181, 29, '#fff', r=3)
            text(x+29, y+5, label, 18, color)
        else:
            yy = y-14 if n in (2, 6) else y+5
            rect(x-220, yy-22, 197, 29, '#fff', r=3)
            text(x-27, yy, label, 18, color, anchor='end')

# Photographs are deliberately separated so their terminals have routing space.
pot = photo('pot', 'p102-potentiometer.png', (550, 550), (40, 0, 505, 550),
            1880, 780, .85)
text(2075, 676, 'RV1  Volume potentiometer', 32, weight=700, anchor='middle')
text(2075, 721, 'P102 / 1 kΩ', 28, anchor='middle')
pp = {1: pot(227, 530), 2: pot(269, 467), 3: pot(388, 516)}

pam = photo('pam', 'pam8302a.jpg', (970, 728), (158, 154, 817, 570),
            2630, 805, .86, radius=48)
text(2910, 742, 'U3  PAM8302A', 34, weight=700, anchor='middle')
ap = {name: pam(x, y) for name, x, y in [
    ('A+', 240, 222), ('A−', 240, 291), ('SD', 240, 361),
    ('VIN', 240, 430), ('GND', 240, 500), ('SP+', 718, 318), ('SP−', 718, 415)]}

sw = photo('switch', 'dpdt-switch.jpg', (1000, 1000), (0, 520, 590, 985),
           350, 1700, .85, 180)
text(600, 1625, 'SW1  Screen / sound switch', 32, weight=700, anchor='middle')
# A/C/B identify throws/common, without assuming the builder's contact-state order.
sp = {name: sw(x, y) for name, x, y in [
    ('A1', 560, 674), ('C1', 514, 712), ('B1', 459, 765),
    ('B2', 576, 832), ('C2', 526, 877), ('A2', 478, 931)]}

usb = photo('usb-breakout', 'micro-usb-breakout.jpg', (942, 802), (0, 0, 942, 802),
            1720, 1680, .55, 270)
text(1940, 1590, 'J1  micro-USB breakout', 32, weight=700, anchor='middle')
up = {name: usb(x, y) for name, x, y in [
    ('VBUS', 833, 382), ('D−', 758, 455), ('D+', 686, 535),
    ('ID', 613, 607), ('GND', 543, 685)]}

# DAC and the three separate 3.5 mm conductors.
rect(1160, 900, 230, 320, '#35424d', '#18252e', 24, 3)
text(1275, 956, 'U2  USB DAC', 27, '#fff', 700, 'middle')
circle(1385, 1084, 35, '#16232c', '#9aa8b1', 4)
rect(1380, 1020, 75, 130, '#28343e', '#14212a', 12)
text(1430, 872, 'J2  3.5 mm TRS', 26, weight=600, anchor='middle')
for yy, label, start in [(990, 'L', 1044), (1090, 'R', 1085), (1190, 'GND', 1127)]:
    wire([(1455, start), (1490, yy), (1520, yy)], GND if label == 'GND' else AUDIO, 4)
    text(1490, yy-20, label, 21, GND if label == 'GND' else AUDIO, anchor='middle')

def resistor(y, name):
    wire([(1520, y), (1600, y)], AUDIO)
    rect(1600, y-20, 145, 40, '#ecd7aa', '#b49d70', 16)
    for dx, color in [(22, '#e5be24'), (48, '#83539c'), (74, '#82582d'), (116, '#b9a052')]:
        rect(1600+dx, y-18, 9, 36, color)
    wire([(1745, y), (1810, y)], AUDIO)
    text(1672, y-46, f'{name}  470 Ω', 26, anchor='middle')

resistor(990, 'R1')
resistor(1090, 'R2')
wire([(1810, 1090), (1810, 740), (2370, 740), (2370, pp[3][1]), pp[3]], AUDIO, 5, 'mono-to-pot-end')
dot(1810, 990, AUDIO)
wire([pp[2], (pp[2][0], 1380), (2470, 1380), (2470, ap['A+'][1]), ap['A+']], AUDIO, 5, 'pot-wiper-to-pam-a-plus')

# Ground at the left track end and input at the right allow all three leads
# to reach their destinations without crossing. The center lead is the wiper.
wire([pp[1], (pp[1][0], 1500)], GND, 5, 'pot-end-to-ground')
wire([(1520, 1190), (1510, 1190), (1510, 1500)], GND, 5, 'dac-sleeve-to-ground')
wire([ap['A−'], (2530, ap['A−'][1]), (2530, 1500)], GND, 5, 'pam-a-minus-to-ground')
wire([ap['GND'], (ap['GND'][0], 1500)], GND, 5, 'pam-gnd')

# Pi supply to the actual PAM input pads. VIN enters from the component side of its pad.
x, y = pins[2]
vin_x, vin_y = ap['VIN']
wire([(x-12, y), (175, y), (175, 130), (vin_x+40, 130),
      (vin_x+40, vin_y), (vin_x, vin_y)], RED, 5, 'pi-2-to-pam-vin')
x, y = pins[6]
wire([(x-12, y), (65, y), (65, 65), (3670, 65), (3670, 1500),
      (1510, 1500)], GND, 5, 'pi-6-common-ground')
for x in [pp[1][0], 2530, ap['GND'][0]]:
    dot(x, 1500)

# Solder-pad overlays and pin names use the photograph, not an invented module layout.
for label, (x, y) in ap.items():
    color = RED if label == 'VIN' else AUDIO if label in ('A+', 'SP+', 'SP−') else GND
    circle(x, y, 8, '#fff', color)
    if label.startswith('SP'):
        text(3205, y-18, label, 24, weight=600)
    else:
        text(2610, y-17, label, 24, weight=600, anchor='end')
x, y = ap['SD']
wire([(x, y), (x-34, y)], GND, 2)
nc(x-34, y)
for n, (x, y) in pp.items():
    circle(x, y, 7, '#fff', GND if n == 1 else AUDIO)
    text(x+16, y-15, str(n), 23, weight=600)

# Speaker is separated from the amplifier by a clear wire run.
cx, cy = 3440, 1040
for r, fill, stroke, swidth in [(150, '#343c43', '#16222b', 4), (126, '#17232b', '#68737b', 7),
                               (85, '#38444d', '#14222b', 3), (39, '#1c2c37', '#14222b', 2)]:
    circle(cx, cy, r, fill, stroke, swidth)
text(cx, 780, 'LS1  Speaker', 32, weight=700, anchor='middle')
text(cx, 824, '4 Ω / 5 W', 28, anchor='middle')
for label, yy in [('SP+', 980), ('SP−', 1100)]:
    rect(3275, yy-10, 46, 20, '#c3ad72', '#887044', 2)
    start = ap[label]
    elbow = 3210 if label == 'SP+' else 3240
    wire([start, (elbow, start[1]), (elbow, yy), (3275, yy)], AUDIO)
    text(3330, yy+8, '+' if label == 'SP+' else '−', 28, '#fff', 700)

# Both switch wires approach from the left, with no crossing or terminal overlap.
x, y = pins[37]
wire([(x, y+12), (x, y+24), (90, y+24), (90, sp['C2'][1]), sp['C2']], SWITCH, 5, 'pi-37-switch')
x, y = pins[39]
wire([(x, y+12), (x, y+25), (150, y+25), (150, sp['A2'][1]), sp['A2']], GND, 5, 'pi-39-switch')
for name, (x, y) in sp.items():
    color = SWITCH if name == 'C2' else GND
    circle(x, y, 6, '#fff', color, 2)
    rect(x-60, y-40, 52, 28, '#fff', r=3)
    text(x-16, y-16, name, 21, color, 600, 'end')

# Actual Pi USB connectors. The external power board feeds PWR IN through CBL1.
for y, label in [(1023, 'USB'), (1234, 'PWR IN')]:
    rect(927, y, 62, 57, '#bbc4ca', '#63717b', 5)
    text(958, y-20, label, 24, '#4d626f', 600, 'middle')
wire([(989, 1052), (1080, 1052), (1080, 1135), (1160, 1135)], '#3b4852', 16, 'usb-otg-cable')
text(1080, 1007, 'USB OTG', 26, '#4d626f', 600, 'middle')
vbx, vby = up['VBUS']
gbx, gby = up['GND']
wire([(989, 1253), (1260, 1253), (1260, 1650), (vbx, 1650), (vbx, vby)], RED, 5, 'cbl1-vbus')
wire([(989, 1275), (1180, 1275), (1180, 2180), (2260, 2180),
      (2260, gby), (gbx, gby)], GND, 5, 'cbl1-gnd')
text(1250, 2245, 'CBL1  micro-USB power cable', 28, '#4d626f', 600)
for name, (x, y) in up.items():
    color = RED if name == 'VBUS' else GND
    circle(x, y, 7, '#fff', color, 2.5)
    if name not in ('VBUS', 'GND'):
        # Bare unused pads remain visible; do not add wires to power-only data pins.
        text(x+23, y-10, name, 19, color, 600)
    else:
        text(x+24, y-16, name, 23, color, 600)

# The mains adapter's USB cable plugs into J1's photographed receptacle.
socket = usb(115, 196)
wire([socket, (socket[0], 2135), (1470, 2135), (1470, 2040)], '#3b4852', 16, 'usb-supply-cable')
rect(1280, 1860, 380, 180, '#f0f3f5', '#8295a2', 18, 3)
text(1470, 1925, 'PS1', 30, weight=700, anchor='middle')
text(1470, 1980, '5 V USB supply', 30, weight=600, anchor='middle')

add('</svg>')
(ROOT/'wiring.svg').write_text('\n'.join(OUT))
print('Wrote', ROOT/'wiring.svg')
print('Pot:', pp, '\nPAM:', ap, '\nSwitch:', sp, '\nUSB breakout:', up)
