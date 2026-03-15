#!/usr/bin/env python3
"""Example subscriber that receives Pose2D messages."""

import time

import zrm
from zrm.msgs import geometry_pb2


def pose_callback(msg: geometry_pb2.Pose2D):
    """Callback function called whenever a message is received."""
    print(f"Received: x={msg.x:.2f}, y={msg.y:.2f}, theta={msg.theta:.2f}")


def main():
    with zrm.open(name="listener") as session:
        sub = zrm.Subscriber(
            session, "robot/pose", geometry_pb2.Pose2D, callback=pose_callback
        )
        print("Subscriber started on topic 'robot/pose'")
        print("Waiting for messages... (Ctrl+C to exit)\n")

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            sub.close()


if __name__ == "__main__":
    main()
