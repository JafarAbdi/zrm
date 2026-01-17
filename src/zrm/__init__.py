"""ZRM: Minimal Zenoh-based communication middleware with ROS-like API."""

from __future__ import annotations

import os
import pathlib
import sys
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import enum

import zenoh


from google.protobuf.message import Message

# Environment variable names for configuration
ZRM_CONFIG_FILE_ENV = "ZRM_CONFIG_FILE"
ZRM_CONFIG_ENV = "ZRM_CONFIG"

# StrEnum was added in Python 3.11
if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    # Based on https://github.com/irgeek/StrEnum for compatibility with python<3.11
    class StrEnum(str, enum.Enum):
        """
        StrEnum is a Python ``enum.Enum`` that inherits from ``str``. The default
        ``auto()`` behavior uses the member name as its value.

        Example usage::

            class Example(StrEnum):
                UPPER_CASE = auto()
                lower_case = auto()
                MixedCase = auto()

            assert Example.UPPER_CASE == "UPPER_CASE"
            assert Example.lower_case == "lower_case"
            assert Example.MixedCase == "MixedCase"
        """

        def __new__(cls, value, *args, **kwargs):
            if not isinstance(value, (str, enum.auto)):
                raise TypeError(
                    f"Values of StrEnums must be strings: {value!r} is a {type(value)}"
                )
            return super().__new__(cls, value, *args, **kwargs)

        def __str__(self):
            return str(self.value)

        def _generate_next_value_(name, *_):
            return name


__all__ = [
    "ActionClient",
    "ActionError",
    "ActionServer",
    "ClientGoalHandle",
    "GoalStatus",
    "InvalidTopicName",
    "MessageTypeMismatchError",
    "Node",
    "Publisher",
    "ServerGoalHandle",
    "ServiceCancelled",
    "ServiceClient",
    "ServiceError",
    "ServiceFuture",
    "ServiceServer",
    "Subscriber",
    "init",
    "shutdown",
]

# Global constants
DOMAIN_ID = 0
ADMIN_SPACE = "@zrm_lv"


class InvalidTopicName(ValueError):
    """Exception raised when a topic name is invalid."""


def clean_topic_name(key: str) -> str:
    """Validate and return topic name.

    Zenoh forbids keys starting with '/'. This function validates that the
    topic name does not start with a leading slash.

    Args:
        key: Topic or service name (e.g., "robot/pose")

    Returns:
        The validated topic name

    Raises:
        InvalidTopicName: If the key starts with '/'

    Examples:
        >>> clean_topic_name("robot/pose")
        'robot/pose'
        >>> clean_topic_name("/robot/pose")
        Traceback (most recent call last):
            ...
        InvalidTopicName: Topic name '/robot/pose' cannot start with '/'. Use 'robot/pose' instead.
    """
    if key.startswith("/"):
        raise InvalidTopicName(
            f"Topic name '{key}' cannot start with '/'. Use '{key.lstrip('/')}' instead."
        )
    return key


def _validate_service_type(service_type: type) -> None:
    """Validate that a type is a valid service type with Request and Response.

    Args:
        service_type: Type to validate

    Raises:
        TypeError: If type is invalid or missing nested messages
    """
    if not isinstance(service_type, type):
        raise TypeError(
            f"service_type must be a protobuf message class, got {type(service_type).__name__}"
        )
    if not hasattr(service_type, "Request"):
        raise TypeError(
            f"Service type '{service_type.__name__}' must have a nested 'Request' message"
        )
    if not hasattr(service_type, "Response"):
        raise TypeError(
            f"Service type '{service_type.__name__}' must have a nested 'Response' message"
        )


def _validate_action_type(action_type: type) -> None:
    """Validate that a type is a valid action type with Goal, Result, and Feedback.

    Args:
        action_type: Type to validate

    Raises:
        TypeError: If type is invalid or missing nested messages
    """
    if not isinstance(action_type, type):
        raise TypeError(
            f"action_type must be a protobuf message class, got {type(action_type).__name__}"
        )
    if not hasattr(action_type, "Goal"):
        raise TypeError(
            f"Action type '{action_type.__name__}' must have a nested 'Goal' message"
        )
    if not hasattr(action_type, "Result"):
        raise TypeError(
            f"Action type '{action_type.__name__}' must have a nested 'Result' message"
        )
    if not hasattr(action_type, "Feedback"):
        raise TypeError(
            f"Action type '{action_type.__name__}' must have a nested 'Feedback' message"
        )


# Global context management
_global_context: "Context | None" = None
_context_lock = threading.Lock()


def _load_config_from_env() -> zenoh.Config | None:
    """Load Zenoh configuration from environment variables.

    Priority order:
        1. ZRM_CONFIG_FILE - path to a JSON5 config file
        2. ZRM_CONFIG - inline JSON5 config string
        3. ZENOH_CONFIG - Zenoh's native config file path (via Config.from_env())

    Returns:
        zenoh.Config if environment variable is set, None otherwise

    Raises:
        FileNotFoundError: If config file path points to non-existent file
        ValueError: If config parsing fails
    """
    config_file = os.environ.get(ZRM_CONFIG_FILE_ENV)
    if config_file:
        path = pathlib.Path(config_file)
        if not path.exists():
            raise FileNotFoundError(
                f"{ZRM_CONFIG_FILE_ENV} points to non-existent file: {config_file}"
            )
        return zenoh.Config.from_file(config_file)

    config_str = os.environ.get(ZRM_CONFIG_ENV)
    if config_str:
        return zenoh.Config.from_json5(config_str)

    # Fall back to Zenoh's native ZENOH_CONFIG env var
    if os.environ.get("ZENOH_CONFIG"):
        return zenoh.Config.from_env()

    return None


class Context:
    """Context holds the Zenoh session and domain configuration."""

    def __init__(self, config: zenoh.Config | None = None, domain_id: int = DOMAIN_ID):
        """Create a new context.

        Args:
            config: Optional Zenoh configuration. If None, checks ZRM_CONFIG_FILE,
                    ZRM_CONFIG, and ZENOH_CONFIG environment variables before
                    using default.
            domain_id: Domain ID for this context (default: DOMAIN_ID constant = 0)
        """
        zenoh.init_log_from_env_or("error")
        effective_config = config if config is not None else _load_config_from_env()
        self._session = zenoh.open(
            effective_config if effective_config is not None else zenoh.Config()
        )
        self._domain_id = domain_id

    @property
    def session(self) -> zenoh.Session:
        """Get the Zenoh session."""
        return self._session

    @property
    def domain_id(self) -> int:
        """Get the domain ID."""
        return self._domain_id

    def close(self) -> None:
        """Close the context and release resources."""
        self._session.close()


def _get_context() -> Context:
    """Get or create the global default context."""
    global _global_context
    if _global_context is None:
        with _context_lock:
            if _global_context is None:
                _global_context = Context()
    return _global_context


class MessageTypeMismatchError(TypeError):
    """Exception raised when message types don't match between publisher and subscriber."""


class ServiceError(Exception):
    """Exception raised when a service call fails."""


class ActionError(Exception):
    """Exception raised when an action fails."""


class GoalStatus(StrEnum):
    """Status of a goal in the action system.

    Follows a simplified state machine:
    - PENDING: Goal received by server, not yet executing
    - EXECUTING: Goal is actively being processed
    - CANCELING: Cancel requested, goal is finishing up
    - SUCCEEDED: Goal completed successfully
    - ABORTED: Goal was aborted by the server (error during execution)
    - CANCELED: Goal was canceled (by client or preempted by new goal)

    State transitions:
        PENDING -> EXECUTING, CANCELED
        EXECUTING -> CANCELING, SUCCEEDED, ABORTED, CANCELED
        CANCELING -> SUCCEEDED, ABORTED, CANCELED
    """

    PENDING = "PENDING"
    EXECUTING = "EXECUTING"
    CANCELING = "CANCELING"
    SUCCEEDED = "SUCCEEDED"
    ABORTED = "ABORTED"
    CANCELED = "CANCELED"

    def is_terminal(self) -> bool:
        """Check if this is a terminal state (goal has completed)."""
        return self in (GoalStatus.SUCCEEDED, GoalStatus.ABORTED, GoalStatus.CANCELED)

    def can_transition_to(self, target: GoalStatus) -> bool:
        """Check if transition to target state is valid."""
        valid_transitions: dict[GoalStatus, tuple[GoalStatus]] = {
            GoalStatus.PENDING: (GoalStatus.EXECUTING, GoalStatus.CANCELED),
            GoalStatus.EXECUTING: (
                GoalStatus.CANCELING,
                GoalStatus.SUCCEEDED,
                GoalStatus.ABORTED,
                GoalStatus.CANCELED,
            ),
            GoalStatus.CANCELING: (
                GoalStatus.SUCCEEDED,
                GoalStatus.ABORTED,
                GoalStatus.CANCELED,
            ),
        }
        return target in valid_transitions.get(self, tuple())


class ServiceCancelled(Exception):
    """Exception raised when a service call is cancelled."""


class EntityKind(StrEnum):
    """Kind of entity in the graph."""

    NODE = "NN"
    PUBLISHER = "MP"
    SUBSCRIBER = "MS"
    SERVICE = "SS"
    CLIENT = "SC"
    ACTION_SERVER = "AS"
    ACTION_CLIENT = "AC"


@dataclass
class ParsedEntity:
    """Minimal parsed entity data from liveliness key."""

    kind: EntityKind
    node_name: str
    topic: str | None = None  # None for NODE kind
    type_name: str | None = None


def _make_node_lv_key(domain_id: int, z_id: str, name: str) -> str:
    """Build node liveliness key.

    Format: @zrm_lv/{domain_id}/{z_id}/NN/{node_name}
    """
    node_name = name.replace("/", "%")
    return f"{ADMIN_SPACE}/{domain_id}/{z_id}/{EntityKind.NODE}/{node_name}"


def _make_endpoint_lv_key(
    domain_id: int,
    z_id: str,
    kind: EntityKind,
    node_name: str,
    topic: str,
    type_name: str | None,
) -> str:
    """Build endpoint liveliness key.

    Format: @zrm_lv/{domain_id}/{z_id}/{kind}/{node_name}/{topic_name}/{type_name}
    """
    node = node_name.replace("/", "%")
    topic_escaped = topic.replace("/", "%")
    type_info = "EMPTY" if type_name is None else type_name.replace("/", "%")
    return f"{ADMIN_SPACE}/{domain_id}/{z_id}/{kind}/{node}/{topic_escaped}/{type_info}"


def _parse_lv_key(ke: str) -> ParsedEntity:
    """Parse a liveliness key expression into a ParsedEntity.

    Format:
    - Node: @zrm_lv/{domain_id}/{z_id}/NN/{node_name}
    - Endpoint: @zrm_lv/{domain_id}/{z_id}/{kind}/{node_name}/{topic_name}/{type_name}

    Args:
        ke: Liveliness key expression to parse

    Returns:
        ParsedEntity with extracted data

    Raises:
        ValueError: If the key expression is malformed or invalid
    """
    parts = ke.split("/")
    if len(parts) < 5:
        raise ValueError(
            f"Invalid liveliness key '{ke}': expected at least 5 parts, got {len(parts)}"
        )

    if parts[0] != ADMIN_SPACE:
        raise ValueError(
            f"Invalid liveliness key '{ke}': expected admin space '{ADMIN_SPACE}', got '{parts[0]}'"
        )

    try:
        entity_kind = EntityKind(parts[3])
    except ValueError as e:
        raise ValueError(
            f"Invalid liveliness key '{ke}': unknown entity kind '{parts[3]}'"
        ) from e

    node_name = parts[4].replace("%", "/")

    if entity_kind == EntityKind.NODE:
        return ParsedEntity(kind=entity_kind, node_name=node_name)

    # For endpoints, we need at least 7 parts
    if len(parts) < 7:
        raise ValueError(
            f"Invalid liveliness key '{ke}': endpoint entity requires at least 7 parts, got {len(parts)}"
        )

    topic = parts[5].replace("%", "/")
    type_name = None if parts[6] == "EMPTY" else parts[6].replace("%", "/")
    return ParsedEntity(
        kind=entity_kind, node_name=node_name, topic=topic, type_name=type_name
    )


class GraphData:
    """Internal graph data structure with efficient indexing."""

    def __init__(self) -> None:
        """Initialize empty graph data."""
        self._entities: dict[str, ParsedEntity] = {}  # Liveliness key -> parsed entity
        self._by_topic: dict[str, list[str]] = {}  # Topic -> [liveliness keys]
        self._by_service: dict[str, list[str]] = {}  # Service -> [liveliness keys]
        self._by_action: dict[str, list[str]] = {}  # Action -> [liveliness keys]
        self._by_node: dict[str, list[str]] = {}  # Node name -> [liveliness keys]

    def insert(self, ke: str) -> None:
        """Add a new liveliness key and update indexes.

        Args:
            ke: Liveliness key expression to insert

        Note:
            Silently ignores invalid keys to handle malformed data from network.
        """
        try:
            entity = _parse_lv_key(ke)
        except ValueError:
            # Silently ignore invalid keys from network
            return

        # Store it
        self._entities[ke] = entity

        # Index by node
        if entity.node_name not in self._by_node:
            self._by_node[entity.node_name] = []
        self._by_node[entity.node_name].append(ke)

        # Index by topic, service, or action for endpoints
        if entity.kind in (EntityKind.PUBLISHER, EntityKind.SUBSCRIBER):
            if entity.topic is not None:
                if entity.topic not in self._by_topic:
                    self._by_topic[entity.topic] = []
                self._by_topic[entity.topic].append(ke)
        elif entity.kind in (EntityKind.SERVICE, EntityKind.CLIENT):
            if entity.topic is not None:
                if entity.topic not in self._by_service:
                    self._by_service[entity.topic] = []
                self._by_service[entity.topic].append(ke)
        elif entity.kind in (EntityKind.ACTION_SERVER, EntityKind.ACTION_CLIENT):
            if entity.topic is not None:
                if entity.topic not in self._by_action:
                    self._by_action[entity.topic] = []
                self._by_action[entity.topic].append(ke)

    def remove(self, ke: str) -> None:
        """Remove a liveliness key and rebuild indexes."""
        if ke not in self._entities:
            return

        # Remove from entities dict
        del self._entities[ke]

        # Rebuild all indexes from scratch (simpler and correct)
        self._by_topic.clear()
        self._by_service.clear()
        self._by_action.clear()
        self._by_node.clear()

        for key, entity in self._entities.items():
            # Index by node
            if entity.node_name not in self._by_node:
                self._by_node[entity.node_name] = []
            self._by_node[entity.node_name].append(key)

            # Index by topic, service, or action for endpoints
            if entity.kind in (EntityKind.PUBLISHER, EntityKind.SUBSCRIBER):
                if entity.topic is not None:
                    if entity.topic not in self._by_topic:
                        self._by_topic[entity.topic] = []
                    self._by_topic[entity.topic].append(key)
            elif entity.kind in (EntityKind.SERVICE, EntityKind.CLIENT):
                if entity.topic is not None:
                    if entity.topic not in self._by_service:
                        self._by_service[entity.topic] = []
                    self._by_service[entity.topic].append(key)
            elif entity.kind in (EntityKind.ACTION_SERVER, EntityKind.ACTION_CLIENT):
                if entity.topic is not None:
                    if entity.topic not in self._by_action:
                        self._by_action[entity.topic] = []
                    self._by_action[entity.topic].append(key)

    def visit_by_topic(
        self, topic: str, callback: Callable[[ParsedEntity], None]
    ) -> None:
        """Visit all entities for a given topic."""
        if topic in self._by_topic:
            for key in self._by_topic[topic]:
                callback(self._entities[key])

    def visit_by_service(
        self, service: str, callback: Callable[[ParsedEntity], None]
    ) -> None:
        """Visit all entities for a given service."""
        if service in self._by_service:
            for key in self._by_service[service]:
                callback(self._entities[key])

    def visit_by_action(
        self, action: str, callback: Callable[[ParsedEntity], None]
    ) -> None:
        """Visit all entities for a given action."""
        if action in self._by_action:
            for key in self._by_action[action]:
                callback(self._entities[key])

    def visit_by_node(
        self, node_name: str, callback: Callable[[ParsedEntity], None]
    ) -> None:
        """Visit all entities for a given node."""
        if node_name in self._by_node:
            for key in self._by_node[node_name]:
                callback(self._entities[key])


def get_type_name(msg_or_type) -> str:
    """Get the type identifier from a message instance or type.

    Args:
        msg_or_type: Protobuf message instance or class

    Returns:
        Type identifier string like 'zrm/msgs/geometry/Point' or 'zrm/srvs/std/Trigger.Request'

    Examples:
        >>> from zrm.msgs import geometry_pb2
        >>> get_type_name(geometry_pb2.Point)
        'zrm/msgs/geometry/Point'
        >>> from zrm.srvs import std_pb2
        >>> get_type_name(std_pb2.Trigger.Request)
        'zrm/srvs/std/Trigger.Request'
    """

    # file.name: "zrm/msgs/geometry.proto"
    # full_name: "zrm.Point" or "zrm.Trigger.Request"
    file_path = pathlib.Path(msg_or_type.DESCRIPTOR.file.name)
    full_name = msg_or_type.DESCRIPTOR.full_name

    # Parse file path: zrm/msgs/geometry.proto -> category='msgs', module='geometry'
    parts = file_path.parts
    category = parts[1]  # 'msgs' or 'srvs'
    module = file_path.stem  # 'geometry'

    # Parse full_name: "zrm.Point" -> package='zrm', type_path='Point'
    # or "zrm.Trigger.Request" -> package='zrm', type_path='Trigger.Request'
    name_parts = full_name.split(".")
    package = name_parts[0]  # 'zrm'
    type_path = ".".join(name_parts[1:])  # 'Point' or 'Trigger.Request'

    # Build identifier: 'zrm/msgs/geometry/Point'
    return f"{package}/{category}/{module}/{type_path}"


def get_message_type(identifier: str) -> type[Message]:
    """Get message type from identifier string.

    Args:
        identifier: Type identifier like 'zrm/msgs/geometry/Point',
                    'zrm/srvs/std/Trigger.Request', or 'zrm/actions/examples/Fibonacci'

    Returns:
        Protobuf message class

    Examples:
        >>> Point = get_message_type('zrm/msgs/geometry/Point')
        >>> point = Point(x=1.0, y=2.0, z=3.0)
        >>> TriggerRequest = get_message_type('zrm/srvs/std/Trigger.Request')
        >>> Fibonacci = get_message_type('zrm/actions/examples/Fibonacci')
    """
    parts = identifier.split("/")
    if len(parts) != 4:
        raise ValueError(
            f"Invalid identifier format: {identifier}. Expected 'package/category/module/Type'"
        )

    package, category, module_name, type_path = parts

    # Validate category
    if category not in ("msgs", "srvs", "actions"):
        raise ValueError(
            f"Category must be 'msgs', 'srvs', or 'actions', got '{category}'"
        )

    # Import module: zrm.msgs.geometry_pb2
    import_path = f"{package}.{category}.{module_name}_pb2"
    type_parts = type_path.split(".")  # ['Point'] or ['Trigger', 'Request']

    try:
        module = __import__(import_path, fromlist=[type_parts[0]])
    except ImportError as e:
        raise ImportError(f"Failed to import module '{import_path}': {e}") from e

    # Navigate nested types: module.Trigger.Request
    obj = module
    for part in type_parts:
        try:
            obj = getattr(obj, part)
        except AttributeError as e:
            raise AttributeError(
                f"Type '{type_path}' not found in module '{import_path}'"
            ) from e

    return obj


def serialize(msg: Message) -> zenoh.ZBytes:
    """Serialize protobuf message to ZBytes."""
    return zenoh.ZBytes(msg.SerializeToString())


def deserialize(
    payload: zenoh.ZBytes,
    msg_type: type[Message],
    actual_type_name: str,
) -> Message:
    """Deserialize ZBytes to protobuf message with type validation.

    Args:
        payload: Serialized message bytes
        msg_type: Expected protobuf message type
        actual_type_name: Actual type name from wire (must match)

    Raises:
        MessageTypeMismatchError: If actual_type_name doesn't match expected type
    """
    expected_type_name = get_type_name(msg_type)
    if actual_type_name != expected_type_name:
        raise MessageTypeMismatchError(
            f"Message type mismatch: expected '{expected_type_name}', "
            f"got '{actual_type_name}'",
        )

    msg = msg_type()
    msg.ParseFromString(payload.to_bytes())
    return msg


class Publisher:
    """Publisher for sending messages on a topic.

    Publisher is write-only and stateless. It does not cache messages.
    Automatically registers with the graph via liveliness tokens.
    """

    def __init__(
        self,
        context: Context,
        liveliness_key: str,
        topic: str,
        msg_type: type[Message],
    ):
        """Create a publisher.

        Args:
            context: Context containing the Zenoh session
            liveliness_key: Liveliness key for graph discovery
            topic: Zenoh key expression (e.g., "robot/pose")
            msg_type: Protobuf message type
        """
        self._topic = clean_topic_name(topic)
        self._msg_type = msg_type
        self._session = context.session
        self._publisher = self._session.declare_publisher(self._topic)

        # Declare liveliness token for graph discovery
        self._lv_token = self._session.liveliness().declare_token(liveliness_key)

    def publish(self, msg: Message) -> None:
        """Publish a protobuf message.

        Args:
            msg: Protobuf message to publish

        Raises:
            TypeError: If msg is not an instance of the expected message type
        """
        if not isinstance(msg, self._msg_type):
            raise TypeError(
                f"Expected message of type {self._msg_type.__name__}, "
                f"got {type(msg).__name__}",
            )

        # Include type metadata in attachment
        type_name = get_type_name(msg)
        attachment = zenoh.ZBytes(type_name.encode())
        self._publisher.put(serialize(msg), attachment=attachment)

    def close(self) -> None:
        """Close the publisher and release resources."""
        self._lv_token.undeclare()
        self._publisher.undeclare()


class Subscriber:
    """Subscriber for receiving messages on a topic.

    Subscriber is read-only and caches the latest message received.
    Automatically registers with the graph via liveliness tokens.
    """

    def __init__(
        self,
        context: Context,
        liveliness_key: str,
        topic: str,
        msg_type: type[Message],
        callback: Callable[[Message], None] | None = None,
    ):
        """Create a subscriber.

        Args:
            context: Context containing the Zenoh session
            liveliness_key: Liveliness key for graph discovery
            topic: Zenoh key expression (e.g., "robot/pose")
            msg_type: Protobuf message type
            callback: Optional callback function called on each message
        """
        self._topic = clean_topic_name(topic)
        self._msg_type = msg_type
        self._callback = callback
        self._latest_msg: Message | None = None
        self._lock = threading.Lock()

        self._session = context.session

        def listener(sample: zenoh.Sample):
            try:
                # Extract type name from attachment
                if sample.attachment is None:
                    raise MessageTypeMismatchError(
                        f"Received message without type metadata on topic '{self._topic}'. "
                        "Ensure publisher includes type information.",
                    )
                actual_type_name = sample.attachment.to_bytes().decode()

                # Deserialize with type validation
                msg = deserialize(sample.payload, msg_type, actual_type_name)
                with self._lock:
                    self._latest_msg = msg
                if self._callback is not None:
                    self._callback(msg)
            except Exception as e:
                print(f"Error in subscriber callback for topic '{self._topic}': {e}")

        self._subscriber = self._session.declare_subscriber(self._topic, listener)

        # Declare liveliness token for graph discovery
        self._lv_token = self._session.liveliness().declare_token(liveliness_key)

    def latest(self) -> Message | None:
        """Get the most recent message received.

        Returns:
            Latest protobuf message or None if nothing received yet.
        """
        with self._lock:
            if self._latest_msg is None:
                print(f'Warning: No messages received on topic "{self._topic}" yet.')
            return self._latest_msg

    def close(self) -> None:
        """Close the subscriber and release resources."""
        self._lv_token.undeclare()
        self._subscriber.undeclare()


class ServiceServer:
    """Service server for handling request-response interactions.

    Automatically registers with the graph via liveliness tokens.
    """

    def __init__(
        self,
        context: Context,
        liveliness_key: str,
        service: str,
        service_type: type[Message],
        callback: Callable[[Message], Message],
    ):
        """Create a service server.

        Args:
            context: Context containing the Zenoh session
            liveliness_key: Liveliness key for graph discovery
            service: Service name (e.g., "compute_trajectory")
            service_type: Protobuf service message type with nested Request and Response
            callback: Function that takes request and returns response
        """
        self._service = clean_topic_name(service)
        self._request_type = service_type.Request
        self._response_type = service_type.Response
        self._callback = callback

        self._session = context.session

        def queryable_handler(query):
            try:
                # Extract and validate request type
                if query.attachment is None:
                    raise MessageTypeMismatchError(
                        f"Received service request without type metadata on '{self._service}'. "
                        "Ensure client includes type information.",
                    )
                actual_request_type = query.attachment.to_bytes().decode()

                # Deserialize request with type validation
                request = deserialize(
                    query.payload, self._request_type, actual_request_type
                )

                # Call user callback
                response = self._callback(request)

                # Validate response type
                if not isinstance(response, self._response_type):
                    raise TypeError(
                        f"Callback must return {self._response_type.__name__}, "
                        f"got {type(response).__name__}",
                    )

                # Send response with type metadata
                response_type_name = get_type_name(response)
                response_attachment = zenoh.ZBytes(response_type_name.encode())
                query.reply(
                    self._service,
                    serialize(response),
                    attachment=response_attachment,
                )

            except Exception as e:
                # Send error response
                error_msg = f"Service error: {e}"
                print(f"Error in service '{self._service}': {error_msg}")
                query.reply_err(zenoh.ZBytes(error_msg.encode()))

        self._queryable = self._session.declare_queryable(
            self._service, queryable_handler
        )

        # Declare liveliness token for graph discovery
        self._lv_token = self._session.liveliness().declare_token(liveliness_key)

    def close(self) -> None:
        """Close the service server and release resources."""
        self._lv_token.undeclare()
        self._queryable.undeclare()


class ServiceFuture:
    """Future for async service calls with cancellation support.

    Returned by ServiceClient.call_async(). Provides methods to wait for
    results, check completion status, and cancel pending calls.
    """

    def __init__(self):
        self._result: Message | None = None
        self._exception: BaseException | None = None
        self._done = threading.Event()
        self._cancellation_token = zenoh.CancellationToken()

    @property
    def cancellation_token(self) -> zenoh.CancellationToken:
        """Cancellation token for this call."""
        return self._cancellation_token

    def set_result(self, result: Message) -> None:
        """Set the result and mark as done."""
        self._result = result
        self._done.set()

    def set_exception(self, exception: BaseException) -> None:
        """Set an exception and mark as done."""
        self._exception = exception
        self._done.set()

    def result(self, timeout: float | None = None) -> Message:
        """Wait for and return the result.

        Args:
            timeout: Maximum seconds to wait, or None for no limit

        Returns:
            The response message

        Raises:
            TimeoutError: If timeout expires before result is ready
            ServiceCancelled: If the call was cancelled
            ServiceError: If the service returned an error
        """
        if not self._done.wait(timeout):
            raise TimeoutError("Timed out waiting for service result")
        if self._exception is not None:
            raise self._exception
        return self._result

    def done(self) -> bool:
        """Return True if completed (success, error, or cancelled)."""
        return self._done.is_set()

    def cancel(self) -> bool:
        """Cancel the call.

        Returns:
            True if cancellation was requested, False if already done
        """
        if self._done.is_set():
            return False
        self._cancellation_token.cancel()
        return True

    def cancelled(self) -> bool:
        """Return True if the call was cancelled."""
        return self._cancellation_token.is_cancelled


class ServiceClient:
    """Service client for calling services.

    Automatically registers with the graph via liveliness tokens.
    Uses a shared thread pool for async calls.
    """

    _executor: ThreadPoolExecutor | None = None
    _executor_lock = threading.Lock()

    @classmethod
    def _get_executor(cls) -> ThreadPoolExecutor:
        """Get or create the shared executor for async calls."""
        with cls._executor_lock:
            if cls._executor is None:
                cls._executor = ThreadPoolExecutor(
                    max_workers=4, thread_name_prefix="svc"
                )
        return cls._executor

    def __init__(
        self,
        context: Context,
        liveliness_key: str,
        service: str,
        service_type: type[Message],
    ):
        """Create a service client.

        Args:
            context: Context containing the Zenoh session
            liveliness_key: Liveliness key for graph discovery
            service: Service name
            service_type: Protobuf service message type with nested Request and Response
        """
        self._service = clean_topic_name(service)
        self._request_type = service_type.Request
        self._response_type = service_type.Response

        self._session = context.session

        # TODO: Uncomment when querier is supports passing a timeout in get()
        # Declare querier for making service calls
        # self._querier = self._session.declare_querier(service)

        # Declare liveliness token for graph discovery
        self._lv_token = self._session.liveliness().declare_token(liveliness_key)

    def call(
        self,
        request: Message,
        timeout: float | None = None,
    ) -> Message:
        """Call the service synchronously.

        Args:
            request: Protobuf request message
            timeout: Timeout for call in seconds (default: None, meaning no timeout)

        Returns:
            Protobuf response message

        Raises:
            TypeError: If request is not an instance of the expected type
            TimeoutError: If no response within timeout
            ServiceError: If service returns error
        """
        if not isinstance(request, self._request_type):
            raise TypeError(
                f"Expected request of type {self._request_type.__name__}, "
                f"got {type(request).__name__}",
            )

        # Send request with type metadata
        request_type_name = get_type_name(request)
        request_attachment = zenoh.ZBytes(request_type_name.encode())

        # Use the querier to make the call
        replies = self._session.get(
            self._service,
            payload=serialize(request),
            attachment=request_attachment,
            timeout=timeout,
        )

        for reply in replies:
            if reply.ok is None:
                raise ServiceError(
                    f"Service '{self._service}' returned error: {reply.err.payload.to_string()}",
                )
            # Extract and validate response type
            if reply.ok.attachment is None:
                raise MessageTypeMismatchError(
                    f"Received service response without type metadata from '{self._service}'. "
                    "Ensure server includes type information.",
                )
            actual_response_type = reply.ok.attachment.to_bytes().decode()

            # Deserialize response with type validation
            response = deserialize(
                reply.ok.payload,
                self._response_type,
                actual_response_type,
            )
            return response

        # No replies received
        raise TimeoutError(
            f"Service '{self._service}' did not respond within {timeout} seconds",
        )

    def call_async(
        self, request: Message, timeout: float | None = None
    ) -> ServiceFuture:
        """Call the service asynchronously with cancellation support.

        Args:
            request: Protobuf request message
            timeout: Timeout in seconds for the call (default: None, meaning no timeout)

        Returns:
            ServiceFuture to track the call and cancel if needed

        Raises:
            TypeError: If request is not an instance of the expected type
        """
        if not isinstance(request, self._request_type):
            raise TypeError(
                f"Expected request of type {self._request_type.__name__}, "
                f"got {type(request).__name__}",
            )

        future = ServiceFuture()
        ServiceClient._get_executor().submit(
            self._execute_async, request, timeout, future
        )
        return future

    def _execute_async(
        self, request: Message, timeout: float, future: ServiceFuture
    ) -> None:
        """Execute async call with cancellation support (internal)."""
        try:
            request_type_name = get_type_name(request)
            request_attachment = zenoh.ZBytes(request_type_name.encode())

            replies = self._session.get(
                self._service,
                payload=serialize(request),
                attachment=request_attachment,
                timeout=timeout,
                cancellation_token=future.cancellation_token,
            )

            for reply in replies:
                if future.cancellation_token.is_cancelled:
                    future.set_exception(
                        ServiceCancelled(
                            f"Service call to '{self._service}' was cancelled"
                        )
                    )
                    return

                if reply.ok is None:
                    future.set_exception(
                        ServiceError(
                            f"Service '{self._service}' returned error: {reply.err.payload.to_string()}"
                        )
                    )
                    return

                if reply.ok.attachment is None:
                    future.set_exception(
                        MessageTypeMismatchError(
                            f"Received service response without type metadata from '{self._service}'. "
                            "Ensure server includes type information."
                        )
                    )
                    return

                actual_response_type = reply.ok.attachment.to_bytes().decode()
                result = deserialize(
                    reply.ok.payload,
                    self._response_type,
                    actual_response_type,
                )
                future.set_result(result)
                return

            if future.cancellation_token.is_cancelled:
                future.set_exception(
                    ServiceCancelled(f"Service call to '{self._service}' was cancelled")
                )
            else:
                future.set_exception(
                    TimeoutError(
                        f"Service '{self._service}' did not respond within {timeout} seconds"
                    )
                )
        except Exception as e:
            if future.cancellation_token.is_cancelled:
                future.set_exception(
                    ServiceCancelled(f"Service call to '{self._service}' was cancelled")
                )
            else:
                future.set_exception(e)

    def close(self) -> None:
        """Close the service client and release resources."""
        # TODO: Uncomment when querier is supports passing a timeout in get()
        # self._querier.undeclare()
        self._lv_token.undeclare()


def _generate_goal_id() -> str:
    """Generate a unique goal ID using UUID4."""
    return str(uuid.uuid4())


class ServerGoalHandle:
    """Server-side handle for managing a single goal's lifecycle.

    Provides methods to update goal status, publish feedback, and set
    the final result. The handle tracks whether cancellation has been
    requested (either by client or by preemption from a new goal).
    """

    def __init__(
        self,
        goal_id: str,
        goal: Message,
        publish_feedback_fn: Callable[[str, Message], None],
        publish_result_fn: Callable[[str, GoalStatus, Message], None],
    ):
        """Create a server goal handle.

        Args:
            goal_id: Unique identifier for this goal
            goal: The goal message from the client
            publish_feedback_fn: Callback to publish feedback
            publish_result_fn: Callback to publish result
        """
        self._goal_id = goal_id
        self._goal = goal
        self._publish_feedback_fn = publish_feedback_fn
        self._publish_result_fn = publish_result_fn
        self._status = GoalStatus.PENDING
        self._cancel_requested = False
        self._lock = threading.Lock()

    @property
    def goal_id(self) -> str:
        """Get the goal ID."""
        return self._goal_id

    @property
    def goal(self) -> Message:
        """Get the goal message."""
        return self._goal

    @property
    def status(self) -> GoalStatus:
        """Get the current goal status."""
        with self._lock:
            return self._status

    @property
    def cancel_requested(self) -> bool:
        """Check if cancellation has been requested.

        Execute callbacks should check this periodically and cleanly
        terminate if True.
        """
        with self._lock:
            return self._cancel_requested

    def request_cancel(self) -> bool:
        """Request cancellation of this goal.

        Returns:
            True if the goal can be canceled, False if already terminal.
        """
        with self._lock:
            if self._status.is_terminal():
                return False
            self._cancel_requested = True
            if self._status == GoalStatus.EXECUTING:
                self._status = GoalStatus.CANCELING
            return True

    def _transition_to(self, target: GoalStatus) -> bool:
        """Attempt state transition. Returns True if successful."""
        with self._lock:
            if not self._status.can_transition_to(target):
                return False
            self._status = target
            return True

    def execute(self) -> None:
        """Transition the goal to EXECUTING state.

        Should be called at the start of the execute callback.
        """
        self._transition_to(GoalStatus.EXECUTING)

    def publish_feedback(self, feedback: Message) -> None:
        """Publish feedback for this goal.

        Args:
            feedback: Feedback message to send to clients
        """
        self._publish_feedback_fn(self._goal_id, feedback)

    def succeed(self, result: Message) -> None:
        """Mark the goal as successfully completed.

        Args:
            result: Result message to send to clients
        """
        if self._transition_to(GoalStatus.SUCCEEDED):
            self._publish_result_fn(self._goal_id, GoalStatus.SUCCEEDED, result)

    def abort(self, result: Message) -> None:
        """Mark the goal as aborted (server-side failure).

        Args:
            result: Result message to send to clients
        """
        if self._transition_to(GoalStatus.ABORTED):
            self._publish_result_fn(self._goal_id, GoalStatus.ABORTED, result)

    def cancel(self, result: Message) -> None:
        """Mark the goal as canceled.

        Args:
            result: Result message to send to clients
        """
        if self._transition_to(GoalStatus.CANCELED):
            self._publish_result_fn(self._goal_id, GoalStatus.CANCELED, result)


class ActionServer:
    """Action server for handling long-running goals with feedback.

    Implements a single-goal policy: only one goal can be active at a time.
    When a new goal arrives, the current goal is automatically preempted.
    The execute callback runs in a thread pool executor.
    """

    def __init__(
        self,
        context: Context,
        liveliness_key: str,
        action_name: str,
        action_type: type[Message],
        execute_callback: Callable[[ServerGoalHandle], None],
    ):
        """Create an action server.

        Args:
            context: Context containing the Zenoh session
            liveliness_key: Liveliness key for graph discovery
            action_name: Action name (e.g., "navigate")
            action_type: Protobuf action type with nested Goal, Result, Feedback
            execute_callback: Function called for each goal (runs in executor thread)
        """
        self._action_name = clean_topic_name(action_name)
        self._goal_type = action_type.Goal
        self._result_type = action_type.Result
        self._feedback_type = action_type.Feedback
        self._execute_callback = execute_callback
        self._session = context.session

        self._current_goal: ServerGoalHandle | None = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="action")
        self._lock = threading.Lock()

        # Declare publishers for feedback and result
        self._feedback_pub = self._session.declare_publisher(
            f"{self._action_name}/feedback"
        )
        self._result_pub = self._session.declare_publisher(
            f"{self._action_name}/result"
        )

        # Declare queryables for goal and cancel
        self._goal_queryable = self._session.declare_queryable(
            f"{self._action_name}/goal",
            self._handle_goal_request,
        )
        self._cancel_queryable = self._session.declare_queryable(
            f"{self._action_name}/cancel",
            self._handle_cancel_request,
        )

        # Declare liveliness token for graph discovery
        self._lv_token = self._session.liveliness().declare_token(liveliness_key)

    def _handle_goal_request(self, query: zenoh.Query) -> None:
        """Handle incoming goal requests."""
        try:
            # Validate request has type metadata
            if query.attachment is None:
                query.reply_err(zenoh.ZBytes(b"Missing type metadata"))
                return

            actual_type_name = query.attachment.to_bytes().decode()
            expected_type_name = get_type_name(self._goal_type)

            if actual_type_name != expected_type_name:
                query.reply_err(
                    zenoh.ZBytes(
                        f"Type mismatch: expected {expected_type_name}, got {actual_type_name}".encode()
                    )
                )
                return

            # Deserialize goal
            goal = self._goal_type()
            goal.ParseFromString(query.payload.to_bytes())

            # Generate goal ID
            goal_id = _generate_goal_id()

            with self._lock:
                # Preempt current goal if active
                if self._current_goal is not None:
                    self._current_goal.request_cancel()

                # Create new goal handle
                goal_handle = ServerGoalHandle(
                    goal_id,
                    goal,
                    self._publish_feedback,
                    self._publish_result,
                )
                self._current_goal = goal_handle

                # Submit to executor
                self._executor.submit(self._execute_goal, goal_handle)

            # Reply with goal ID (accepted)
            query.reply(
                f"{self._action_name}/goal",
                zenoh.ZBytes(goal_id.encode()),
                attachment=zenoh.ZBytes(b"accepted"),
            )

        except Exception as e:
            print(f"Error handling goal request: {e}")
            query.reply_err(zenoh.ZBytes(f"Error: {e}".encode()))

    def _handle_cancel_request(self, query: zenoh.Query) -> None:
        """Handle cancel requests."""
        try:
            goal_id = query.payload.to_bytes().decode()

            with self._lock:
                if self._current_goal is None or self._current_goal.goal_id != goal_id:
                    query.reply_err(
                        zenoh.ZBytes(b"Goal not found or already completed")
                    )
                    return

                success = self._current_goal.request_cancel()

            if success:
                query.reply(
                    f"{self._action_name}/cancel",
                    zenoh.ZBytes(b""),
                    attachment=zenoh.ZBytes(b"ok"),
                )
            else:
                query.reply_err(zenoh.ZBytes(b"Goal already in terminal state"))

        except Exception as e:
            print(f"Error handling cancel request: {e}")
            query.reply_err(zenoh.ZBytes(f"Error: {e}".encode()))

    def _execute_goal(self, goal_handle: ServerGoalHandle) -> None:
        """Execute a goal in the executor thread."""
        try:
            self._execute_callback(goal_handle)

            # If callback didn't set a terminal state, abort
            if not goal_handle.status.is_terminal():
                print(
                    f"Warning: Execute callback did not set terminal state, aborting goal {goal_handle.goal_id}"
                )
                goal_handle.abort(self._result_type())

        except Exception as e:
            print(f"Error in execute callback: {e}")
            try:
                goal_handle.abort(self._result_type())
            except Exception as inner_e:
                print(f"Failed to abort goal {goal_handle.goal_id}: {inner_e}")

    def _publish_feedback(self, goal_id: str, feedback: Message) -> None:
        """Publish feedback for a goal."""
        if not isinstance(feedback, self._feedback_type):
            raise TypeError(
                f"Expected feedback of type {self._feedback_type.__name__}, "
                f"got {type(feedback).__name__}"
            )

        type_name = get_type_name(feedback)
        attachment = zenoh.ZBytes(f"{type_name}|{goal_id}".encode())
        self._feedback_pub.put(serialize(feedback), attachment=attachment)

    def _publish_result(
        self, goal_id: str, status: GoalStatus, result: Message
    ) -> None:
        """Publish final result for a goal."""
        if not isinstance(result, self._result_type):
            raise TypeError(
                f"Expected result of type {self._result_type.__name__}, "
                f"got {type(result).__name__}"
            )

        type_name = get_type_name(result)
        attachment = zenoh.ZBytes(f"{type_name}|{goal_id}|{status}".encode())
        self._result_pub.put(serialize(result), attachment=attachment)

    def close(self, timeout: float = 5.0) -> None:
        """Close the action server and release resources.

        Args:
            timeout: Maximum time to wait for active goal to complete (seconds)
        """
        # Signal cancellation to active goal
        with self._lock:
            if self._current_goal is not None:
                self._current_goal.request_cancel()

        # Wait for executor to finish with timeout
        self._executor.shutdown(wait=True, cancel_futures=False)

        # Clean up Zenoh resources
        self._lv_token.undeclare()
        self._goal_queryable.undeclare()
        self._cancel_queryable.undeclare()
        self._feedback_pub.undeclare()
        self._result_pub.undeclare()


class ClientGoalHandle:
    """Client-side handle for tracking a submitted goal.

    Provides methods to check status, get results, and cancel the goal.
    """

    def __init__(
        self,
        goal_id: str,
        action_client: "ActionClient",
    ):
        """Create a client goal handle.

        Args:
            goal_id: Unique identifier for this goal
            action_client: Reference to the parent action client
        """
        self._goal_id = goal_id
        self._action_client = action_client
        self._status = GoalStatus.PENDING
        self._result: Message | None = None
        self._result_received = threading.Event()
        self._lock = threading.Lock()

    @property
    def goal_id(self) -> str:
        """Get the goal ID."""
        return self._goal_id

    @property
    def status(self) -> GoalStatus:
        """Get the current goal status."""
        with self._lock:
            return self._status

    @property
    def result(self) -> Message | None:
        """Get the result message (None if not yet received)."""
        with self._lock:
            return self._result

    def _update_status(self, status: GoalStatus, result: Message | None = None) -> None:
        """Update goal status (internal use)."""
        with self._lock:
            self._status = status
            if result is not None:
                self._result = result
                self._result_received.set()

    def cancel(self, timeout: float = 5.0) -> bool:
        """Request cancellation of this goal.

        Args:
            timeout: Timeout for cancel request in seconds

        Returns:
            True if cancel was acknowledged, False otherwise
        """
        return self._action_client._cancel_goal(self._goal_id, timeout)

    def get_result(self, timeout: float | None = None) -> Message:
        """Wait for and return the result.

        Args:
            timeout: Maximum time to wait (None for infinite)

        Returns:
            The result message

        Raises:
            TimeoutError: If timeout expires before result received
            ActionError: If the goal was aborted or canceled
        """
        if not self._result_received.wait(timeout):
            raise TimeoutError(f"Timed out waiting for result on goal {self._goal_id}")

        with self._lock:
            if self._status == GoalStatus.ABORTED:
                raise ActionError(f"Goal {self._goal_id} was aborted")
            if self._status == GoalStatus.CANCELED:
                raise ActionError(f"Goal {self._goal_id} was canceled")
            if self._result is None:
                raise ActionError(f"Goal {self._goal_id} completed without result")
            return self._result

    def wait_for_result(self, timeout: float | None = None) -> bool:
        """Wait for the result to be received.

        Args:
            timeout: Maximum time to wait (None for infinite)

        Returns:
            True if result received, False if timeout
        """
        return self._result_received.wait(timeout)


class ActionClient:
    """Action client for sending goals and tracking their progress.

    Sends goals to an action server, receives feedback during execution,
    and gets the final result. Supports cancellation of active goals.
    """

    def __init__(
        self,
        context: Context,
        liveliness_key: str,
        action_name: str,
        action_type: type[Message],
    ):
        """Create an action client.

        Args:
            context: Context containing the Zenoh session
            liveliness_key: Liveliness key for graph discovery
            action_name: Action name (e.g., "navigate")
            action_type: Protobuf action type with nested Goal, Result, Feedback
        """
        self._action_name = clean_topic_name(action_name)
        self._goal_type = action_type.Goal
        self._result_type = action_type.Result
        self._feedback_type = action_type.Feedback
        self._session = context.session

        self._goals: dict[str, ClientGoalHandle] = {}
        self._feedback_callbacks: dict[str, Callable[[Message], None]] = {}
        self._lock = threading.Lock()

        # Subscribe to feedback and result
        self._feedback_sub = self._session.declare_subscriber(
            f"{self._action_name}/feedback",
            self._handle_feedback,
        )
        self._result_sub = self._session.declare_subscriber(
            f"{self._action_name}/result",
            self._handle_result,
        )

        # Declare liveliness token for graph discovery
        self._lv_token = self._session.liveliness().declare_token(liveliness_key)

    def _handle_feedback(self, sample: zenoh.Sample) -> None:
        """Handle incoming feedback messages."""
        try:
            if sample.attachment is None:
                return

            # Parse attachment: type|goal_id
            attachment_str = sample.attachment.to_bytes().decode()
            parts = attachment_str.split("|")
            if len(parts) != 2:
                return

            type_name, goal_id = parts

            with self._lock:
                if goal_id not in self._goals:
                    return
                callback = self._feedback_callbacks.get(goal_id)

            if callback is not None:
                # Deserialize feedback
                feedback = deserialize(sample.payload, self._feedback_type, type_name)
                callback(feedback)

        except Exception as e:
            print(f"Error handling feedback: {e}")

    def _handle_result(self, sample: zenoh.Sample) -> None:
        """Handle incoming result messages."""
        try:
            if sample.attachment is None:
                return

            # Parse attachment: type|goal_id|status
            attachment_str = sample.attachment.to_bytes().decode()
            parts = attachment_str.split("|")
            if len(parts) != 3:
                return

            type_name, goal_id, status_str = parts

            with self._lock:
                if goal_id not in self._goals:
                    return
                goal_handle = self._goals[goal_id]

            # Deserialize result
            result = deserialize(sample.payload, self._result_type, type_name)
            status = GoalStatus(status_str)
            goal_handle._update_status(status, result)

        except Exception as e:
            print(f"Error handling result: {e}")

    def send_goal(
        self,
        goal: Message,
        feedback_callback: Callable[[Message], None] | None = None,
        timeout: float = 5.0,
    ) -> ClientGoalHandle:
        """Send a goal to the action server.

        Args:
            goal: Goal message to send
            feedback_callback: Optional callback for feedback messages
            timeout: Timeout for goal acceptance in seconds

        Returns:
            ClientGoalHandle for tracking the goal

        Raises:
            TypeError: If goal is wrong type
            TimeoutError: If server doesn't respond
            ActionError: If goal is rejected
        """
        if not isinstance(goal, self._goal_type):
            raise TypeError(
                f"Expected goal of type {self._goal_type.__name__}, "
                f"got {type(goal).__name__}"
            )

        # Send goal request
        type_name = get_type_name(goal)
        replies = self._session.get(
            f"{self._action_name}/goal",
            payload=serialize(goal),
            attachment=zenoh.ZBytes(type_name.encode()),
            timeout=timeout,
        )

        for reply in replies:
            if reply.ok is None:
                error_msg = (
                    reply.err.payload.to_string() if reply.err else "Unknown error"
                )
                raise ActionError(f"Goal rejected: {error_msg}")

            # Check attachment for acceptance status
            if (
                reply.ok.attachment is None
                or reply.ok.attachment.to_bytes() != b"accepted"
            ):
                attachment_str = (
                    reply.ok.attachment.to_bytes().decode()
                    if reply.ok.attachment
                    else "no attachment"
                )
                raise ActionError(f"Goal not accepted: {attachment_str}")

            # Get goal ID from payload
            goal_id = reply.ok.payload.to_bytes().decode()

            # Create and track goal handle
            goal_handle = ClientGoalHandle(goal_id, self)
            with self._lock:
                self._goals[goal_id] = goal_handle
                if feedback_callback is not None:
                    self._feedback_callbacks[goal_id] = feedback_callback

            return goal_handle

        raise TimeoutError(
            f"Action server '{self._action_name}' did not respond within {timeout} seconds"
        )

    def _cancel_goal(self, goal_id: str, timeout: float) -> bool:
        """Send a cancel request for a goal."""
        try:
            replies = self._session.get(
                f"{self._action_name}/cancel",
                payload=zenoh.ZBytes(goal_id.encode()),
                attachment=zenoh.ZBytes(b"cancel"),
                timeout=timeout,
            )

            for reply in replies:
                if reply.ok is not None:
                    return (
                        reply.ok.attachment is not None
                        and reply.ok.attachment.to_bytes() == b"ok"
                    )
                return False

            return False

        except Exception as e:
            print(f"Error canceling goal: {e}")
            return False

    def close(self) -> None:
        """Close the action client and release resources."""
        self._lv_token.undeclare()
        self._feedback_sub.undeclare()
        self._result_sub.undeclare()


class Graph:
    """Graph for discovering and tracking entities in the ZRM network.

    The Graph uses Zenoh's liveliness feature to automatically discover
    publishers, subscribers, services, and clients across the network.
    """

    def __init__(self, session: zenoh.Session, domain_id: int = DOMAIN_ID) -> None:
        """Create a graph instance.

        Args:
            session: Zenoh session to use
            domain_id: Domain ID to monitor (default: DOMAIN_ID constant = 0)
        """
        self._data = GraphData()
        self._condition = threading.Condition()
        self._session = session

        # Subscribe to liveliness tokens with history to get existing entities
        def liveliness_callback(sample: zenoh.Sample) -> None:
            ke = str(sample.key_expr)
            with self._condition:
                if sample.kind == zenoh.SampleKind.PUT:
                    self._data.insert(ke)
                elif sample.kind == zenoh.SampleKind.DELETE:
                    self._data.remove(ke)
                self._condition.notify_all()

        key_expr = f"{ADMIN_SPACE}/{domain_id}/**"
        # Explicitly call discovery on initialization
        replies = self._session.liveliness().get(key_expr, timeout=1.0)
        for reply in replies:
            try:
                liveliness_callback(reply.ok)
            except Exception as e:
                print(
                    f"Error processing liveliness sample (ERROR: '{reply.err.payload.to_string()}'): {e}"
                )
        self._subscriber = self._session.liveliness().declare_subscriber(
            key_expr,
            liveliness_callback,
            # TODO: Do we need history? Enabling it causes duplicate entries currently since we manually fetch existing tokens above.
            # history=True,
        )

    def count(self, kind: EntityKind, topic: str) -> int:
        """Count entities of a given kind on a topic.

        Args:
            kind: Entity kind (must be PUBLISHER, SUBSCRIBER, SERVICE, or CLIENT)
            topic: Topic or service name

        Returns:
            Number of matching entities
        """
        if kind == EntityKind.NODE:
            raise ValueError("Use count_by_node() for node entities")

        total = 0

        def counter(entity: ParsedEntity) -> None:
            nonlocal total
            if entity.kind == kind:
                total += 1

        with self._condition:
            if kind in (EntityKind.PUBLISHER, EntityKind.SUBSCRIBER):
                self._data.visit_by_topic(topic, counter)
            elif kind in (EntityKind.SERVICE, EntityKind.CLIENT):
                self._data.visit_by_service(topic, counter)

        return total

    def get_entities_by_topic(self, kind: EntityKind, topic: str) -> list[ParsedEntity]:
        """Get all entities of a given kind on a topic.

        Args:
            kind: Entity kind (PUBLISHER or SUBSCRIBER)
            topic: Topic name

        Returns:
            List of matching entities
        """
        if kind not in (EntityKind.PUBLISHER, EntityKind.SUBSCRIBER):
            raise ValueError("kind must be PUBLISHER or SUBSCRIBER")

        results: list[ParsedEntity] = []

        def collector(entity: ParsedEntity) -> None:
            if entity.kind == kind:
                results.append(entity)

        with self._condition:
            self._data.visit_by_topic(topic, collector)

        return results

    def get_entities_by_service(
        self, kind: EntityKind, service: str
    ) -> list[ParsedEntity]:
        """Get all entities of a given kind for a service.

        Args:
            kind: Entity kind (SERVICE or CLIENT)
            service: Service name

        Returns:
            List of matching entities
        """
        if kind not in (EntityKind.SERVICE, EntityKind.CLIENT):
            raise ValueError("kind must be SERVICE or CLIENT")

        results: list[ParsedEntity] = []

        def collector(entity: ParsedEntity) -> None:
            if entity.kind == kind:
                results.append(entity)

        with self._condition:
            self._data.visit_by_service(service, collector)

        return results

    def get_entities_by_node(
        self, kind: EntityKind, node_name: str
    ) -> list[ParsedEntity]:
        """Get all endpoint entities of a given kind for a node.

        Args:
            kind: Entity kind (must not be NODE)
            node_name: Node name

        Returns:
            List of matching endpoint entities
        """
        if kind == EntityKind.NODE:
            raise ValueError("kind must not be NODE")

        results: list[ParsedEntity] = []

        def collector(entity: ParsedEntity) -> None:
            if entity.kind == kind:
                results.append(entity)

        with self._condition:
            self._data.visit_by_node(node_name, collector)

        return results

    def get_node_names(self) -> list[str]:
        """Get all node names in the network.

        Returns:
            List of node names
        """
        node_names: set[str] = set()

        with self._condition:
            for entity in self._data._entities.values():
                node_names.add(entity.node_name)

        return list(node_names)

    def get_topic_names_and_types(self) -> list[tuple[str, str]]:
        """Get all topic names and their types in the network.

        Returns:
            List of (topic_name, type_name) tuples
        """
        results: dict[str, str] = {}

        with self._condition:
            for topic_name, keys in self._data._by_topic.items():
                for key in keys:
                    entity = self._data._entities[key]
                    if entity.type_name is not None:
                        results[topic_name] = entity.type_name
                        break  # One type per topic

        return list(results.items())

    def get_service_names_and_types(self) -> list[tuple[str, str]]:
        """Get all service names and their types in the network.

        Returns:
            List of (service_name, type_name) tuples
        """
        results: dict[str, str] = {}

        with self._condition:
            for service_name, keys in self._data._by_service.items():
                for key in keys:
                    entity = self._data._entities[key]
                    if entity.type_name is not None:
                        results[service_name] = entity.type_name
                        break  # One type per service

        return list(results.items())

    def get_action_names_and_types(self) -> list[tuple[str, str]]:
        """Get all action names and their types in the network.

        Returns:
            List of (action_name, type_name) tuples
        """
        results: dict[str, str] = {}

        with self._condition:
            for action_name, keys in self._data._by_action.items():
                for key in keys:
                    entity = self._data._entities[key]
                    if entity.type_name is not None:
                        results[action_name] = entity.type_name
                        break  # One type per action

        return list(results.items())

    def get_entities_by_action(
        self, kind: EntityKind, action: str
    ) -> list[ParsedEntity]:
        """Get all entities of a given kind for an action.

        Args:
            kind: Entity kind (ACTION_SERVER or ACTION_CLIENT)
            action: Action name

        Returns:
            List of matching entities
        """
        if kind not in (EntityKind.ACTION_SERVER, EntityKind.ACTION_CLIENT):
            raise ValueError("kind must be ACTION_SERVER or ACTION_CLIENT")

        results: list[ParsedEntity] = []

        def collector(entity: ParsedEntity) -> None:
            if entity.kind == kind:
                results.append(entity)

        with self._condition:
            self._data.visit_by_action(action, collector)

        return results

    def get_names_and_types_by_node(
        self,
        node_name: str,
        kind: EntityKind,
    ) -> list[tuple[str, str]]:
        """Get all topic/service names and types for a given node.

        Args:
            node_name: Node name
            kind: Entity kind (PUBLISHER, SUBSCRIBER, SERVICE, or CLIENT)

        Returns:
            List of (name, type_name) tuples
        """
        if kind == EntityKind.NODE:
            raise ValueError("kind must not be NODE")

        results: list[tuple[str, str]] = []

        def collector(entity: ParsedEntity) -> None:
            if (
                entity.kind == kind
                and entity.topic is not None
                and entity.type_name is not None
            ):
                results.append((entity.topic, entity.type_name))

        with self._condition:
            self._data.visit_by_node(node_name, collector)

        return results

    def wait_for_subscribers(self, topic: str, timeout: float | None = None) -> bool:
        """Wait until at least one subscriber exists on the topic.

        Args:
            topic: Topic name
            timeout: Maximum time to wait in seconds, or None for no timeout

        Returns:
            True if the condition was met, False if timeout occurred
        """

        def predicate() -> bool:
            for key in self._data._by_topic.get(topic, []):
                if self._data._entities[key].kind == EntityKind.SUBSCRIBER:
                    return True
            return False

        with self._condition:
            return self._condition.wait_for(predicate, timeout=timeout)

    def wait_for_publishers(self, topic: str, timeout: float | None = None) -> bool:
        """Wait until at least one publisher exists on the topic.

        Args:
            topic: Topic name
            timeout: Maximum time to wait in seconds, or None for no timeout

        Returns:
            True if the condition was met, False if timeout occurred
        """

        def predicate() -> bool:
            for key in self._data._by_topic.get(topic, []):
                if self._data._entities[key].kind == EntityKind.PUBLISHER:
                    return True
            return False

        with self._condition:
            return self._condition.wait_for(predicate, timeout=timeout)

    def wait_for_service(self, service: str, timeout: float | None = None) -> bool:
        """Wait until a service server is available.

        Args:
            service: Service name
            timeout: Maximum time to wait in seconds, or None for no timeout

        Returns:
            True if the condition was met, False if timeout occurred
        """

        def predicate() -> bool:
            for key in self._data._by_service.get(service, []):
                if self._data._entities[key].kind == EntityKind.SERVICE:
                    return True
            return False

        with self._condition:
            return self._condition.wait_for(predicate, timeout=timeout)

    def wait_for_clients(self, service: str, timeout: float | None = None) -> bool:
        """Wait until at least one client exists for the service.

        Args:
            service: Service name
            timeout: Maximum time to wait in seconds, or None for no timeout

        Returns:
            True if the condition was met, False if timeout occurred
        """

        def predicate() -> bool:
            for key in self._data._by_service.get(service, []):
                if self._data._entities[key].kind == EntityKind.CLIENT:
                    return True
            return False

        with self._condition:
            return self._condition.wait_for(predicate, timeout=timeout)

    def wait_for_action_server(self, action: str, timeout: float | None = None) -> bool:
        """Wait until an action server is available.

        Args:
            action: Action name
            timeout: Maximum time to wait in seconds, or None for no timeout

        Returns:
            True if the condition was met, False if timeout occurred
        """

        def predicate() -> bool:
            for key in self._data._by_action.get(action, []):
                if self._data._entities[key].kind == EntityKind.ACTION_SERVER:
                    return True
            return False

        with self._condition:
            return self._condition.wait_for(predicate, timeout=timeout)

    def close(self) -> None:
        """Close the graph and release resources."""
        self._subscriber.undeclare()


class Node:
    """Node represents a participant in the ZRM network.

    A Node holds a name and provides factory methods for creating
    Publishers, Subscribers, Services, and Clients. It also provides graph
    discovery for the network.
    """

    def __init__(
        self,
        name: str,
        context: Context | None = None,
    ):
        """Create a new node.

        Args:
            name: Node name
            context: Context to use (defaults to global context via _get_context())
        """
        self._context = context if context is not None else _get_context()
        self._name = name

        # Declare liveliness token for node presence
        lv_key = _make_node_lv_key(
            domain_id=self._context.domain_id,
            z_id=str(self._context.session.info.zid()),
            name=name,
        )
        self._lv_token = self._context.session.liveliness().declare_token(lv_key)

        # Create graph for discovery
        self.graph = Graph(self._context.session, domain_id=self._context.domain_id)

    @property
    def name(self) -> str:
        """Get node name."""
        return self._name

    def create_publisher(self, topic: str, msg_type: type[Message]) -> "Publisher":
        """Create a publisher for this node.

        Args:
            topic: Zenoh key expression (e.g., "robot/pose" or "/robot/pose")
            msg_type: Protobuf message type

        Returns:
            Publisher instance
        """
        topic = clean_topic_name(topic)
        lv_key = _make_endpoint_lv_key(
            domain_id=self._context.domain_id,
            z_id=str(self._context.session.info.zid()),
            kind=EntityKind.PUBLISHER,
            node_name=self._name,
            topic=topic,
            type_name=get_type_name(msg_type),
        )
        return Publisher(self._context, lv_key, topic, msg_type)

    def create_subscriber(
        self,
        topic: str,
        msg_type: type[Message],
        callback: Callable[[Message], None] | None = None,
    ) -> "Subscriber":
        """Create a subscriber for this node.

        Args:
            topic: Zenoh key expression (e.g., "robot/pose" or "/robot/pose")
            msg_type: Protobuf message type
            callback: Optional callback function called on each message

        Returns:
            Subscriber instance
        """
        topic = clean_topic_name(topic)
        lv_key = _make_endpoint_lv_key(
            domain_id=self._context.domain_id,
            z_id=str(self._context.session.info.zid()),
            kind=EntityKind.SUBSCRIBER,
            node_name=self._name,
            topic=topic,
            type_name=get_type_name(msg_type),
        )
        return Subscriber(self._context, lv_key, topic, msg_type, callback)

    def create_service(
        self,
        service: str,
        service_type: type[Message],
        callback: Callable[[Message], Message],
    ) -> "ServiceServer":
        """Create a service server for this node.

        Args:
            service: Service name (e.g., "compute_trajectory" or "/compute_trajectory")
            service_type: Protobuf service message type with nested Request and Response
            callback: Function that takes request and returns response

        Returns:
            ServiceServer instance
        """
        _validate_service_type(service_type)
        service = clean_topic_name(service)
        lv_key = _make_endpoint_lv_key(
            domain_id=self._context.domain_id,
            z_id=str(self._context.session.info.zid()),
            kind=EntityKind.SERVICE,
            node_name=self._name,
            topic=service,
            type_name=get_type_name(service_type),
        )
        return ServiceServer(self._context, lv_key, service, service_type, callback)

    def create_client(
        self,
        service: str,
        service_type: type[Message],
    ) -> "ServiceClient":
        """Create a service client for this node.

        Args:
            service: Service name (e.g., "compute_trajectory" or "/compute_trajectory")
            service_type: Protobuf service message type with nested Request and Response

        Returns:
            ServiceClient instance
        """
        _validate_service_type(service_type)
        service = clean_topic_name(service)
        lv_key = _make_endpoint_lv_key(
            domain_id=self._context.domain_id,
            z_id=str(self._context.session.info.zid()),
            kind=EntityKind.CLIENT,
            node_name=self._name,
            topic=service,
            type_name=get_type_name(service_type),
        )
        return ServiceClient(self._context, lv_key, service, service_type)

    def create_action_server(
        self,
        action_name: str,
        action_type: type[Message],
        execute_callback: Callable[[ServerGoalHandle], None],
    ) -> "ActionServer":
        """Create an action server for this node.

        Args:
            action_name: Action name (e.g., "navigate")
            action_type: Protobuf action type with nested Goal, Result, and Feedback
            execute_callback: Function called for each goal (runs in separate thread).
                              Should call goal_handle.set_succeeded(), set_aborted(),
                              or set_canceled() when done.

        Returns:
            ActionServer instance
        """
        _validate_action_type(action_type)
        action_name = clean_topic_name(action_name)
        lv_key = _make_endpoint_lv_key(
            domain_id=self._context.domain_id,
            z_id=str(self._context.session.info.zid()),
            kind=EntityKind.ACTION_SERVER,
            node_name=self._name,
            topic=action_name,
            type_name=get_type_name(action_type),
        )
        return ActionServer(
            self._context, lv_key, action_name, action_type, execute_callback
        )

    def create_action_client(
        self,
        action_name: str,
        action_type: type[Message],
    ) -> "ActionClient":
        """Create an action client for this node.

        Args:
            action_name: Action name (e.g., "navigate")
            action_type: Protobuf action type with nested Goal, Result, and Feedback

        Returns:
            ActionClient instance
        """
        _validate_action_type(action_type)
        action_name = clean_topic_name(action_name)
        lv_key = _make_endpoint_lv_key(
            domain_id=self._context.domain_id,
            z_id=str(self._context.session.info.zid()),
            kind=EntityKind.ACTION_CLIENT,
            node_name=self._name,
            topic=action_name,
            type_name=get_type_name(action_type),
        )
        return ActionClient(self._context, lv_key, action_name, action_type)

    def close(self) -> None:
        """Close the node and release all resources."""
        self._lv_token.undeclare()
        self.graph.close()


def init(config: zenoh.Config | None = None, domain_id: int = DOMAIN_ID) -> None:
    """Initialize ZRM with a global context.

    If already initialized, this is a no-op (idempotent).

    Configuration priority (first match wins):
        1. Explicit config argument
        2. ZRM_CONFIG_FILE environment variable (path to JSON5 file)
        3. ZRM_CONFIG environment variable (inline JSON5 string)
        4. ZENOH_CONFIG environment variable (Zenoh's native config file path)
        5. Default zenoh.Config()

    Args:
        config: Optional Zenoh configuration. If None, environment variables
                are checked before falling back to default.
        domain_id: Domain ID for the context (default: DOMAIN_ID constant = 0)
    """
    global _global_context
    with _context_lock:
        if _global_context is None:
            _global_context = Context(config, domain_id)


def shutdown() -> None:
    """Shutdown ZRM and close the global context."""
    global _global_context
    with _context_lock:
        if _global_context is not None:
            _global_context.close()
            _global_context = None
