FROM python:3.13-slim

# 国内服务器默认走清华源
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir \
    -i ${PIP_INDEX_URL} --trusted-host ${PIP_TRUSTED_HOST} \
    -r requirements.txt gunicorn

COPY . /app
RUN mkdir -p /app/out

EXPOSE 5001
CMD ["gunicorn", "-w", "2", "-k", "gthread", "-b", "0.0.0.0:5001", "--timeout", "120", "app:app"]
