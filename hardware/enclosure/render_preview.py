#!/usr/bin/env python3
"""Render an assembled binary STL without an OpenGL context.

Usage: python3 render_preview.py tv-parametric-model.stl render.png --printing-layout
Dependencies: NumPy, Pillow. Coordinates match tv-parametric-model.scad.
"""
import argparse
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def read_stl(path):
    data = Path(path).read_bytes()
    count = int.from_bytes(data[80:84], 'little')
    if len(data) != 84 + 50 * count:
        raise ValueError('Expected a binary STL exported by OpenSCAD.')
    dtype = np.dtype([('normal', '<f4', 3), ('vertices', '<f4', (3, 3)), ('attr', '<u2')])
    records = np.frombuffer(data, dtype=dtype, offset=84, count=count)
    return records['vertices'].astype(np.float64)


def assemble_printing_layout(vertices):
    """Undo the six supplied print transforms, then apply SCAD assembly transforms."""
    unique, indices = np.unique(vertices.reshape(-1, 3), axis=0, return_inverse=True)
    parent = np.arange(len(unique))

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for a, b, c in indices.reshape(-1, 3):
        first = find(a)
        parent[find(b)] = first
        parent[find(c)] = first
    groups = np.array([find(i) for i in indices[::3]])
    labels = np.unique(groups)
    if len(labels) != 6:
        raise ValueError('The supplied printing layout must contain exactly six connected parts.')

    def rotation(axis, degrees):
        angle = np.deg2rad(degrees)
        c, s = np.cos(angle), np.sin(angle)
        if axis == 'x':
            return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
        if axis == 'y':
            return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
        return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])

    result = vertices.copy()
    colors = np.tile([190., 201., 202.], (len(vertices), 1))
    names = []
    for label in labels:
        mask = groups == label
        part = vertices[mask]
        low, high = part.min(axis=(0, 1)), part.max(axis=(0, 1))
        center = (low+high)/2
        if high[0]-low[0] > 100:
            front = center[0] < 0
            offset = [-80, 0, 0] if front else [80, 0, 0]
            result[mask] = (part-offset) @ rotation('x', 90 if front else -90).T
            colors[mask] = [30., 155., 153.]
            names.append('front' if front else 'back')
        elif center[1] < 85:
            volume = center[0] < 0
            offset = [-25, 75, 10] if volume else [25, 75, 8]
            local = (part-offset) @ rotation('x', 180).T
            matrix = rotation('z', 48) @ rotation('x', 105 if volume else 75)
            result[mask] = (local+[0, 0, 70 if volume else 64]) @ matrix.T
            names.append('volume' if volume else 'button')
        else:
            left = center[0] < 30
            local = (part-([-40, 90, 2] if left else [40, 90, 2])) @ rotation('y', -90).T
            matrix = rotation('z', 45 if left else -45) @ rotation('x', -20)
            result[mask] = (local+[0, 0, 60]) @ matrix.T
            names.append('antenna-left' if left else 'antenna-right')
    if len(set(names)) != 6:
        raise ValueError('Part bounds do not match the supplied OpenSCAD print layout.')
    print('Assembled: '+', '.join(names))
    return result, colors


def render(vertices, output, face_colors=None):
    width, height = 1800, 1400
    eye = np.array([240., -380., 190.])
    eye /= np.linalg.norm(eye)
    right = np.cross([0., 0., 1.], eye)
    right /= np.linalg.norm(right)
    up = np.cross(eye, right)
    camera = np.stack((right, -up, eye), axis=1)
    projected = vertices @ camera
    lo = projected[:, :, :2].min(axis=(0, 1))
    hi = projected[:, :, :2].max(axis=(0, 1))
    scale = min((width-360)/(hi[0]-lo[0]), (height-240)/(hi[1]-lo[1]))
    projected[:, :, :2] = (projected[:, :, :2]-(lo+hi)/2)*scale + [width/2, height/2-15]

    base = Image.new('RGB', (width, height), '#f1f5f4')
    shadow = Image.new('RGBA', base.size)
    draw = ImageDraw.Draw(shadow)
    floor_y = min(height-100, int(projected[:, :, 1].max())-10)
    draw.ellipse((width*.25, floor_y-70, width*.76, floor_y+90), fill=(24, 54, 50, 40))
    base = Image.alpha_composite(base.convert('RGBA'), shadow.filter(ImageFilter.GaussianBlur(32))).convert('RGB')
    canvas = np.asarray(base).copy()
    depth = np.full((height, width), -np.inf)

    normals = np.cross(vertices[:, 1]-vertices[:, 0], vertices[:, 2]-vertices[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    normals /= np.maximum(lengths[:, None], 1e-12)
    light = np.array([-0.6, -0.8, 1.3])
    light /= np.linalg.norm(light)
    fill_light = np.array([.7, .3, .5]); fill_light /= np.linalg.norm(fill_light)
    intensity = .38 + .53*np.maximum(0, normals @ light) + .12*np.maximum(0, normals @ fill_light)
    center = vertices.mean(axis=1)
    # OpenSCAD uses teal for the body and silver for the protruding accessories.
    colors = np.tile([30., 155., 153.], (len(vertices), 1))
    colors[np.linalg.norm(center, axis=1)>71.5] = [190., 201., 202.]
    if face_colors is not None:
        colors = face_colors
    colors = np.clip(colors*intensity[:, None], 0, 255).astype(np.uint8)

    for tri, normal, color in zip(projected, normals, colors):
        if normal @ eye <= 0:
            continue
        xmin, ymin = np.maximum(0, np.floor(tri[:, :2].min(axis=0)).astype(int))
        xmax, ymax = np.minimum([width-1, height-1], np.ceil(tri[:, :2].max(axis=0)).astype(int))
        if xmax < xmin or ymax < ymin:
            continue
        a, b, c = tri
        denominator = (b[1]-c[1])*(a[0]-c[0]) + (c[0]-b[0])*(a[1]-c[1])
        if abs(denominator) < 1e-9:
            continue
        yy, xx = np.mgrid[ymin:ymax+1, xmin:xmax+1]
        xx = xx + .5; yy = yy + .5
        w0 = ((b[1]-c[1])*(xx-c[0])+(c[0]-b[0])*(yy-c[1]))/denominator
        w1 = ((c[1]-a[1])*(xx-c[0])+(a[0]-c[0])*(yy-c[1]))/denominator
        w2 = 1-w0-w1
        z = w0*a[2]+w1*b[2]+w2*c[2]
        target_depth = depth[ymin:ymax+1, xmin:xmax+1]
        mask = (w0>=0) & (w1>=0) & (w2>=0) & (z>target_depth)
        target_depth[mask] = z[mask]
        canvas[ymin:ymax+1, xmin:xmax+1][mask] = color
    result = Image.fromarray(canvas).resize((1350, 1050), Image.Resampling.LANCZOS)
    result.save(output, optimize=True)
    print(f'Rendered {len(vertices):,} triangles to {output}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stl', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--printing-layout', action='store_true', help='Assemble the six parts in the supplied print-layout STL.')
    args = parser.parse_args()
    vertices = read_stl(args.stl)
    colors = None
    if args.printing_layout:
        vertices, colors = assemble_printing_layout(vertices)
    render(vertices, args.output, colors)
