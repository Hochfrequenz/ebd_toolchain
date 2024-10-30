FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY src .

CMD ["python", "ebd_toolchain/main.py", "-i", "/container/ebd.docx", "-o", "/container/output", "-t", "json", "-t", "dot", "-t", "svg", "-t", "puml"]
# to test this image run
# $ docker build -t local-test-image .
# $ docker compose up --build --abort-on-container-exit