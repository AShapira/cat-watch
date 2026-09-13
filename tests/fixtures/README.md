`synthetic-review.mp4` is a generated 12-second, 352x198, 15 fps solid-green H.264
clip for browser seek and overlay acceptance. It contains no camera footage.

Regenerate with FFmpeg:

```sh
ffmpeg -f lavfi -i color=c=darkgreen:s=352x198:r=15 -t 12 -c:v libx264 -pix_fmt yuv420p tests/fixtures/synthetic-review.mp4
```
