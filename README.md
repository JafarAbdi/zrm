# ZRM (Zenoh ROS-like Middleware)
[![CI](https://github.com/JafarAbdi/zrm/actions/workflows/ci.yml/badge.svg)](https://github.com/JafarAbdi/zrm/actions/workflows/ci.yml)

A minimal, single-file communication middleware built on Zenoh, providing a clean and simple API inspired by ROS2 patterns.

https://github.com/user-attachments/assets/3e41d9a7-f553-457b-a879-cae2af45bf63

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
git clone https://github.com/JafarAbdi/zrm.git
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
from zrm.msgs import geometry_pb2

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
from zrm.srvs import examples_pb2

# Define service handler
def add_callback(req):
    return examples_pb2.AddTwoInts.Response(sum=req.a + req.b)

# Create node
node = Node("service_node")

# Create service server via node factory method
server = node.create_service(
    service="add_two_ints",
    service_type=examples_pb2.AddTwoInts,
    callback=add_callback,
)

# Create service client via node factory method
client = node.create_client(
    service="add_two_ints",
    service_type=examples_pb2.AddTwoInts,
)

# Call service
request = examples_pb2.AddTwoInts.Request(a=5, b=3)
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

## Message Organization

ZRM uses a convention-based message organization with the `zrm-proto` CLI tool to generate Python modules from protobuf definitions.

### Directory Structure

Packages must follow this structure:

```
src/<package>/
├── proto/                 # Proto definitions
│   ├── msgs/              # Message definitions (.proto files)
│   └── srvs/              # Service definitions (.proto files)
├── msgs/                  # Generated message modules (*_pb2.py)
└── srvs/                  # Generated service modules (*_pb2.py)
```

### Generating Python Code

```bash
# Generate protos (run from package root)
zrm-proto

# Generate protos for a package that depends on zrm
zrm-proto --dep zrm
```

The tool auto-discovers the package from `src/<package>/proto/`. The `--dep` flag looks up the proto directory from installed packages, so dependencies must be installed first.

### Standard Messages

**Messages** (`zrm.msgs`):
- **geometry**: Point, Vector3, Quaternion, Pose, Pose2D, Twist, PoseStamped
- **sensor**: Image, LaserScan, PointCloud2
- **header**: Header

**Services** (`zrm.srvs`):
- **std**: Trigger

## CLI Tools

ZRM provides command-line tools for inspecting and interacting with the network:

### Topic Commands

```bash
# List all topics and their publishers/subscribers
zrm-topic list

# Echo messages from a topic (auto-discovers type)
zrm-topic echo robot/pose

# Echo with explicit type
zrm-topic echo robot/pose -t zrm/msgs/geometry/Pose2D

# Publish to a topic
zrm-topic pub robot/pose "x: 1.0 y: 2.0 theta: 0.5" -t zrm/msgs/geometry/Pose2D -r 10

# Measure topic frequency
zrm-topic hz robot/pose
```

### Node Commands

```bash
# List all nodes in the network
zrm-node list
```

### Service Commands

```bash
# List all services in the network
zrm-service list

# Call a service (auto-discovers type)
zrm-service call add_two_ints 'a: 1 b: 2'

# Call with explicit type
zrm-service call add_two_ints 'a: 1 b: 2' -t zrm/srvs/examples/AddTwoInts
```

## Examples

See `examples/` directory for complete working examples:
- `talker.py` / `listener.py`: Basic publisher/subscriber pattern
- `service_server.py` / `service_client.py`: Service request/response pattern
- Graph discovery and introspection

## Acknowledgements

- The Graph class is inspired by [ros-z](https://github.com/ZettaScaleLabs/ros-z)
- Built on [Eclipse Zenoh](https://zenoh.io/) for efficient pub/sub and query/reply patterns
