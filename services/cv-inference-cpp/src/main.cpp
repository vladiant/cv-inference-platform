// Stateless gRPC inference service. This is the CPU-bound hot path of the
// system (see docs/design-decisions.md for why it's C++ rather than Python).
//
// The inference itself is deliberately simple (OpenCV Haar cascade face
// detection) -- the point of this service is the service boundary and the
// throughput characteristics, not the model.

#include <chrono>
#include <iostream>
#include <memory>
#include <string>

#include <grpcpp/grpcpp.h>
#include <grpcpp/health_check_service_interface.h>
#include <opencv2/opencv.hpp>
#include <opencv2/objdetect.hpp>

#include "inference.grpc.pb.h"

using grpc::Server;
using grpc::ServerBuilder;
using grpc::ServerContext;
using grpc::Status;
using cvinference::Inference;
using cvinference::InferRequest;
using cvinference::InferResponse;
using cvinference::Detection;

namespace {

// Loaded once at startup and shared (read-only) across requests --
// CascadeClassifier::detectMultiScale is safe to call concurrently on a
// const classifier from multiple threads.
class InferenceServiceImpl final : public Inference::Service {
public:
    explicit InferenceServiceImpl(const std::string& cascade_path) {
        if (!cascade_.load(cascade_path)) {
            throw std::runtime_error("failed to load cascade: " + cascade_path);
        }
    }

    Status InferImage(ServerContext* /*context*/, const InferRequest* request,
                       InferResponse* response) override {
        const auto start = std::chrono::steady_clock::now();
        response->set_image_id(request->image_id());

        try {
            std::vector<uchar> buf(request->image_data().begin(), request->image_data().end());
            cv::Mat img = cv::imdecode(buf, cv::IMREAD_GRAYSCALE);
            if (img.empty()) {
                response->set_success(false);
                response->set_error_message("could not decode image");
                return Status::OK;
            }

            std::vector<cv::Rect> faces;
            cascade_.detectMultiScale(img, faces, 1.1, 4, 0, cv::Size(30, 30));

            for (const auto& face : faces) {
                Detection* d = response->add_detections();
                d->set_label("face");
                d->set_confidence(1.0f);  // Haar cascades don't give a real score
                d->set_x(face.x);
                d->set_y(face.y);
                d->set_width(face.width);
                d->set_height(face.height);
            }

            response->set_success(true);
        } catch (const std::exception& ex) {
            response->set_success(false);
            response->set_error_message(ex.what());
        }

        const auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now() - start);
        response->set_processing_ms(static_cast<int32_t>(elapsed.count()));
        return Status::OK;
    }

private:
    cv::CascadeClassifier cascade_;
};

}  // namespace

int main(int argc, char** argv) {
    std::string cascade_path = "/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml";
    if (argc > 1) {
        cascade_path = argv[1];
    }

    const std::string server_address = "0.0.0.0:50051";
    InferenceServiceImpl service(cascade_path);

    // Serve the standard gRPC health-checking protocol (grpc.health.v1.Health)
    // so Kubernetes' native grpc readiness probe can confirm the service is
    // registered and SERVING. Must be enabled before BuildAndStart().
    grpc::EnableDefaultHealthCheckService(true);

    ServerBuilder builder;
    builder.AddListeningPort(server_address, grpc::InsecureServerCredentials());
    builder.RegisterService(&service);

    std::unique_ptr<Server> server(builder.BuildAndStart());
    std::cout << "cv-inference-cpp listening on " << server_address << std::endl;
    server->Wait();

    return 0;
}
