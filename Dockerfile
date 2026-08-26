FROM python:3.13-slim

# git is needed because requirements.txt installs discord.py-self straight
# from GitHub. curl/ca-certificates are needed to fetch Node.js's setup
# script. Node.js runs the Captchaly bridge (node_captcha_solver/) for
# hCaptcha auto-solving. Chromium + its shared libraries are needed for the
# top.gg auto-vote feature (DrissionPage). Render's native Python runtime has
# none of this, which is why this service needs to run as Docker instead.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    chromium \
    fonts-liberation \
    libnss3 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdrm2 \
    libgbm1 \
    libasound2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY node_captcha_solver/package.json node_captcha_solver/package.json
RUN cd node_captcha_solver && npm install --omit=dev

COPY . .

CMD ["sh", "-c", "cp /etc/secrets/owo.json data/owo.json 2>/dev/null; cp /etc/secrets/settings.json data/settings.json 2>/dev/null; python main.py"]
