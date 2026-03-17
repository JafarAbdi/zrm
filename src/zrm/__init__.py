"""ZRM: Minimal Zenoh-based communication middleware with ROS-like API."""

from __future__ import annotations

import enum
import os
import pathlib
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass

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


import zenoh
from google.protobuf.message import Message


DOMAIN_DEFAULT = 0
ADMIN_SPACE = "@zrm_lv"

# Environment variable names for configuration.
ZRM_CONFIG_FILE_ENV = "ZRM_CONFIG_FILE"
ZRM_CONFIG_ENV = "ZRM_CONFIG"


class MessageTypeMismatchError(TypeError):
    """Raised when message types don't match between publisher and subscriber."""


class ServiceError(Exception):
    """Raised when a service call fails."""


def _load_config_from_env() -> zenoh.Config | None:
    """Load Zenoh configuration from environment variables.

    Priority order:
        1. ZRM_CONFIG_FILE - path to a JSON5 config file
        2. ZRM_CONFIG - inline JSON5 config string
        3. ZENOH_CONFIG - Zenoh's native config file path (via Config.from_env())

    Returns:
        zenoh.Config if environment variable is set, None otherwise.

    Raises:
        FileNotFoundError: If config file path points to non-existent file.
    """
    config_file = os.environ.get(ZRM_CONFIG_FILE_ENV)
    if config_file is not None:
        path = pathlib.Path(config_file)
        if not path.exists():
            raise FileNotFoundError(
                f"{ZRM_CONFIG_FILE_ENV} points to non-existent file: {config_file}"
            )
        return zenoh.Config.from_file(config_file)

    config_str = os.environ.get(ZRM_CONFIG_ENV)
    if config_str is not None:
        return zenoh.Config.from_json5(config_str)

    if os.environ.get("ZENOH_CONFIG") is not None:
        return zenoh.Config.from_env()

    return None


class Session:
    """Wraps a Zenoh session with ZRM-specific functionality.

    Use as a context manager for automatic cleanup:

        with zrm.open() as session:
            pub = zrm.Publisher(session, "topic", MyMsg)
            ...
    """

    def __init__(
        self,
        config: zenoh.Config | None = None,
        domain: int = DOMAIN_DEFAULT,
        name: str | None = None,
    ):
        """Create a new session.

        Args:
            config: Optional Zenoh configuration. If None, checks environment
                    variables before using default.
            domain: Domain ID for isolation (default: 0).
            name: Human-readable session name for discovery. Defaults to
                  the Zenoh session ID.
        """
        zenoh.init_log_from_env_or("error")
        effective_config = config if config is not None else _load_config_from_env()
        self._zenoh = zenoh.open(
            effective_config if effective_config is not None else zenoh.Config()
        )
        self._domain = domain
        self._zid = str(self._zenoh.info.zid())
        self._name = name if name is not None else self._zid

    @property
    def zenoh(self) -> zenoh.Session:
        """The underlying Zenoh session."""
        return self._zenoh

    @property
    def domain(self) -> int:
        """Domain ID for this session."""
        return self._domain

    @property
    def zid(self) -> str:
        """Zenoh session ID."""
        return self._zid

    @property
    def name(self) -> str:
        """Human-readable session name."""
        return self._name

    def close(self) -> None:
        """Close the session and release resources."""
        self._zenoh.close()

    def __enter__(self) -> Session:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


def open(
    config: zenoh.Config | None = None,
    domain: int = DOMAIN_DEFAULT,
    name: str | None = None,
) -> Session:
    """Open a new ZRM session.

    Args:
        config: Optional Zenoh configuration.
        domain: Domain ID for isolation (default: 0).
        name: Human-readable session name for discovery.

    Returns:
        A new Session instance.
    """
    return Session(config, domain, name)


def _type_name(msg_type: type[Message]) -> str:
    """Get canonical type name for a protobuf message type.

    Args:
        msg_type: Protobuf message class.

    Returns:
        Type identifier like 'zrm/msgs/geometry/Point'.
    """
    # file.name: "zrm/msgs/geometry.proto"
    # full_name: "zrm.Point" or "zrm.Trigger.Request"
    file_path = pathlib.Path(msg_type.DESCRIPTOR.file.name)
    full_name = msg_type.DESCRIPTOR.full_name

    # Parse file path: zrm/msgs/geometry.proto -> category='msgs', module='geometry'
    parts = file_path.parts
    category = parts[1]  # 'msgs' or 'srvs'
    module = file_path.stem  # 'geometry'

    # Parse full_name: "zrm.Point" -> package='zrm', type_path='Point'
    name_parts = full_name.split(".")
    package = name_parts[0]
    type_path = ".".join(name_parts[1:])

    return f"{package}/{category}/{module}/{type_path}"


def get_message_type(identifier: str) -> type[Message]:
    """Get message type from identifier string.

    Args:
        identifier: Type identifier like 'zrm/msgs/geometry/Point',
                    'zrm/srvs/std/Trigger.Request', or 'zrm/srvs/examples/AddTwoInts'

    Returns:
        Protobuf message class.

    Raises:
        ValueError: If identifier format is invalid.
        ImportError: If module cannot be imported.
        AttributeError: If type is not found in module.

    Examples:
        >>> Point = get_message_type('zrm/msgs/geometry/Point')
        >>> point = Point(x=1.0, y=2.0, z=3.0)
        >>> TriggerRequest = get_message_type('zrm/srvs/std/Trigger.Request')
    """
    parts = identifier.split("/")
    if len(parts) != 4:
        raise ValueError(
            f"Invalid identifier format: {identifier}. "
            "Expected 'package/category/module/Type'"
        )

    package, category, module_name, type_path = parts

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


def _serialize(msg: Message) -> zenoh.ZBytes:
    """Serialize a protobuf message to ZBytes."""
    return zenoh.ZBytes(msg.SerializeToString())


def _deserialize(data: zenoh.ZBytes, msg_type: type[Message]) -> Message:
    """Deserialize ZBytes to a protobuf message."""
    msg = msg_type()
    msg.ParseFromString(data.to_bytes())
    return msg


def _get_service_types(service_type: type) -> tuple[type[Message], type[Message]]:
    """Extract Request and Response types from a service type.

    Service types must have nested Request and Response classes:

        class MyService:
            class Request(Message): ...
            class Response(Message): ...

    Args:
        service_type: The service type class.

    Returns:
        Tuple of (RequestType, ResponseType).

    Raises:
        TypeError: If service_type is invalid or missing nested classes.
    """
    if not isinstance(service_type, type):
        raise TypeError(
            f"service_type must be a class, got {type(service_type).__name__}"
        )

    try:
        request_type = service_type.Request
    except AttributeError:
        raise TypeError(
            f"Service type '{service_type.__name__}' must have nested 'Request' class"
        ) from None

    try:
        response_type = service_type.Response
    except AttributeError:
        raise TypeError(
            f"Service type '{service_type.__name__}' must have nested 'Response' class"
        ) from None

    return request_type, response_type


class EntityKind(StrEnum):
    """Kind of entity in the graph."""

    PUBLISHER = "MP"
    SUBSCRIBER = "MS"
    SERVER = "SS"
    CLIENT = "SC"


@dataclass(frozen=True, slots=True)
class Entity:
    """Describes an entity discovered in the graph."""

    kind: EntityKind
    topic: str
    type_name: str
    zid: str
    name: str


def _make_lv_key(
    session: Session,
    kind: EntityKind,
    topic: str,
    type_name: str,
) -> str:
    """Build liveliness key: @zrm_lv/{domain}/{zid}/{name}/{kind}/{topic}/{type}."""
    name_escaped = session.name.replace("/", "%")
    topic_escaped = topic.replace("/", "%")
    type_escaped = type_name.replace("/", "%")
    return f"{ADMIN_SPACE}/{session.domain}/{session.zid}/{name_escaped}/{kind}/{topic_escaped}/{type_escaped}"


def _parse_lv_key(key: str) -> Entity | None:
    """Parse liveliness key to Entity. Returns None if malformed."""
    parts = key.split("/")
    # Expected: @zrm_lv / domain / zid / name / kind / topic / type
    if len(parts) != 7:
        return None
    if parts[0] != ADMIN_SPACE:
        return None

    try:
        kind = EntityKind(parts[4])
    except ValueError:
        return None

    return Entity(
        kind=kind,
        topic=parts[5].replace("%", "/"),
        type_name=parts[6].replace("%", "/"),
        zid=parts[2],
        name=parts[3].replace("%", "/"),
    )


class Publisher:
    """Publishes protobuf messages to a topic."""

    def __init__(self, session: Session, topic: str, msg_type: type[Message]):
        """Create a publisher.

        Args:
            session: ZRM session.
            topic: Topic name (e.g., "robot/pose"). Must not start with '/'.
            msg_type: Protobuf message type.

        Raises:
            ValueError: If topic starts with '/'.
        """
        if topic.startswith("/"):
            raise ValueError(
                f"Topic '{topic}' cannot start with '/'. Use '{topic.lstrip('/')}' instead."
            )

        self._topic = topic
        self._msg_type = msg_type
        self._type_name = _type_name(msg_type)

        self._pub = session.zenoh.declare_publisher(topic)
        self._token = session.zenoh.liveliness().declare_token(
            _make_lv_key(session, EntityKind.PUBLISHER, topic, self._type_name)
        )

    def publish(self, msg: Message) -> None:
        """Publish a message.

        Args:
            msg: Protobuf message to publish.

        Raises:
            TypeError: If msg is not the expected type.
        """
        if not isinstance(msg, self._msg_type):
            raise TypeError(
                f"Expected {self._msg_type.__name__}, got {type(msg).__name__}"
            )

        attachment = zenoh.ZBytes(self._type_name.encode())
        self._pub.put(_serialize(msg), attachment=attachment)

    def close(self) -> None:
        """Close the publisher and release resources."""
        self._token.undeclare()
        self._pub.undeclare()


class Subscriber:
    """Subscribes to protobuf messages on a topic."""

    def __init__(
        self,
        session: Session,
        topic: str,
        msg_type: type[Message],
        callback: Callable[[Message], None] | None = None,
    ):
        """Create a subscriber.

        Args:
            session: ZRM session.
            topic: Topic name (e.g., "robot/pose"). Must not start with '/'.
            msg_type: Expected protobuf message type.
            callback: Optional callback invoked for each message.

        Raises:
            ValueError: If topic starts with '/'.
        """
        if topic.startswith("/"):
            raise ValueError(
                f"Topic '{topic}' cannot start with '/'. Use '{topic.lstrip('/')}' instead."
            )

        self._topic = topic
        self._msg_type = msg_type
        self._type_name = _type_name(msg_type)
        self._callback = callback
        self._latest: Message | None = None
        self._lock = threading.Lock()

        def on_sample(sample: zenoh.Sample) -> None:
            # Validate type from attachment.
            if sample.attachment is None:
                print(f"Warning: Message without type attachment on '{topic}'")
                return

            actual_type = sample.attachment.to_bytes().decode()
            if actual_type != self._type_name:
                print(
                    f"Warning: Type mismatch on '{topic}': "
                    f"expected {self._type_name}, got {actual_type}"
                )
                return

            msg = _deserialize(sample.payload, msg_type)

            with self._lock:
                self._latest = msg

            if callback is not None:
                try:
                    callback(msg)
                except Exception as e:
                    print(f"Error in subscriber callback for '{topic}': {e}")

        self._sub = session.zenoh.declare_subscriber(topic, on_sample)
        self._token = session.zenoh.liveliness().declare_token(
            _make_lv_key(session, EntityKind.SUBSCRIBER, topic, self._type_name)
        )

    def latest(self) -> Message | None:
        """Get the most recently received message, or None if none received."""
        with self._lock:
            return self._latest

    def close(self) -> None:
        """Close the subscriber and release resources."""
        self._token.undeclare()
        self._sub.undeclare()


class Server:
    """Serves requests for a service."""

    def __init__(
        self,
        session: Session,
        name: str,
        service_type: type,
        handler: Callable[[Message], Message],
    ):
        """Create a service server.

        Args:
            session: ZRM session.
            name: Service name (e.g., "add_two_ints"). Must not start with '/'.
            service_type: Protobuf type with nested Request and Response classes.
            handler: Function that takes Request and returns Response.

        Raises:
            ValueError: If name starts with '/'.
            TypeError: If service_type is invalid.
        """
        if name.startswith("/"):
            raise ValueError(
                f"Service name '{name}' cannot start with '/'. "
                f"Use '{name.lstrip('/')}' instead."
            )

        self._name = name
        self._request_type, self._response_type = _get_service_types(service_type)
        self._handler = handler
        self._type_name = _type_name(service_type)
        self._request_type_name = _type_name(self._request_type)
        self._response_type_name = _type_name(self._response_type)

        def on_query(query: zenoh.Query) -> None:
            try:
                # Validate request type.
                if query.attachment is None:
                    query.reply_err(zenoh.ZBytes(b"Missing type attachment"))
                    return

                actual_type = query.attachment.to_bytes().decode()
                if actual_type != self._request_type_name:
                    query.reply_err(
                        zenoh.ZBytes(
                            f"Type mismatch: expected {self._request_type_name}, "
                            f"got {actual_type}".encode()
                        )
                    )
                    return

                # Deserialize and handle.
                request = _deserialize(query.payload, self._request_type)
                response = handler(request)

                # Validate response type.
                if not isinstance(response, self._response_type):
                    query.reply_err(
                        zenoh.ZBytes(
                            f"Handler returned {type(response).__name__}, "
                            f"expected {self._response_type.__name__}".encode()
                        )
                    )
                    return

                # Send response.
                query.reply(
                    name,
                    _serialize(response),
                    attachment=zenoh.ZBytes(self._response_type_name.encode()),
                )

            except Exception as e:
                print(f"Error in service '{name}': {e}")
                query.reply_err(zenoh.ZBytes(f"Server error: {e}".encode()))

        self._queryable = session.zenoh.declare_queryable(name, on_query)
        self._token = session.zenoh.liveliness().declare_token(
            _make_lv_key(session, EntityKind.SERVER, name, self._type_name)
        )

    def close(self) -> None:
        """Close the server and release resources."""
        self._token.undeclare()
        self._queryable.undeclare()


class Client:
    """Calls a service."""

    def __init__(self, session: Session, name: str, service_type: type):
        """Create a service client.

        Args:
            session: ZRM session.
            name: Service name (e.g., "add_two_ints"). Must not start with '/'.
            service_type: Protobuf type with nested Request and Response classes.

        Raises:
            ValueError: If name starts with '/'.
            TypeError: If service_type is invalid.
        """
        if name.startswith("/"):
            raise ValueError(
                f"Service name '{name}' cannot start with '/'. "
                f"Use '{name.lstrip('/')}' instead."
            )

        self._session = session
        self._name = name
        self._request_type, self._response_type = _get_service_types(service_type)
        self._type_name = _type_name(service_type)
        self._request_type_name = _type_name(self._request_type)
        self._response_type_name = _type_name(self._response_type)

        self._token = session.zenoh.liveliness().declare_token(
            _make_lv_key(session, EntityKind.CLIENT, name, self._type_name)
        )

    def call(self, request: Message, timeout: float | None = None) -> Message:
        """Call the service synchronously.

        Args:
            request: Request message.
            timeout: Timeout in seconds (None = no timeout).

        Returns:
            Response message.

        Raises:
            TypeError: If request is wrong type.
            TimeoutError: If no response within timeout.
            ServiceError: If service returns an error.
        """
        if not isinstance(request, self._request_type):
            raise TypeError(
                f"Expected {self._request_type.__name__}, got {type(request).__name__}"
            )

        replies = self._session.zenoh.get(
            self._name,
            payload=_serialize(request),
            attachment=zenoh.ZBytes(self._request_type_name.encode()),
            timeout=timeout,
        )

        for reply in replies:
            if reply.ok is None:
                error_msg = reply.err.payload.to_string() if reply.err else "Unknown"
                raise ServiceError(f"Service '{self._name}' error: {error_msg}")

            # Validate response type.
            if reply.ok.attachment is None:
                raise ServiceError(f"Response from '{self._name}' missing type")

            actual_type = reply.ok.attachment.to_bytes().decode()
            if actual_type != self._response_type_name:
                raise MessageTypeMismatchError(
                    f"Response type mismatch: expected {self._response_type_name}, "
                    f"got {actual_type}"
                )

            return _deserialize(reply.ok.payload, self._response_type)

        raise TimeoutError(f"Service '{self._name}' did not respond")

    def close(self) -> None:
        """Close the client and release resources."""
        self._token.undeclare()


class Graph:
    """Discovers entities in the ZRM network.

    Uses Zenoh's liveliness feature to track publishers, subscribers,
    servers, and clients.
    """

    def __init__(self, session: Session):
        """Create a graph for discovery.

        Args:
            session: ZRM session to use for discovery.
        """
        self._session = session
        self._entities: dict[str, Entity] = {}
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)

        key_expr = f"{ADMIN_SPACE}/{session.domain}/**"

        def on_liveliness(sample: zenoh.Sample) -> None:
            key = str(sample.key_expr)
            entity = _parse_lv_key(key)
            if entity is None:
                return

            with self._condition:
                if sample.kind == zenoh.SampleKind.PUT:
                    self._entities[key] = entity
                elif sample.kind == zenoh.SampleKind.DELETE:
                    self._entities.pop(key, None)
                self._condition.notify_all()

        # Get existing entities.
        for reply in session.zenoh.liveliness().get(key_expr, timeout=1.0):
            if reply.ok is not None:
                on_liveliness(reply.ok)

        self._sub = session.zenoh.liveliness().declare_subscriber(
            key_expr,
            on_liveliness,
            # TODO: Do we need history? Enabling it causes duplicate entries currently since we manually fetch existing tokens above.
            # history=True,
        )

    def get_publishers(self, topic: str) -> list[Entity]:
        """Get all publishers for a topic."""
        with self._lock:
            return [
                e
                for e in self._entities.values()
                if e.kind == EntityKind.PUBLISHER and e.topic == topic
            ]

    def get_subscribers(self, topic: str) -> list[Entity]:
        """Get all subscribers for a topic."""
        with self._lock:
            return [
                e
                for e in self._entities.values()
                if e.kind == EntityKind.SUBSCRIBER and e.topic == topic
            ]

    def get_servers(self, name: str) -> list[Entity]:
        """Get all servers for a service."""
        with self._lock:
            return [
                e
                for e in self._entities.values()
                if e.kind == EntityKind.SERVER and e.topic == name
            ]

    def get_clients(self, name: str) -> list[Entity]:
        """Get all clients for a service."""
        with self._lock:
            return [
                e
                for e in self._entities.values()
                if e.kind == EntityKind.CLIENT and e.topic == name
            ]

    def get_all_entities(self) -> list[Entity]:
        """Get all discovered entities."""
        with self._lock:
            return list(self._entities.values())

    def get_topics(self) -> list[tuple[str, str]]:
        """Get all topics and their types.

        Returns:
            List of (topic_name, type_name) tuples.
        """
        results: dict[str, str] = {}
        with self._lock:
            for entity in self._entities.values():
                if entity.kind in (EntityKind.PUBLISHER, EntityKind.SUBSCRIBER):
                    results[entity.topic] = entity.type_name
        return list(results.items())

    def get_services(self) -> list[tuple[str, str]]:
        """Get all services and their types.

        Returns:
            List of (service_name, type_name) tuples.
        """
        results: dict[str, str] = {}
        with self._lock:
            for entity in self._entities.values():
                if entity.kind in (EntityKind.SERVER, EntityKind.CLIENT):
                    results[entity.topic] = entity.type_name
        return list(results.items())

    def wait_for_publisher(self, topic: str, timeout: float | None = None) -> bool:
        """Wait until at least one publisher exists for the topic.

        Args:
            topic: Topic name.
            timeout: Maximum wait time in seconds (None = forever).

        Returns:
            True if found, False if timeout.
        """

        def has_publisher() -> bool:
            return any(
                e.kind == EntityKind.PUBLISHER and e.topic == topic
                for e in self._entities.values()
            )

        with self._condition:
            return self._condition.wait_for(has_publisher, timeout=timeout)

    def wait_for_subscriber(self, topic: str, timeout: float | None = None) -> bool:
        """Wait until at least one subscriber exists for the topic.

        Args:
            topic: Topic name.
            timeout: Maximum wait time in seconds (None = forever).

        Returns:
            True if found, False if timeout.
        """

        def has_subscriber() -> bool:
            return any(
                e.kind == EntityKind.SUBSCRIBER and e.topic == topic
                for e in self._entities.values()
            )

        with self._condition:
            return self._condition.wait_for(has_subscriber, timeout=timeout)

    def wait_for_server(self, name: str, timeout: float | None = None) -> bool:
        """Wait until a server is available for the service.

        Args:
            name: Service name.
            timeout: Maximum wait time in seconds (None = forever).

        Returns:
            True if found, False if timeout.
        """

        def has_server() -> bool:
            return any(
                e.kind == EntityKind.SERVER and e.topic == name
                for e in self._entities.values()
            )

        with self._condition:
            return self._condition.wait_for(has_server, timeout=timeout)

    def wait_for_client(self, name: str, timeout: float | None = None) -> bool:
        """Wait until at least one client exists for the service.

        Args:
            name: Service name.
            timeout: Maximum wait time in seconds (None = forever).

        Returns:
            True if found, False if timeout.
        """

        def has_client() -> bool:
            return any(
                e.kind == EntityKind.CLIENT and e.topic == name
                for e in self._entities.values()
            )

        with self._condition:
            return self._condition.wait_for(has_client, timeout=timeout)

    def close(self) -> None:
        """Close the graph and release resources."""
        self._sub.undeclare()
