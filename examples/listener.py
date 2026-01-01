#!/usr/bin/env python3
"""Example subscriber that receives Pose2D messages."""

import time

import zrm
from zrm.msgs import geometry_pb2 as geometry_msgs


def pose_callback(msg: geometry_msgs.Pose2D):
    """Callback function called whenever a message is received."""
    print(f"Received: x={msg.x:.2f}, y={msg.y:.2f}, theta={msg.theta:.2f}")


def main():
    # Create node
    node = zrm.Node("listener_node")

    # Create subscriber via node factory method
    sub = node.create_subscriber(
        "robot/pose", geometry_msgs.Pose2D, callback=pose_callback
    )
    print("Subscriber started on topic 'robot/pose'")
    print("Waiting for messages... (Ctrl+C to exit)\n")

    try:
        # Keep the program running
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        sub.close()
        node.close()
        zrm.shutdown()


if __name__ == "__main__":
    main()
