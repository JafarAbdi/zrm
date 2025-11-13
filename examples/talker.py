#!/usr/bin/env python3
"""Example publisher that sends Pose2D messages."""

import time
import math

import zrm
from zrm import Node
from zrm.msgs import geometry_pb2 as geometry_msgs


def main():
    # Create node
    node = Node("talker_node")

    # Create publisher via node factory method
    pub = node.create_publisher("robot/pose", geometry_msgs.Pose2D)
    print("Publisher started on topic 'robot/pose'")

    # Publish messages in a loop
    count = 0
    try:
        while True:
            # Create a message with circular motion
            t = count * 0.1
            msg = geometry_msgs.Pose2D(
                x=math.cos(t),
                y=math.sin(t),
                theta=t,
            )

            pub.publish(msg)
            print(f"Published: x={msg.x:.2f}, y={msg.y:.2f}, theta={msg.theta:.2f}")

            count += 1
            time.sleep(0.5)

    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        pub.close()
        node.close()
        zrm.shutdown()


if __name__ == "__main__":
    main()
