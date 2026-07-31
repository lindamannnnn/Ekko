FROM python:3.13-slim

WORKDIR /app
COPY . /app

# 依赖（项目 venv 安装在 managed 目录，这里走系统 python 即可）
RUN pip install --no-cache-dir \
    Flask Flask-SQLAlchemy Flask-Login Flask-WTF Flask-Migrate \
    SQLAlchemy alembic cryptography python-dotenv requests \
    python-pptx python-docx pdfplumber openpyxl reportlab email-validator

EXPOSE 5000
CMD ["python", "run.py"]
