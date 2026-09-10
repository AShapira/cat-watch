FROM docker.io/library/python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    YOLO_CONFIG_DIR=/tmp/ultralytics YOLO_AUTOINSTALL=false YOLO_OFFLINE=true \
    MPLCONFIGDIR=/tmp/matplotlib CATWATCH_DATA=/data OMP_NUM_THREADS=2
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/cat-watch
COPY requirements.txt ./
RUN pip install --no-cache-dir torch==2.7.1 torchvision==0.22.1 --index-url https://download.pytorch.org/whl/cu128 \
    && pip install --no-cache-dir -r requirements.txt
RUN mkdir /opt/models && cd /opt/models \
    && python -c "from ultralytics import YOLO; YOLO('yolo11n.pt')" \
    && echo '0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1  yolo11n.pt' | sha256sum -c - \
    && sha256sum yolo11n.pt > SHA256SUMS \
    && pip freeze > /opt/python-lock.txt
RUN cd /opt/models \
    && python -c "from ultralytics import YOLO; YOLO('yolo11m.pt')" \
    && echo 'd5ffc1a674953a08e11a8d21e022781b1b23a19b730afc309290bd9fb5305b95  yolo11m.pt' | sha256sum -c - \
    && sha256sum yolo11m.pt >> SHA256SUMS
COPY catwatch ./catwatch
USER 1000:1000
CMD ["python", "-m", "catwatch"]
