FROM python:3.14-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY src .
# PYTHONPATH must include /app so that `from ebd_toolchain.x import ...` resolves.
# Without it, `python ebd_toolchain/main.py` only adds /app/ebd_toolchain/ to sys.path.
ENV PYTHONPATH=/app

CMD ["python", "ebd_toolchain/main.py", "-i", "/container/ebd.docx", "-o", "/container/output", "-t", "json", "-t", "dot", "-t", "svg", "-t", "puml"]
# to test this image run
# $ docker build -t local-test-image .
# $ docker compose up --build --abort-on-container-exit