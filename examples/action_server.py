#!/usr/bin/env python3
"""Example action server that computes Fibonacci sequences."""

import time

import zrm
from zrm import Node, ServerGoalHandle
from zrm.actions import examples_pb2 as fibonacci_pb2


def execute_fibonacci(goal_handle: ServerGoalHandle) -> None:
    """Execute callback for the Fibonacci action.

    Computes a Fibonacci sequence up to the requested order,
    publishing feedback after each number is computed.
    """
    goal = goal_handle.goal
    order = goal.order

    print(f"Executing goal: computing Fibonacci sequence of order {order}")

    # Transition to executing state
    goal_handle.execute()

    # Initialize sequence
    sequence = [0, 1]

    # Compute Fibonacci sequence
    for i in range(1, order):
        # Check for cancellation
        if goal_handle.cancel_requested:
            print("Goal canceled!")
            result = fibonacci_pb2.Fibonacci.Result(sequence=sequence)
            goal_handle.cancel(result)
            return

        # Compute next Fibonacci number
        sequence.append(sequence[i] + sequence[i - 1])

        # Publish feedback
        feedback = fibonacci_pb2.Fibonacci.Feedback(partial_sequence=sequence)
        goal_handle.publish_feedback(feedback)
        print(f"  Feedback: {sequence}")

        # Simulate work
        time.sleep(1)

    # Goal succeeded
    result = fibonacci_pb2.Fibonacci.Result(sequence=sequence)
    goal_handle.succeed(result)
    print(f"Goal succeeded: {sequence}")


def main():
    # Create node
    node = Node("fibonacci_action_server")

    # Create action server via node factory method
    server = node.create_action_server(
        "fibonacci",
        fibonacci_pb2.Fibonacci,
        execute_fibonacci,
    )
    print("Fibonacci action server started")
    print("Waiting for goals... (Ctrl+C to exit)")

    try:
        # Keep the server running
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        server.close()
        node.close()
        zrm.shutdown()


if __name__ == "__main__":
    main()
