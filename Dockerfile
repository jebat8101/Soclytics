FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.12 python3.12-dev python3-pip python3.12-venv \
    build-essential cmake g++ make pkg-config \
    libopenblas-dev liblapack-dev libx11-dev libgtk-3-dev \
    libpng-dev libjpeg-dev xvfb x11-utils ca-certificates fonts-liberation \
    libasound2t64 libatk-bridge2.0-0 libatk1.0-0 libcups2 libdbus-1-3 \
    libdrm2 libgbm1 libgtk-3-0 libnspr4 libnss3 libx11-6 libxcomposite1 \
    libxdamage1 libxext6 libxfixes3 libxrandr2 \
    wget curl git sqlite3 python3-tk \
    && rm -rf /var/lib/apt/lists/*

RUN wget -q -O /tmp/chrome.deb \
    https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get update \
    && apt-get install -y /tmp/chrome.deb \
    && rm /tmp/chrome.deb \
    && rm -rf /var/lib/apt/lists/*

RUN python3.12 -m venv /app/venv
ENV PATH="/app/venv/bin:$PATH"

RUN pip install --upgrade pip \
    && pip install flask seleniumbase Pillow numpy pytest reportlab matplotlib \
    && pip install telethon beautifulsoup4 requests \
    && pip install dlib \
    && pip install face_recognition \
    && pip install git+https://github.com/ageitgey/face_recognition_models

RUN python3 - << 'PYEOF'
import os, sys
path = os.path.join(sys.prefix, 'lib', f'python{sys.version_info.major}.{sys.version_info.minor}', 'site-packages')
init = os.path.join(path, 'face_recognition_models', '__init__.py')
if os.path.exists(init) and 'pkg_resources' in open(init).read():
    open(init, 'w').write('''import os as _os
_here = _os.path.dirname(_os.path.abspath(__file__))
def pose_predictor_model_location():
    return _os.path.join(_here, "models/shape_predictor_68_face_landmarks.dat")
def pose_predictor_five_point_model_location():
    return _os.path.join(_here, "models/shape_predictor_5_face_landmarks.dat")
def face_recognition_model_location():
    return _os.path.join(_here, "models/dlib_face_recognition_resnet_model_v1.dat")
def cnn_face_detector_model_location():
    return _os.path.join(_here, "models/mmod_human_face_detector.dat")
''')
PYEOF

WORKDIR /app
RUN mkdir -p /app/face_data /app/face_data_ig /app/face_data_threads /app/face_data_tg \
    /app/post_screenshots /app/telegram_media /app/reports /app/icons
COPY app/ /app/
ENV PYTHONPATH=/app PYTHONUNBUFFERED=1 DISPLAY=:99 PORT=5000
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh
EXPOSE 5000
ENTRYPOINT ["/docker-entrypoint.sh"]
