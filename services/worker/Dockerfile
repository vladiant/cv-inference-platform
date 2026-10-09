FROM python:3.12-slim

WORKDIR /srv

COPY services/worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Generate gRPC stubs from the shared proto contract at build time,
# so the .proto file stays the single source of truth.
COPY proto/inference.proto ./proto/inference.proto
RUN python -m grpc_tools.protoc -I proto --python_out=. --grpc_python_out=. proto/inference.proto

COPY services/worker/app ./app

CMD ["python", "-u", "-m", "app.main"]
