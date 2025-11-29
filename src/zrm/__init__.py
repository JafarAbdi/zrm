"""ZRM: Minimal Zenoh-based communication middleware with ROS-like API."""

from __future__ import annotations

import pathlib
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass
import enum

import zenoh
from google.protobuf.message import Message

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
    "InvalidTopicName",
    "MessageTypeMismatchError",
    "Node",
    "Publisher",
    "ServiceClient",
    "ServiceError",
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


# Global context management
_global_context: "Context | None" = None
_context_lock = threading.Lock()


class Context:
    """Context holds the Zenoh session and domain configuration."""

    def __init__(self, config: zenoh.Config | None = None, domain_id: int = DOMAIN_ID):
        """Create a new context.

        Args:
            config: Optional Zenoh configuration (defaults to zenoh.Config())
            domain_id: Domain ID for this context (default: DOMAIN_ID constant = 0)
        """
        zenoh.init_log_from_env_or("error")
        self._session = zenoh.open(config if config is not None else zenoh.Config())
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


class EntityKind(StrEnum):
    """Kind of entity in the graph."""

    NODE = "NN"
    PUBLISHER = "MP"
    SUBSCRIBER = "MS"
    SERVICE = "SS"
    CLIENT = "SC"


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

        # Index by topic or service for endpoints
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

    def remove(self, ke: str) -> None:
        """Remove a liveliness key and rebuild indexes."""
        if ke not in self._entities:
            return

        # Remove from entities dict
        del self._entities[ke]

        # Rebuild all indexes from scratch (simpler and correct)
        self._by_topic.clear()
        self._by_service.clear()
        self._by_node.clear()

        for key, entity in self._entities.items():
            # Index by node
            if entity.node_name not in self._by_node:
                self._by_node[entity.node_name] = []
            self._by_node[entity.node_name].append(key)

            # Index by topic or service for endpoints
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
        identifier: Type identifier like 'zrm/msgs/geometry/Point' or 'zrm/srvs/std/Trigger.Request'

    Returns:
        Protobuf message class

    Examples:
        >>> Point = get_message_type('zrm/msgs/geometry/Point')
        >>> point = Point(x=1.0, y=2.0, z=3.0)
        >>> TriggerRequest = get_message_type('zrm/srvs/std/Trigger.Request')
    """
    parts = identifier.split("/")
    if len(parts) != 4:
        raise ValueError(
            f"Invalid identifier format: {identifier}. Expected 'package/category/module/Type'"
        )

    package, category, module_name, type_path = parts

    # Validate category
    if category not in ("msgs", "srvs"):
        raise ValueError(f"Category must be 'msgs' or 'srvs', got '{category}'")

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


class ServiceClient:
    """Service client for calling services.

    Automatically registers with the graph via liveliness tokens.
    """

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
        timeout: float = 5.0,
    ) -> Message:
        """Call the service synchronously.

        Args:
            request: Protobuf request message
            timeout: Timeout for call in seconds (default: 5.0)

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

    def close(self) -> None:
        """Close the service client and release resources."""
        # TODO: Uncomment when querier is supports passing a timeout in get()
        # self._querier.undeclare()
        self._lv_token.undeclare()


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
        self._domain_id = domain_id
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

    def close(self) -> None:
        """Close the node and release all resources."""
        self._lv_token.undeclare()
        self.graph.close()


def init(config: zenoh.Config | None = None, domain_id: int = DOMAIN_ID) -> None:
    """Initialize ZRM with a global context.

    If already initialized, this is a no-op (idempotent).

    Args:
        config: Optional Zenoh configuration (defaults to zenoh.Config())
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
