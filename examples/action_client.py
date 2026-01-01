#!/usr/bin/env python3
"""Example action client that requests Fibonacci sequences."""

import zrm
from zrm import Node
from zrm.actions import examples_pb2 as fibonacci_pb2


def feedback_callback(feedback: fibonacci_pb2.Fibonacci.Feedback) -> None:
    """Callback for receiving feedback during goal execution."""
    print(f"Feedback received: {list(feedback.partial_sequence)}")


def main():
    # Create node
    node = Node("fibonacci_action_client")

    # Create action client via node factory method
    client = node.create_action_client(
        "fibonacci",
        fibonacci_pb2.Fibonacci,
    )
    print("Fibonacci action client ready")

    try:
        # Send a goal
        order = 10
        print(f"\nSending goal: order={order}")

        goal = fibonacci_pb2.Fibonacci.Goal(order=order)
        goal_handle = client.send_goal(goal, feedback_callback=feedback_callback)
        print(f"Goal accepted with ID: {goal_handle.goal_id}")

        # Wait for result
        print("Waiting for result...")
        result = goal_handle.get_result(timeout=30.0)
        print(f"\nResult: {list(result.sequence)}")
        print(f"Final status: {goal_handle.status}")

    except TimeoutError as e:
        print(f"Timeout: {e}")
    except zrm.ActionError as e:
        print(f"Action error: {e}")
    except KeyboardInterrupt:
        print("\nCanceling goal...")
        if goal_handle:
            goal_handle.cancel()
    finally:
        client.close()
        node.close()
        zrm.shutdown()


if __name__ == "__main__":
    main()
