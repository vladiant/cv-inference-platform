cmake_minimum_required(VERSION 3.16)
project(cv_inference_cpp CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(OpenCV REQUIRED)
find_package(Protobuf REQUIRED)
find_package(gRPC REQUIRED)

set(PROTO_DIR ${CMAKE_SOURCE_DIR}/../../proto)
set(GENERATED_DIR ${CMAKE_BINARY_DIR}/generated)
file(MAKE_DIRECTORY ${GENERATED_DIR})

protobuf_generate_cpp(PROTO_SRCS PROTO_HDRS ${PROTO_DIR}/inference.proto)

get_target_property(GRPC_CPP_PLUGIN gRPC::grpc_cpp_plugin LOCATION)
add_custom_command(
    OUTPUT ${GENERATED_DIR}/inference.grpc.pb.cc ${GENERATED_DIR}/inference.grpc.pb.h
    COMMAND protobuf::protoc
    ARGS --grpc_out=${GENERATED_DIR}
         --plugin=protoc-gen-grpc=${GRPC_CPP_PLUGIN}
         -I ${PROTO_DIR}
         ${PROTO_DIR}/inference.proto
    DEPENDS ${PROTO_DIR}/inference.proto
)

add_executable(cv_inference_server
    src/main.cpp
    ${PROTO_SRCS}
    ${GENERATED_DIR}/inference.grpc.pb.cc
)

target_include_directories(cv_inference_server PRIVATE ${GENERATED_DIR} ${CMAKE_BINARY_DIR})
target_link_libraries(cv_inference_server
    ${OpenCV_LIBS}
    gRPC::grpc++
    protobuf::libprotobuf
)
