# ZRM (Zenoh ROS-like Middleware)
[![CI](https://github.com/JafarAbdi/zrm/actions/workflows/ci.yml/badge.svg)](https://github.com/JafarAbdi/zrm/actions/workflows/ci.yml)

A minimal, single-file communication middleware built on Zenoh, providing a clean and simple API inspired by ROS2 patterns.

## Features

- **Minimalist**: [Single-file implementation](src/zrm/__init__.py)
- **Type-safe**: Protobuf-based serialization with runtime type checking
- **Ergonomic**: Pythonic API with sensible defaults

## Installation

```bash
# Install from PyPI
pip install zrm
```

For development:

```bash
# Clone the repository and install dependencies
git clone https://github.com/yourusername/zrm.git
cd zrm
uv sync
```

## Development

### Linting

Run linting and formatting checks using pre-commit:

```bash
uv run pre-commit run -a
```

This runs all configured linters and formatters on all files in the repository.

### Testing

Run the test suite with pytest:

```bash
uv run pytest tests/ -v
```

## Quick Start

### Publisher/Subscriber

```python
from zrm import Node
from zrm.generated_protos import geometry_pb2

# Create a node
node = Node("my_node")

# Create publisher and subscriber via node factory methods
pub = node.create_publisher("robot/pose", geometry_pb2.Pose2D)
sub = node.create_subscriber("robot/pose", geometry_pb2.Pose2D)

# Publish a message
pose = geometry_pb2.Pose2D(x=1.0, y=2.0, theta=0.5)
pub.publish(pose)

# Get latest message
current_pose = sub.latest()
if current_pose:
    print(f"Position: x={current_pose.x}, y={current_pose.y}")

# Clean up
pub.close()
sub.close()
node.close()
```

### Subscriber with Callback

```python
def handle_pose(pose):
    print(f"Received: x={pose.x}, y={pose.y}")

node = Node("listener_node")
sub = node.create_subscriber(
    topic="robot/pose",
    msg_type=geometry_pb2.Pose2D,
    callback=handle_pose,
)
```

### Service Server/Client

Services use namespaced Request/Response messages for better organization:

```python
from zrm import Node
from zrm.generated_protos import example_services_pb2

# Define service handler
def add_callback(req):
    return example_services_pb2.AddTwoInts.Response(sum=req.a + req.b)

# Create node
node = Node("service_node")

# Create service server via node factory method
server = node.create_service(
    service="add_two_ints",
    service_type=example_services_pb2.AddTwoInts,
    callback=add_callback,
)

# Create service client via node factory method
client = node.create_client(
    service="add_two_ints",
    service_type=example_services_pb2.AddTwoInts,
)

# Call service
request = example_services_pb2.AddTwoInts.Request(a=5, b=3)
response = client.call(request)
print(f"Sum: {response.sum}")  # Output: 8

# Clean up
client.close()
server.close()
node.close()
```

**Service Definition Pattern:**
```protobuf
// Services must have nested Request and Response messages
message AddTwoInts {
  message Request {
    int32 a = 1;
    int32 b = 2;
  }

  message Response {
    int32 sum = 1;
  }
}
```

## Protobuf Workflow

ZRM uses protobuf for all message serialization. Standard message definitions are in `proto/`.

### Generating Python Code

```bash
# To make sure protoc generate the files with the correct import paths
./protoc-33.0-linux-x86_64/bin/protoc \
  --pyi_out=src \
  --python_out=src \
  --proto_path=zrm/generated_protos=proto \
  $(fd --extension proto)
```

### Standard Messages

- **geometry.proto**: Point, Vector3, Quaternion, Pose, Pose2D, Twist, PoseStamped
- **services.proto**: Trigger

## CLI Tools

ZRM provides command-line tools for inspecting the network:

```bash
# List all nodes in the network
uv run zrm-nodes

# List all topics and their publishers/subscribers
uv run zrm-topics

# List all services in the network
uv run zrm-services
```

## Examples

See `examples/` directory for complete working examples:
- `talker.py` / `listener.py`: Basic publisher/subscriber pattern
- `service_server.py` / `service_client.py`: Service request/response pattern
- Graph discovery and introspection

## Acknowledgements

- The Graph class is inspired by [ros-z](https://github.com/ZettaScaleLabs/ros-z)
- Built on [Eclipse Zenoh](https://zenoh.io/) for efficient pub/sub and query/reply patterns
