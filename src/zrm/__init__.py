"""ZRM: Minimal Zenoh-based communication middleware with ROS-like API."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

import zenoh
from google.protobuf.message import Message

__all__ = [
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
class NodeEntity:
    """Node entity in the graph."""

    domain_id: int
    z_id: str
    name: str

    def key(self) -> str:
        """Get unique key for this node (name)."""
        return self.name

    def to_liveliness_ke(self) -> str:
        """Convert to liveliness key expression."""
        node_name = self.name.replace("/", "%")
        return (
            f"{ADMIN_SPACE}/{self.domain_id}/{self.z_id}/{EntityKind.NODE}/{node_name}"
        )


@dataclass
class EndpointEntity:
    """Endpoint entity (publisher, subscriber, service, client) in the graph."""

    node: NodeEntity
    kind: EntityKind
    topic: str
    type_name: str | None = None

    def to_liveliness_ke(self) -> str:
        """Convert to liveliness key expression."""
        node_name = self.node.name.replace("/", "%")
        topic_name = self.topic.replace("/", "%")
        type_info = (
            "EMPTY" if self.type_name is None else self.type_name.replace("/", "%")
        )

        return (
            f"{ADMIN_SPACE}/{self.node.domain_id}/{self.node.z_id}/"
            f"{self.kind}/{node_name}/{topic_name}/{type_info}"
        )


@dataclass
class Entity:
    """Union type for Node or Endpoint entity."""

    node: NodeEntity | None = None
    endpoint: EndpointEntity | None = None

    def kind(self) -> EntityKind:
        """Get the entity kind."""
        if self.endpoint is not None:
            return self.endpoint.kind
        return EntityKind.NODE

    def get_endpoint(self) -> EndpointEntity | None:
        """Get endpoint entity if this is an endpoint."""
        return self.endpoint

    @staticmethod
    def from_liveliness_ke(ke: str) -> "Entity | None":
        """Parse a liveliness key expression into an Entity.

        Format:
        - Node: @zrm_lv/{domain_id}/{z_id}/NN/{node_name}
        - Endpoint: @zrm_lv/{domain_id}/{z_id}/{kind}/{node_name}/{topic_name}/{type_name}
        """
        parts = ke.split("/")
        if len(parts) < 5:
            raise ValueError(f"Invalid liveliness key: {ke}")

        assert parts[0] == ADMIN_SPACE, (
            f"Invalid admin space in liveliness key: '{ke}'. Expected '{ADMIN_SPACE}' but got '{parts[0]}'"
        )

        try:
            domain_id = int(parts[1])
            z_id = parts[2]
            entity_kind = EntityKind(parts[3])
            node_name = parts[4].replace("%", "/")

            node = NodeEntity(
                domain_id=domain_id,
                z_id=z_id,
                name=node_name,
            )

            if entity_kind == EntityKind.NODE:
                return Entity(node=node)

            # For endpoints, we need at least 7 parts
            if len(parts) < 7:
                return None

            topic_name = parts[5].replace("%", "/")
            type_name = None if parts[6] == "EMPTY" else parts[6].replace("%", "/")

            endpoint = EndpointEntity(
                node=node,
                kind=entity_kind,
                topic=topic_name,
                type_name=type_name,
            )

            return Entity(endpoint=endpoint)

        except (ValueError, IndexError):
            return None


class GraphData:
    """Internal graph data structure with efficient indexing."""

    def __init__(self) -> None:
        """Initialize empty graph data."""
        self._entities: dict[str, Entity] = {}  # Liveliness key -> parsed entity
        self._by_topic: dict[str, list[Entity]] = {}  # Topic -> entities
        self._by_service: dict[str, list[Entity]] = {}  # Service -> entities
        self._by_node: dict[str, list[Entity]] = {}  # NodeKey -> entities

    def insert(self, ke: str) -> None:
        """Add a new liveliness key and update indexes."""
        # Parse the entity
        entity = Entity.from_liveliness_ke(ke)
        if entity is None:
            return

        # Store it
        self._entities[ke] = entity

        # Update indexes
        endpoint = entity.get_endpoint()
        if endpoint is not None:
            # Index endpoint by its node
            node_key = endpoint.node.key()
            if node_key not in self._by_node:
                self._by_node[node_key] = []
            self._by_node[node_key].append(entity)

            # Index by topic or service
            if endpoint.kind in (EntityKind.PUBLISHER, EntityKind.SUBSCRIBER):
                if endpoint.topic not in self._by_topic:
                    self._by_topic[endpoint.topic] = []
                self._by_topic[endpoint.topic].append(entity)
            elif endpoint.kind in (EntityKind.SERVICE, EntityKind.CLIENT):
                if endpoint.topic not in self._by_service:
                    self._by_service[endpoint.topic] = []
                self._by_service[endpoint.topic].append(entity)
        elif entity.node is not None:
            # Index standalone node entity
            node_key = entity.node.key()
            if node_key not in self._by_node:
                self._by_node[node_key] = []
            self._by_node[node_key].append(entity)

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

        for entity in self._entities.values():
            endpoint = entity.get_endpoint()
            if endpoint is not None:
                # Index endpoint by its node
                node_key = endpoint.node.key()
                if node_key not in self._by_node:
                    self._by_node[node_key] = []
                self._by_node[node_key].append(entity)

                # Index by topic or service
                if endpoint.kind in (EntityKind.PUBLISHER, EntityKind.SUBSCRIBER):
                    if endpoint.topic not in self._by_topic:
                        self._by_topic[endpoint.topic] = []
                    self._by_topic[endpoint.topic].append(entity)
                elif endpoint.kind in (EntityKind.SERVICE, EntityKind.CLIENT):
                    if endpoint.topic not in self._by_service:
                        self._by_service[endpoint.topic] = []
                    self._by_service[endpoint.topic].append(entity)
            elif entity.node is not None:
                # Index standalone node entity
                node_key = entity.node.key()
                if node_key not in self._by_node:
                    self._by_node[node_key] = []
                self._by_node[node_key].append(entity)

    def visit_by_topic(self, topic: str, callback: Callable[[Entity], None]) -> None:
        """Visit all entities for a given topic."""
        if topic in self._by_topic:
            for entity in self._by_topic[topic]:
                callback(entity)

    def visit_by_service(
        self, service: str, callback: Callable[[Entity], None]
    ) -> None:
        """Visit all entities for a given service."""
        if service in self._by_service:
            for entity in self._by_service[service]:
                callback(entity)

    def visit_by_node(self, node_key: str, callback: Callable[[Entity], None]) -> None:
        """Visit all entities for a given node."""
        if node_key in self._by_node:
            for entity in self._by_node[node_key]:
                callback(entity)


def get_type_name(msg_or_type) -> str:
    """Get the full protobuf type name from a message instance or type."""
    if isinstance(msg_or_type, type):
        return msg_or_type.DESCRIPTOR.full_name
    return msg_or_type.DESCRIPTOR.full_name


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
        node_entity: NodeEntity,
        topic: str,
        msg_type: type[Message],
    ):
        """Create a publisher.

        Args:
            context: Context containing the Zenoh session
            node_entity: Node entity for graph registration
            topic: Zenoh key expression (e.g., "robot/pose")
            msg_type: Protobuf message type
        """
        self._topic = topic
        self._msg_type = msg_type
        self._session = context.session
        self._publisher = self._session.declare_publisher(topic)

        # Declare liveliness token for graph discovery
        endpoint = EndpointEntity(
            node=node_entity,
            kind=EntityKind.PUBLISHER,
            topic=topic,
            type_name=get_type_name(msg_type),
        )
        self._lv_token = self._session.liveliness().declare_token(
            endpoint.to_liveliness_ke()
        )

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
        node_entity: NodeEntity,
        topic: str,
        msg_type: type[Message],
        callback: Callable[[Message], None] | None = None,
    ):
        """Create a subscriber.

        Args:
            context: Context containing the Zenoh session
            node_entity: Node entity for graph registration
            topic: Zenoh key expression (e.g., "robot/pose", "robot/*")
            msg_type: Protobuf message type
            callback: Optional callback function called on each message
        """
        self._topic = topic
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
                        f"Received message without type metadata on topic '{topic}'. "
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
                print(f"Error in subscriber callback for topic '{topic}': {e}")

        self._subscriber = self._session.declare_subscriber(topic, listener)

        # Declare liveliness token for graph discovery
        endpoint = EndpointEntity(
            node=node_entity,
            kind=EntityKind.SUBSCRIBER,
            topic=topic,
            type_name=get_type_name(msg_type),
        )
        self._lv_token = self._session.liveliness().declare_token(
            endpoint.to_liveliness_ke()
        )

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
        node_entity: NodeEntity,
        service: str,
        service_type: type[Message],
        callback: Callable[[Message], Message],
    ):
        """Create a service server.

        Args:
            context: Context containing the Zenoh session
            node_entity: Node entity for graph registration
            service: Service name (e.g., "compute_trajectory")
            service_type: Protobuf service message type with nested Request and Response
            callback: Function that takes request and returns response

        Raises:
            TypeError: If service_type doesn't have Request and Response nested messages
        """
        # Validate that service_type has Request and Response nested messages
        if not isinstance(service_type, type):
            raise TypeError(
                f"service_type must be a protobuf message class, got {type(service_type).__name__}"
            )

        request_type = getattr(service_type, "Request", None)
        response_type = getattr(service_type, "Response", None)

        if request_type is None:
            raise TypeError(
                f"Service type {service_type.__name__} must have a nested 'Request' message"
            )
        if response_type is None:
            raise TypeError(
                f"Service type {service_type.__name__} must have a nested 'Response' message"
            )

        self._service = service
        self._request_type = request_type
        self._response_type = response_type
        self._callback = callback

        self._session = context.session

        def queryable_handler(query):
            try:
                # Extract and validate request type
                if query.attachment is None:
                    raise MessageTypeMismatchError(
                        f"Received service request without type metadata on '{service}'. "
                        "Ensure client includes type information.",
                    )
                actual_request_type = query.attachment.to_bytes().decode()

                # Deserialize request with type validation
                request = deserialize(query.payload, request_type, actual_request_type)

                # Call user callback
                response = self._callback(request)

                # Validate response type
                if not isinstance(response, response_type):
                    raise TypeError(
                        f"Callback must return {response_type.__name__}, "
                        f"got {type(response).__name__}",
                    )

                # Send response with type metadata
                response_type_name = get_type_name(response)
                response_attachment = zenoh.ZBytes(response_type_name.encode())
                query.reply(
                    service,
                    serialize(response),
                    attachment=response_attachment,
                )

            except Exception as e:
                # Send error response
                error_msg = f"Service error: {e}"
                print(f"Error in service '{service}': {error_msg}")
                query.reply_err(zenoh.ZBytes(error_msg.encode()))

        self._queryable = self._session.declare_queryable(service, queryable_handler)

        # Declare liveliness token for graph discovery
        endpoint = EndpointEntity(
            node=node_entity,
            kind=EntityKind.SERVICE,
            topic=service,
            type_name=get_type_name(request_type),
        )
        self._lv_token = self._session.liveliness().declare_token(
            endpoint.to_liveliness_ke()
        )

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
        node_entity: NodeEntity,
        service: str,
        service_type: type[Message],
    ):
        """Create a service client.

        Args:
            context: Context containing the Zenoh session
            node_entity: Node entity for graph registration
            service: Service name
            service_type: Protobuf service message type with nested Request and Response

        Raises:
            TypeError: If service_type doesn't have Request and Response nested messages
        """
        # Validate that service_type has Request and Response nested messages
        if not isinstance(service_type, type):
            raise TypeError(
                f"service_type must be a protobuf message class, got {type(service_type).__name__}"
            )

        request_type = getattr(service_type, "Request", None)
        response_type = getattr(service_type, "Response", None)

        if request_type is None:
            raise TypeError(
                f"Service type {service_type.__name__} must have a nested 'Request' message"
            )
        if response_type is None:
            raise TypeError(
                f"Service type {service_type.__name__} must have a nested 'Response' message"
            )

        self._service = service
        self._request_type = request_type
        self._response_type = response_type

        self._session = context.session

        # TODO: Uncomment when querier is supports passing a timeout in get()
        # Declare querier for making service calls
        # self._querier = self._session.declare_querier(service)

        # Declare liveliness token for graph discovery
        endpoint = EndpointEntity(
            node=node_entity,
            kind=EntityKind.CLIENT,
            topic=service,
            type_name=get_type_name(request_type),
        )
        self._lv_token = self._session.liveliness().declare_token(
            endpoint.to_liveliness_ke()
        )

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
            try:
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
            except Exception as e:
                error_msg = reply.err.payload.to_string()
                raise ServiceError(
                    f"Service '{self._service}' returned error: {error_msg}",
                ) from e

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
        self._lock = threading.Lock()
        self._session = session

        # Subscribe to liveliness tokens with history to get existing entities
        def liveliness_callback(sample: zenoh.Sample) -> None:
            ke = str(sample.key_expr)
            with self._lock:
                if sample.kind == zenoh.SampleKind.PUT:
                    self._data.insert(ke)
                elif sample.kind == zenoh.SampleKind.DELETE:
                    self._data.remove(ke)

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

        def counter(entity: Entity) -> None:
            nonlocal total
            if entity.kind() == kind:
                total += 1

        with self._lock:
            if kind in (EntityKind.PUBLISHER, EntityKind.SUBSCRIBER):
                self._data.visit_by_topic(topic, counter)
            elif kind in (EntityKind.SERVICE, EntityKind.CLIENT):
                self._data.visit_by_service(topic, counter)

        return total

    def get_entities_by_topic(self, kind: EntityKind, topic: str) -> list[Entity]:
        """Get all entities of a given kind on a topic.

        Args:
            kind: Entity kind (PUBLISHER or SUBSCRIBER)
            topic: Topic name

        Returns:
            List of matching entities
        """
        if kind not in (EntityKind.PUBLISHER, EntityKind.SUBSCRIBER):
            raise ValueError("kind must be PUBLISHER or SUBSCRIBER")

        results: list[Entity] = []

        def collector(entity: Entity) -> None:
            if entity.kind() == kind:
                results.append(entity)

        with self._lock:
            self._data.visit_by_topic(topic, collector)

        return results

    def get_entities_by_service(self, kind: EntityKind, service: str) -> list[Entity]:
        """Get all entities of a given kind for a service.

        Args:
            kind: Entity kind (SERVICE or CLIENT)
            service: Service name

        Returns:
            List of matching entities
        """
        if kind not in (EntityKind.SERVICE, EntityKind.CLIENT):
            raise ValueError("kind must be SERVICE or CLIENT")

        results: list[Entity] = []

        def collector(entity: Entity) -> None:
            if entity.kind() == kind:
                results.append(entity)

        with self._lock:
            self._data.visit_by_service(service, collector)

        return results

    def get_entities_by_node(
        self, kind: EntityKind, node_key: str
    ) -> list[EndpointEntity]:
        """Get all endpoint entities of a given kind for a node.

        Args:
            kind: Entity kind (must not be NODE)
            node_key: Node key (node name)

        Returns:
            List of matching endpoint entities
        """
        if kind == EntityKind.NODE:
            raise ValueError("kind must not be NODE")

        results: list[EndpointEntity] = []

        def collector(entity: Entity) -> None:
            if entity.kind() == kind:
                endpoint = entity.get_endpoint()
                if endpoint is not None:
                    results.append(endpoint)

        with self._lock:
            self._data.visit_by_node(node_key, collector)

        return results

    def get_node_names(self) -> list[str]:
        """Get all node names in the network.

        Returns:
            List of node names
        """
        results: list[str] = []

        with self._lock:
            for entity in self._data._entities.values():
                if entity.node is not None:
                    results.append(entity.node.key())

        return results

    def get_topic_names_and_types(self) -> list[tuple[str, str]]:
        """Get all topic names and their types in the network.

        Returns:
            List of (topic_name, type_name) tuples
        """
        results: dict[str, str] = {}

        with self._lock:
            for topic_name, entities in self._data._by_topic.items():
                for entity in entities:
                    endpoint = entity.get_endpoint()
                    if endpoint is not None and endpoint.type_name is not None:
                        results[topic_name] = endpoint.type_name
                        break  # One type per topic

        return list(results.items())

    def get_service_names_and_types(self) -> list[tuple[str, str]]:
        """Get all service names and their types in the network.

        Returns:
            List of (service_name, type_name) tuples
        """
        results: dict[str, str] = {}

        with self._lock:
            for service_name, entities in self._data._by_service.items():
                for entity in entities:
                    endpoint = entity.get_endpoint()
                    if endpoint is not None and endpoint.type_name is not None:
                        results[service_name] = endpoint.type_name
                        break  # One type per service

        return list(results.items())

    def get_names_and_types_by_node(
        self,
        node_key: str,
        kind: EntityKind,
    ) -> list[tuple[str, str]]:
        """Get all topic/service names and types for a given node.

        Args:
            node_key: Node key (node name)
            kind: Entity kind (PUBLISHER, SUBSCRIBER, SERVICE, or CLIENT)

        Returns:
            List of (name, type_name) tuples
        """
        if kind == EntityKind.NODE:
            raise ValueError("kind must not be NODE")

        results: list[tuple[str, str]] = []

        def collector(entity: Entity) -> None:
            if entity.kind() == kind:
                endpoint = entity.get_endpoint()
                if endpoint is not None and endpoint.type_name is not None:
                    results.append((endpoint.topic, endpoint.type_name))

        with self._lock:
            self._data.visit_by_node(node_key, collector)

        return results

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

        # Create node entity
        self._entity = NodeEntity(
            domain_id=self._context.domain_id,
            z_id=str(self._context.session.info.zid()),
            name=name,
        )

        # Declare liveliness token for node presence
        self._lv_token = self._context.session.liveliness().declare_token(
            self._entity.to_liveliness_ke()
        )

        # Create graph for discovery
        self.graph = Graph(self._context.session, domain_id=self._context.domain_id)

    @property
    def name(self) -> str:
        """Get node name."""
        return self._entity.name

    def create_publisher(self, topic: str, msg_type: type[Message]) -> "Publisher":
        """Create a publisher for this node.

        Args:
            topic: Zenoh key expression (e.g., "robot/pose")
            msg_type: Protobuf message type

        Returns:
            Publisher instance
        """
        return Publisher(self._context, self._entity, topic, msg_type)

    def create_subscriber(
        self,
        topic: str,
        msg_type: type[Message],
        callback: Callable[[Message], None] | None = None,
    ) -> "Subscriber":
        """Create a subscriber for this node.

        Args:
            topic: Zenoh key expression (e.g., "robot/pose", "robot/*")
            msg_type: Protobuf message type
            callback: Optional callback function called on each message

        Returns:
            Subscriber instance
        """
        return Subscriber(self._context, self._entity, topic, msg_type, callback)

    def create_service(
        self,
        service: str,
        service_type: type[Message],
        callback: Callable[[Message], Message],
    ) -> "ServiceServer":
        """Create a service server for this node.

        Args:
            service: Service name (e.g., "compute_trajectory")
            service_type: Protobuf service message type with nested Request and Response
            callback: Function that takes request and returns response

        Returns:
            ServiceServer instance
        """
        return ServiceServer(
            self._context, self._entity, service, service_type, callback
        )

    def create_client(
        self,
        service: str,
        service_type: type[Message],
    ) -> "ServiceClient":
        """Create a service client for this node.

        Args:
            service: Service name
            service_type: Protobuf service message type with nested Request and Response

        Returns:
            ServiceClient instance
        """
        return ServiceClient(self._context, self._entity, service, service_type)

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
