FROM python:3.13-slim

WORKDIR /app
COPY . /app

# 依赖（项目 venv 安装在 managed 目录，这里走系统 python 即可）
RUN pip install --no-cache-dir \
    Flask Flask-SQLAlchemy Flask-Login Flask-WTF Flask-Migrate \
    SQLAlchemy alembic cryptography python-dotenv requests \
    python-pptx python-docx pdfplumber openpyxl reportlab email-validator \
    gunicorn

EXPOSE 5000
# 生产用 gunicorn 多 worker（gthread 支持 AI 同步阻塞调用并发）；debug 已在代码关闭
CMD ["gunicorn", "-w", "4", "-k", "gthread", "--threads", "4", "-b", "0.0.0.0:5000", "run:app"]
