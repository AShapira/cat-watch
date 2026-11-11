# Third-party components

The [MIT license](LICENSE) covers cat-watch's original source code and
documentation. It does not relicense dependencies, model weights, operating-system
packages, or a combined application containing those components.

## Ultralytics and YOLO11n

The application imports `ultralytics==8.3.222`, and the container build downloads
the YOLO11n pretrained weights. Ultralytics supplies its software and models under
AGPL-3.0 by default, with separate enterprise licensing available. The combined
application using those components is subject to their AGPL requirements; it is
not an MIT-only distribution. The MIT grant for cat-watch's original code remains
available, including for reuse with a different detector.

- [Ultralytics 8.3.222 license](https://github.com/ultralytics/ultralytics/blob/v8.3.222/LICENSE)
- [Ultralytics licensing guidance](https://www.ultralytics.com/license)
- [YOLO11 model documentation](https://docs.ultralytics.com/models/yolo11/)

Ultralytics source and model weights are not vendored in this repository. The
Containerfile records the upstream model location through its loader and verifies
the downloaded weights against a fixed SHA-256 digest.

## Other dependencies

Python packages, CUDA runtime libraries, FFmpeg, and Debian packages retain their
respective upstream licenses and notices. The container's `/opt/python-lock.txt`
records installed Python versions, and `/opt/models/SHA256SUMS` records its model
checksum. Consult installed package metadata and upstream licenses before
redistributing a built container. This source publication does not publish a
prebuilt container image or model-weight archive.

## VideoMAE behavior backbone

The learning image includes `MCG-NJU/videomae-base-finetuned-kinetics`, revision
`488eb9a0565f257b32866000305c8178965eb9f6`, under **CC BY-NC 4.0**. Its noncommercial
restriction applies to the pretrained weights and derived use; the project's MIT
license does not replace it. Attribution: VideoMAE authors / MCG-NJU. See the
[checkpoint card](https://huggingface.co/MCG-NJU/videomae-base-finetuned-kinetics/tree/488eb9a0565f257b32866000305c8178965eb9f6)
and [license](https://creativecommons.org/licenses/by-nc/4.0/).
`scripts/install-learning-model.py` verifies the weights and writes provenance
and file hashes into the image. Transformers and Safetensors retain their
respective upstream licenses. The learning requirements are pinned separately.
