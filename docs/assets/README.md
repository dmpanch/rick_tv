# Documentation media

`rick-tv-demo.gif` is a 10-second, silent loop from the builder-supplied
`IMG_5643.MOV`. It uses 480×480 pixels, 10 frames per second, and a 128-color
palette. The crop focuses on the television and its controls. The original
recording is not stored in the repository.

Recreate it with FFmpeg from the repository root:

```sh
ffmpeg -i /path/to/IMG_5643.MOV -t 10 \
  -filter_complex '[0:v:0]fps=10,crop=1080:1080:0:300,scale=480:480:flags=lanczos,split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle[out]' \
  -map '[out]' -an -map_metadata -1 -loop 0 -y docs/assets/rick-tv-demo.gif
```

FFmpeg applies the source's rotation metadata before cropping. Only the filtered
video stream is selected; audio and source metadata are omitted. The committed
GIF was generated with FFmpeg 6.0.
