# ZRM (Zenoh ROS-like Middleware)

[![CI](https://github.com/JafarAbdi/zrm/actions/workflows/ci.yml/badge.svg)](https://github.com/JafarAbdi/zrm/actions/workflows/ci.yml)

A minimal, single-file communication middleware built on Zenoh, providing a clean and simple API inspired by ROS2 patterns.

https://github.com/user-attachments/assets/3e41d9a7-f553-457b-a879-cae2af45bf63

## Features

- **Minimalist**: [Single-file implementation](src/zrm/__init__.py)
- **Type-safe**: Protobuf-based serialization with runtime type checking
- **Ergonomic**: Pythonic API with sensible defaults

## Migration from v2.x

v3.0 replaces the `Node`-based API with a simpler session-centric architecture. If you prefer the old API, pin to `zrm==2.1.0`.

## Installation

```bash
pip install zrm
```

Requires Python 3.10+.

## Quick Start

```python
import zrm
from zrm.msgs import geometry_pb2

with zrm.open(name="my_session") as session:
    # Publish
    pub = zrm.Publisher(session, "robot/pose", geometry_pb2.Pose2D)
    pub.publish(geometry_pb2.Pose2D(x=1.0, y=2.0, theta=0.5))

    # Subscribe
    sub = zrm.Subscriber(session, "robot/pose", geometry_pb2.Pose2D)
    if pose := sub.latest():
        print(f"Position: x={pose.x}, y={pose.y}")

    pub.close()
    sub.close()
```

**Protobuf definition:**
```protobuf
message Pose2D {
  double x = 1;
  double y = 2;
  double theta = 3;
}
```

## CLI Tools

```bash
zrm-topic list                    # List topics
zrm-topic echo robot/pose         # Echo messages
zrm-topic pub robot/pose 'x: 1.0' # Publish to topic
zrm-topic hz robot/pose           # Measure frequency
zrm-service list                  # List services
zrm-service call add 'a: 1 b: 2'  # Call service
zrm-session list                  # List sessions
```

## More Examples

See `examples/` for complete working examples including services and graph discovery.

---

<details>
<summary><b>Configuration</b></summary>

### Environment Variables

ZRM checks environment variables for Zenoh configuration (priority order):

1. `ZRM_CONFIG_FILE` - path to a JSON5 config file
2. `ZRM_CONFIG` - inline JSON5 config string
3. `ZENOH_CONFIG` - Zenoh's native config file path

```bash
# Inline config
export ZRM_CONFIG='{ mode: "peer", listen: { endpoints: ["tcp/0.0.0.0:0#iface=enp8s0"] } }'

# Or with multicast discovery
export ZRM_CONFIG='{
  mode: "peer",
  listen: { endpoints: ["tcp/0.0.0.0:0#iface=enp8s0"] },
  scouting: { multicast: { enabled: true, interface: "enp8s0" } }
}'

# Or from a file
export ZRM_CONFIG_FILE=/path/to/config.json5
```

### Programmatic Configuration

```python
import zenoh
import zrm

config = zenoh.Config()
config.insert_json5("mode", "'peer'")
config.insert_json5("listen/endpoints", "['tcp/0.0.0.0:0#iface=enp8s0']")

with zrm.open(config) as session:
    pub = zrm.Publisher(session, "robot/pose", geometry_pb2.Pose2D)
```
</details>

<details>
<summary><b>Services</b></summary>

Services use nested Request/Response messages:

```python
import zrm
from zrm.srvs import examples_pb2

def add_callback(req):
    return examples_pb2.AddTwoInts.Response(sum=req.a + req.b)

with zrm.open(name="service_example") as session:
    server = zrm.Server(session, "add_two_ints", examples_pb2.AddTwoInts, add_callback)
    client = zrm.Client(session, "add_two_ints", examples_pb2.AddTwoInts)

    response = client.call(examples_pb2.AddTwoInts.Request(a=5, b=3), timeout=5.0)
    print(f"Sum: {response.sum}")  # Output: 8

    server.close()
    client.close()
```

**Protobuf definition:**
```protobuf
message AddTwoInts {
  message Request { int32 a = 1; int32 b = 2; }
  message Response { int32 sum = 1; }
}
```
</details>

<details>
<summary><b>Graph Discovery</b></summary>

Discover topics, services, publishers, and subscribers in the network:

```python
import zrm

with zrm.open(name="discovery") as session:
    graph = zrm.Graph(session)

    # Get all topics and services
    topics = graph.get_topics()      # [(name, type), ...]
    services = graph.get_services()  # [(name, type), ...]

    # Get publishers/subscribers for a topic
    pubs = graph.get_publishers("robot/pose")
    subs = graph.get_subscribers("robot/pose")

    # Get servers/clients for a service
    servers = graph.get_servers("add_two_ints")
    clients = graph.get_clients("add_two_ints")

    # Wait for entities to appear
    graph.wait_for_publisher("robot/pose", timeout=5.0)
    graph.wait_for_server("add_two_ints", timeout=5.0)

    graph.close()
```
</details>

<details>
<summary><b>Message Organization & Proto Generation</b></summary>

### Directory Structure

```
src/<package>/
├── proto/                 # Proto definitions
│   ├── msgs/              # Message definitions
│   └── srvs/              # Service definitions
├── msgs/                  # Auto-generated *_pb2.py
└── srvs/                  # Auto-generated *_pb2.py
```

### Generating Python Code

```bash
zrm-proto              # Generate from local protos
zrm-proto --dep zrm    # Include dependency protos
```

### Standard Messages

| Category | Module | Types |
|----------|--------|-------|
| Messages | `zrm.msgs.header_pb2` | Header |
| Messages | `zrm.msgs.geometry_pb2` | Point, Vector3, Quaternion, Pose, Pose2D, Twist, PoseStamped |
| Messages | `zrm.msgs.sensor_pb2` | Imu, Image, CompressedImage, CameraInfo, JointState |
| Messages | `zrm.msgs.vision_pb2` | Point2D, BoundingBox2D |
| Services | `zrm.srvs.std_pb2` | Trigger |
| Services | `zrm.srvs.examples_pb2` | AddTwoInts |
</details>

<details>
<summary><b>Logging</b></summary>

ZRM initializes Zenoh logging from the `RUST_LOG` environment variable, defaulting to `error`. Set it to see more output:

```bash
# Show info-level logs
RUST_LOG=info python my_app.py

# Show debug-level logs
RUST_LOG=debug python my_app.py

# Filter to specific modules
RUST_LOG=zenoh=info python my_app.py
```

Valid levels: `error`, `warn`, `info`, `debug`, `trace`.
</details>

<details>
<summary><b>Development</b></summary>

```bash
git clone https://github.com/JafarAbdi/zrm.git
cd zrm
uv sync

# Linting
uv run pre-commit run -a

# Testing
uv run pytest tests/ -v
```
</details>

## Acknowledgements

- Graph class inspired by [ros-z](https://github.com/ZettaScaleLabs/ros-z)
- Built on [Eclipse Zenoh](https://zenoh.io/)
