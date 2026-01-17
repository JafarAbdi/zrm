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
pip install zrm
```

## Quick Start

```python
import zrm
from zrm.msgs import geometry_pb2

node = zrm.Node("my_node")

# Publish
pub = node.create_publisher("robot/pose", geometry_pb2.Pose2D)
pub.publish(geometry_pb2.Pose2D(x=1.0, y=2.0, theta=0.5))

# Subscribe
sub = node.create_subscriber("robot/pose", geometry_pb2.Pose2D)
if pose := sub.latest():
    print(f"Position: x={pose.x}, y={pose.y}")

node.close()
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
zrm-service list                  # List services
zrm-service call add 'a: 1 b: 2'  # Call service
zrm-action list                   # List actions
zrm-action send fib 'order: 10'   # Send action goal
zrm-node list                     # List nodes
```

## More Examples

See `examples/` for complete working examples including services, actions with feedback/cancellation, and graph discovery.

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

zrm.init(config)
node = zrm.Node("my_node")
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

node = zrm.Node("service_node")
server = node.create_service("add_two_ints", examples_pb2.AddTwoInts, add_callback)
client = node.create_client("add_two_ints", examples_pb2.AddTwoInts)

response = client.call(examples_pb2.AddTwoInts.Request(a=5, b=3))
print(f"Sum: {response.sum}")  # Output: 8

node.close()
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
<summary><b>Actions</b></summary>

Actions support long-running goals with feedback and cancellation:

```python
import zrm
from zrm.actions import examples_pb2

def execute_fibonacci(goal_handle: zrm.ServerGoalHandle) -> None:
    goal_handle.execute()
    sequence = [0, 1]
    for i in range(1, goal_handle.goal.order):
        if goal_handle.cancel_requested:
            goal_handle.cancel(examples_pb2.Fibonacci.Result(sequence=sequence))
            return
        sequence.append(sequence[i] + sequence[i - 1])
        goal_handle.publish_feedback(examples_pb2.Fibonacci.Feedback(partial_sequence=sequence))
    goal_handle.succeed(examples_pb2.Fibonacci.Result(sequence=sequence))

node = zrm.Node("action_node")
server = node.create_action_server("fibonacci", examples_pb2.Fibonacci, execute_fibonacci)
client = node.create_action_client("fibonacci", examples_pb2.Fibonacci)

goal_handle = client.send_goal(
    examples_pb2.Fibonacci.Goal(order=10),
    feedback_callback=lambda fb: print(f"Progress: {list(fb.partial_sequence)}")
)
result = goal_handle.get_result(timeout=30.0)
print(f"Result: {list(result.sequence)}")

node.close()
```

**Protobuf definition:**
```protobuf
message Fibonacci {
  message Goal { int32 order = 1; }
  message Result { repeated int32 sequence = 1; }
  message Feedback { repeated int32 partial_sequence = 1; }
}
```
</details>

<details>
<summary><b>Message Organization & Proto Generation</b></summary>

### Directory Structure

```
src/<package>/
├── proto/                 # Proto definitions
│   ├── msgs/              # Message definitions
│   ├── srvs/              # Service definitions
│   └── actions/           # Action definitions
├── msgs/                  # Auto-generated *_pb2.py
├── srvs/                  # Auto-generated *_pb2.py
└── actions/               # Auto-generated *_pb2.py
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
| Actions | `zrm.actions.examples_pb2` | Fibonacci |
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
