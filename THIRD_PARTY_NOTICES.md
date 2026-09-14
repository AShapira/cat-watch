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

## Label Studio

Optional local annotation service: HumanSignal Label Studio Community Edition 1.23.0, Apache License 2.0. The official image is digest-pinned in scripts/label-studio.lock.json. Upstream: https://github.com/HumanSignal/label-studio. It runs separately; project code uses its documented API and standard labeling controls.
