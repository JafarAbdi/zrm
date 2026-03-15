#!/usr/bin/env python3
"""Example publisher that sends Pose2D messages."""

import math
import time

import zrm
from zrm.msgs import geometry_pb2


def main():
    with zrm.open(name="talker") as session:
        pub = zrm.Publisher(session, "robot/pose", geometry_pb2.Pose2D)
        print("Publisher started on topic 'robot/pose'")

        count = 0
        try:
            while True:
                # Create a message with circular motion.
                t = count * 0.1
                msg = geometry_pb2.Pose2D(
                    x=math.cos(t),
                    y=math.sin(t),
                    theta=t,
                )

                pub.publish(msg)
                print(f"Published: x={msg.x:.2f}, y={msg.y:.2f}, theta={msg.theta:.2f}")

                count += 1
                time.sleep(0.5)

        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            pub.close()


if __name__ == "__main__":
    main()
