FROM python:3.13-slim

# pip 源可切换：国内服务器用清华源（默认），海外机器构建时传 --build-arg PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn

WORKDIR /app

# 先只拷依赖清单 —— 代码改动时这层缓存不失效，重新部署快很多
COPY requirements.txt /app/requirements.txt

# 依赖统一由 requirements.txt 管理（此前手写清单漏了 PyYAML，会导致
# app.py -> seeds.py -> import yaml 启动即崩，切勿再改回手写列表）
RUN pip install --no-cache-dir \
        -i ${PIP_INDEX_URL} --trusted-host ${PIP_TRUSTED_HOST} \
        -r requirements.txt gunicorn

# 再拷业务代码（.dockerignore 已排除 .venv/.git/instance/.env）
COPY . /app

# SQLite 与上传目录由 volume 挂载，先建好避免首次启动权限问题
RUN mkdir -p /app/instance /app/uploads

EXPOSE 5000

# 生产用 gunicorn：4 worker × 4 线程。
# AI 调用是同步阻塞的，必须用 gthread（而非默认 sync）否则一个人生成课评会卡住整个 worker。
# --timeout 180 是因为大模型生成可能超过默认 30s 而被 gunicorn 杀掉。
CMD ["gunicorn", "-w", "4", "-k", "gthread", "--threads", "4", \
     "--timeout", "180", "--access-logfile", "-", "--error-logfile", "-", \
     "-b", "0.0.0.0:5000", "run:app"]
