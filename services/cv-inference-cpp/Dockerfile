# syntax=docker/dockerfile:1
FROM debian:bookworm-slim AS build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake git pkg-config \
    libopencv-dev libgrpc++-dev libprotobuf-dev protobuf-compiler-grpc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
# Root build context so the service can reach the shared proto/ contract.
COPY proto ./proto
COPY services/cv-inference-cpp ./services/cv-inference-cpp

WORKDIR /src/services/cv-inference-cpp
RUN cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j"$(nproc)"

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    libopencv-core406 libopencv-imgproc406 libopencv-imgcodecs406 libopencv-objdetect406 \
    libgrpc++1.51 libprotobuf32 opencv-data \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /src/services/cv-inference-cpp/build/cv_inference_server /usr/local/bin/cv_inference_server

EXPOSE 50051
CMD ["cv_inference_server"]
