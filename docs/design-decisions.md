# Design Decisions

Written as if explaining trade-offs to a non-engineering stakeholder — the
"why", not just the "what".

## Why split ingestion from inference?

If the API that accepts uploads also runs inference synchronously, a slow
model or a burst of uploads makes the *upload* feel slow, even though
uploading and inferring are unrelated concerns from the customer's point of
view. Splitting them means: uploads always feel instant, and we can scale the
inference workers up or down independently of how many people are uploading
right now, without redeploying the upload service.

## Why gRPC between worker and cv-inference-cpp, but REST everywhere else?

REST/JSON is the right default for anything a human or a third party might
call directly — it's debuggable with `curl`, self-describing, and nobody
needs a code generator to use it. The worker-to-inference call is different:
it's a high-frequency, internal, binary-payload (image bytes) call where
serialization overhead is not free. gRPC's binary protobuf framing and HTTP/2
multiplexing measurably reduce overhead at that call rate. Using REST there
"for consistency" would be optimizing for a value (uniformity) at the expense
of the value that actually matters on that path (throughput).

## Why C++ for the inference service specifically?

Everything else in the system is I/O-bound: it's waiting on the network, the
database, or object storage, and Python's `asyncio` handles that well. The
inference step is CPU-bound — it's the one place where per-request Python
interpreter overhead actually shows up in the bill. Isolating it as its own
service means the CPU-bound hot path can be optimized (or the model swapped,
or GPU support added) without touching the rest of the system, and it can be
scaled and resourced separately in Kubernetes (different CPU/memory requests
than the I/O-bound services).

## Why an event stream instead of the worker polling the database?

Polling means either wasted queries when nothing's new, or added latency
between "image uploaded" and "worker notices it," depending on the poll
interval. A stream gives near-immediate delivery without a polling loop, and
consumer groups mean adding a second worker doesn't require any code change —
it just means the same events get load-balanced across more consumers.

## Why keep raw images and metadata in different stores with different retention?

Raw image bytes are large and mostly write-once/read-rarely after processing.
Metadata and results are small, queried constantly, and need to support
filtering ("show me all failed inferences from last week"). Forcing both into
one system means picking a storage engine that's mediocre at both jobs
instead of good at one. Splitting them lets each store use a retention policy
that matches how the data is actually used: images age out to cold storage
automatically; metadata stays queryable indefinitely, with old partitions
archived rather than deleted, since audit and analytics needs on structured
data tend to outlast the raw files they describe.

## What would change with real production scale?

- Redis Streams → Kafka, once cross-service replay/ordering guarantees or
  multi-datacenter delivery matter more than operational simplicity.
- A single Postgres instance → read replicas for `results-api`, since it's
  read-heavy and can tolerate slightly stale data.
- The C++ inference service would get a proper batching layer (accumulate N
  requests or T milliseconds, run one batched inference call) if a real model
  benefits from batch throughput — not implemented here since the scaffold
  uses a single-image OpenCV operation.
