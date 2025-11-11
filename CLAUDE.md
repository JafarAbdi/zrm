# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ZRM (Zenoh ROS-like Middleware) is a minimal, single-file communication middleware built on Zenoh, providing a clean and simple API inspired by ROS2 patterns. The entire implementation lives in `src/zrm/__init__.py` (~270 lines).

## Core Architecture

### Design Principles

1. **Single-file implementation**: Everything in `src/zrm/__init__.py`
2. **Global session**: Single Zenoh session shared across all components (lazy-initialized, thread-safe)
3. **Protobuf-only**: All messages use protobuf serialization via `zenoh.ZBytes()`
4. **Zero ceremony**: No explicit node creation, components instantiate directly
5. **Separation of concerns**: Publisher is write-only, Subscriber is read-only

### Core Components

- **Publisher**: Write-only, stateless. Uses `session.declare_publisher()` and `put()`
- **Subscriber**: Read-only with `latest()` method and optional callback. Thread-safe message caching
- **ServiceServer**: Uses Zenoh's `declare_queryable()` for request-response
- **ServiceClient**: Uses Zenoh's `session.get()` for synchronous service calls

### Key Implementation Details

- **Session management**: `_get_session()` uses double-checked locking pattern
- **Serialization**: `_serialize()` and `_deserialize()` wrap protobuf ↔ ZBytes conversion
- **Thread safety**: Subscriber uses `threading.Lock()` for `_latest_msg` access
- **Error types**: `ServiceError` for service failures, standard `TimeoutError`, `TypeError`

## Protobuf Workflow

### Generating Python Code from Proto Files
```bash

# Standard protobuf definitions are in proto/
./protoc-33.0-linux-x86_64/bin/protoc \
  --pyi_out=src/zrm/generated_protos \
  --python_out=src/zrm/generated_protos \
  -Iproto \
  $(fd --extension proto)
```

### Standard Messages

- `proto/geometry.proto`: Point, Vector3, Quaternion, Pose, Pose2D, Twist, PoseStamped
- `proto/services.proto`: AddTwoInts, ComputePath, GetTransform (example services)

## Development Commands

### Dependencies

Uses `uv` for package management. Core dependencies:
- `eclipse-zenoh>=1.6.2`
- `protobuf>=6.33.0`

### Package Management

```bash
# Install dependencies
uv sync

# Run Python code
uv run python script.py
```

## Important Constraints

1. **No dynamic attribute access**: Avoid `hasattr()`, `getattr()`, and `setattr()`. Use direct attribute access and explicit checks instead. Dynamic attribute access reduces code clarity and makes type checking difficult.
2. **Type validation**: All components validate message types at runtime with `isinstance()`
3. **Namespaced imports**: Use fully qualified names (one level) for clarity, except for `typing` module. Examples:
   - Use `pathlib.Path` not `Path`
   - Use `geometry_pb2.Pose` not `Pose`
   - Exception: `typing` imports can be direct (e.g., `from typing import Optional`)

## API Usage Pattern

```python
from zrm import Publisher, Subscriber, ServiceServer, ServiceClient
from generated_protos import geometry_pb2, example_services_pb2

# Publisher/Subscriber
pub = Publisher("robot/pose", geometry_pb2.Pose)
sub = Subscriber("robot/pose", geometry_pb2.Pose, callback=lambda msg: print(msg))

pub.publish(geometry_pb2.Pose(x=1.0, y=2.0))
latest = sub.latest()  # Thread-safe

# Services (using namespaced Request/Response)
def handle_request(req):
    return example_services_pb2.AddTwoInts.Response(sum=req.a + req.b)

server = ServiceServer("service_name", example_services_pb2.AddTwoInts, handle_request)
client = ServiceClient("service_name", example_services_pb2.AddTwoInts)
request = example_services_pb2.AddTwoInts.Request(a=1, b=2)
response = client.call(request, timeout=2.0)
```

### Service Message Pattern

All service definitions must use nested Request/Response messages:

```protobuf
message ServiceName {
  message Request {
    // request fields
  }

  message Response {
    // response fields
  }
}
```

The `ServiceServer` and `ServiceClient` classes validate that the provided service type has both nested messages at initialization.

## Related Documentation

See `SPEC.md` for detailed API specification and design rationale.
