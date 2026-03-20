"""Shared CLI helpers for ZRM tools."""

from google.protobuf import text_format

import zrm


class Style:
    """ANSI styles for terminal output."""

    BOLD = "\033[1m"
    DIM = "\033[2m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    R = "\033[0m"


def validate_name(name: str) -> None:
    """Raise ValueError if a topic or service name starts with '/'."""
    if name.startswith("/"):
        raise ValueError(
            f"Name cannot start with '/'. Use '{name.lstrip('/')}' instead."
        )


def resolve_topic_type(graph: zrm.Graph, topic: str, msg_type: str | None) -> str:
    """Resolve message type: use provided or auto-discover from graph.

    Raises LookupError if the topic is not found and no type was provided.
    """
    if msg_type is not None:
        return msg_type
    for topic_name, type_name in graph.get_topics():
        if topic_name == topic:
            return type_name
    raise LookupError(f"Topic '{topic}' not found. Specify type explicitly.")


def resolve_service_type(
    graph: zrm.Graph, service: str, service_type: str | None
) -> str:
    """Resolve service type: use provided or auto-discover from graph.

    Raises LookupError if the service is not found and no type was provided.
    """
    if service_type is not None:
        return service_type
    for svc_name, type_name in graph.get_services():
        if svc_name == service:
            return type_name
    raise LookupError(f"Service '{service}' not found. Specify type explicitly.")


def load_message_type(type_name: str) -> type:
    """Load a protobuf message class by fully qualified type name.

    Raises LookupError if the type cannot be loaded.
    """
    try:
        return zrm.get_message_type(type_name)
    except (ImportError, AttributeError, ValueError) as e:
        raise LookupError(f"Cannot load message type '{type_name}': {e}") from e


def get_topics(session_name: str = "_zrm_cli") -> str:
    """Return a plain-text listing of all topics in the network."""
    with zrm.open(name=session_name) as session:
        graph = zrm.Graph(session)
        topics = graph.get_topics()
        if not topics:
            graph.close()
            return "No topics found"
        lines: list[str] = []
        for topic_name, type_name in sorted(topics):
            pubs = graph.get_publishers(topic_name)
            subs = graph.get_subscribers(topic_name)
            lines.append(
                f"{topic_name}  type={type_name}  pub={len(pubs)}  sub={len(subs)}"
            )
        graph.close()
        return "\n".join(lines)


def get_services(session_name: str = "_zrm_cli") -> str:
    """Return a plain-text listing of all services in the network."""
    with zrm.open(name=session_name) as session:
        graph = zrm.Graph(session)
        services = graph.get_services()
        if not services:
            graph.close()
            return "No services found"
        lines: list[str] = []
        for service_name, type_name in sorted(services):
            servers = graph.get_servers(service_name)
            clients = graph.get_clients(service_name)
            lines.append(
                f"{service_name}  type={type_name}"
                f"  servers={len(servers)}  clients={len(clients)}"
            )
        graph.close()
        return "\n".join(lines)


def get_sessions(session_name: str = "_zrm_cli") -> str:
    """Return a plain-text listing of all sessions in the network."""
    with zrm.open(name=session_name) as session:
        graph = zrm.Graph(session)
        entities = graph.get_all_entities()

        grouped: dict[str, list[zrm.Entity]] = {}
        for entity in entities:
            if entity.name == session_name:
                continue
            grouped.setdefault(entity.name, []).append(entity)

        if not grouped:
            graph.close()
            return "No sessions found"

        lines: list[str] = []
        for name in sorted(grouped):
            group = grouped[name]
            pubs = [e for e in group if e.kind == zrm.EntityKind.PUBLISHER]
            subs = [e for e in group if e.kind == zrm.EntityKind.SUBSCRIBER]
            servers = [e for e in group if e.kind == zrm.EntityKind.SERVER]
            clients = [e for e in group if e.kind == zrm.EntityKind.CLIENT]
            parts = [name]
            if pubs:
                topics = ", ".join(e.topic for e in pubs)
                parts.append(f"  pub: {topics}")
            if subs:
                topics = ", ".join(e.topic for e in subs)
                parts.append(f"  sub: {topics}")
            if servers:
                topics = ", ".join(e.topic for e in servers)
                parts.append(f"  srv: {topics}")
            if clients:
                topics = ", ".join(e.topic for e in clients)
                parts.append(f"  cli: {topics}")
            lines.append("\n".join(parts))
        graph.close()
        return "\n\n".join(lines)


def call(
    service: str,
    data: str,
    service_type: str | None = None,
    timeout: float = 300.0,
    session_name: str = "_zrm_cli",
) -> str:
    """Call a service and return the response as protobuf text.

    Raises ValueError for invalid names, LookupError for missing types,
    text_format.ParseError for bad request data, TimeoutError on timeout,
    and zrm.ServiceError for service failures.
    """
    validate_name(service)
    with zrm.open(name=session_name) as session:
        graph = zrm.Graph(session)
        resolved = resolve_service_type(graph, service, service_type)
        svc_cls = load_message_type(resolved)

        request = svc_cls.Request()
        text_format.Parse(data, request)

        client = zrm.Client(session, service, svc_cls)
        try:
            response = client.call(request, timeout=timeout)
            return text_format.MessageToString(response)
        finally:
            client.close()
            graph.close()
