"""Tests for Entity, NodeEntity, EndpointEntity and liveliness key parsing."""

from __future__ import annotations

import pytest

import zrm


def test_node_entity_creation():
    """Test creating a NodeEntity."""
    node = zrm.NodeEntity(domain_id=0, z_id="abc123", name="robot_controller")

    assert node.domain_id == 0
    assert node.z_id == "abc123"
    assert node.name == "robot_controller"


def test_node_entity_key():
    """Test NodeEntity.key() returns the name."""
    node = zrm.NodeEntity(domain_id=0, z_id="abc123", name="robot_controller")
    assert node.key() == "robot_controller"


def test_node_entity_to_liveliness_ke():
    """Test NodeEntity to liveliness key expression conversion."""
    node = zrm.NodeEntity(domain_id=0, z_id="abc123", name="robot_controller")
    ke = node.to_liveliness_ke()

    assert ke == "@zrm_lv/0/abc123/NN/robot_controller"


def test_node_entity_to_liveliness_ke_with_slash():
    """Test NodeEntity liveliness key with slash in name."""
    node = zrm.NodeEntity(domain_id=0, z_id="abc123", name="robot/controller")
    ke = node.to_liveliness_ke()

    # Slash should be replaced with %
    assert ke == "@zrm_lv/0/abc123/NN/robot%controller"


def test_endpoint_entity_creation():
    """Test creating an EndpointEntity."""
    node = zrm.NodeEntity(domain_id=0, z_id="abc123", name="test_node")
    endpoint = zrm.EndpointEntity(
        node=node,
        kind=zrm.EntityKind.PUBLISHER,
        topic="robot/pose",
        type_name="geometry.Pose",
    )

    assert endpoint.node == node
    assert endpoint.kind == zrm.EntityKind.PUBLISHER
    assert endpoint.topic == "robot/pose"
    assert endpoint.type_name == "geometry.Pose"


def test_endpoint_entity_to_liveliness_ke():
    """Test EndpointEntity to liveliness key expression conversion."""
    node = zrm.NodeEntity(domain_id=0, z_id="abc123", name="test_node")
    endpoint = zrm.EndpointEntity(
        node=node,
        kind=zrm.EntityKind.PUBLISHER,
        topic="robot/pose",
        type_name="geometry.Pose",
    )

    ke = endpoint.to_liveliness_ke()
    assert ke == "@zrm_lv/0/abc123/MP/test_node/robot%pose/geometry.Pose"


def test_endpoint_entity_to_liveliness_ke_with_slashes():
    """Test EndpointEntity liveliness key with slashes in names."""
    node = zrm.NodeEntity(domain_id=0, z_id="abc123", name="ns/node")
    endpoint = zrm.EndpointEntity(
        node=node,
        kind=zrm.EntityKind.SUBSCRIBER,
        topic="robot/status/pose",
        type_name="geometry/msgs/Pose",
    )

    ke = endpoint.to_liveliness_ke()
    assert ke == "@zrm_lv/0/abc123/MS/ns%node/robot%status%pose/geometry%msgs%Pose"


def test_endpoint_entity_no_type_name():
    """Test EndpointEntity with None type_name."""
    node = zrm.NodeEntity(domain_id=0, z_id="abc123", name="test_node")
    endpoint = zrm.EndpointEntity(
        node=node,
        kind=zrm.EntityKind.PUBLISHER,
        topic="robot/pose",
        type_name=None,
    )

    ke = endpoint.to_liveliness_ke()
    assert ke == "@zrm_lv/0/abc123/MP/test_node/robot%pose/EMPTY"


def test_entity_with_node():
    """Test Entity containing a NodeEntity."""
    node = zrm.NodeEntity(domain_id=0, z_id="abc123", name="test_node")
    entity = zrm.Entity(node=node)

    assert entity.kind() == zrm.EntityKind.NODE
    assert entity.get_endpoint() is None


def test_entity_with_endpoint():
    """Test Entity containing an EndpointEntity."""
    node = zrm.NodeEntity(domain_id=0, z_id="abc123", name="test_node")
    endpoint = zrm.EndpointEntity(
        node=node,
        kind=zrm.EntityKind.PUBLISHER,
        topic="robot/pose",
        type_name="geometry.Pose",
    )
    entity = zrm.Entity(endpoint=endpoint)

    assert entity.kind() == zrm.EntityKind.PUBLISHER
    assert entity.get_endpoint() == endpoint


def test_entity_from_liveliness_ke_node():
    """Test parsing a node liveliness key expression."""
    ke = "@zrm_lv/0/abc123/NN/robot_controller"
    entity = zrm.Entity.from_liveliness_ke(ke)

    assert entity is not None
    assert entity.kind() == zrm.EntityKind.NODE
    assert entity.node is not None
    assert entity.node.name == "robot_controller"
    assert entity.node.z_id == "abc123"
    assert entity.node.domain_id == 0


def test_entity_from_liveliness_ke_node_with_slash():
    """Test parsing a node liveliness key with slash in name."""
    ke = "@zrm_lv/0/abc123/NN/robot%controller"
    entity = zrm.Entity.from_liveliness_ke(ke)

    assert entity is not None
    assert entity.node is not None
    assert entity.node.name == "robot/controller"


def test_entity_from_liveliness_ke_publisher():
    """Test parsing a publisher liveliness key expression."""
    ke = "@zrm_lv/0/abc123/MP/test_node/robot%pose/geometry.Pose"
    entity = zrm.Entity.from_liveliness_ke(ke)

    assert entity is not None
    assert entity.kind() == zrm.EntityKind.PUBLISHER
    assert entity.endpoint is not None
    assert entity.endpoint.topic == "robot/pose"
    assert entity.endpoint.type_name == "geometry.Pose"
    assert entity.endpoint.node.name == "test_node"


def test_entity_from_liveliness_ke_subscriber():
    """Test parsing a subscriber liveliness key expression."""
    ke = "@zrm_lv/0/abc123/MS/test_node/sensor%data/sensor.LaserScan"
    entity = zrm.Entity.from_liveliness_ke(ke)

    assert entity is not None
    assert entity.kind() == zrm.EntityKind.SUBSCRIBER
    assert entity.endpoint is not None
    assert entity.endpoint.topic == "sensor/data"
    assert entity.endpoint.type_name == "sensor.LaserScan"


def test_entity_from_liveliness_ke_service():
    """Test parsing a service liveliness key expression."""
    ke = "@zrm_lv/0/abc123/SS/test_node/compute_path/nav.ComputePath"
    entity = zrm.Entity.from_liveliness_ke(ke)

    assert entity is not None
    assert entity.kind() == zrm.EntityKind.SERVICE
    assert entity.endpoint is not None
    assert entity.endpoint.topic == "compute_path"
    assert entity.endpoint.type_name == "nav.ComputePath"


def test_entity_from_liveliness_ke_client():
    """Test parsing a client liveliness key expression."""
    ke = "@zrm_lv/0/abc123/SC/test_node/compute_path/nav.ComputePath"
    entity = zrm.Entity.from_liveliness_ke(ke)

    assert entity is not None
    assert entity.kind() == zrm.EntityKind.CLIENT
    assert entity.endpoint is not None
    assert entity.endpoint.topic == "compute_path"
    assert entity.endpoint.type_name == "nav.ComputePath"


def test_entity_from_liveliness_ke_empty_type():
    """Test parsing endpoint with EMPTY type name."""
    ke = "@zrm_lv/0/abc123/MP/test_node/robot%pose/EMPTY"
    entity = zrm.Entity.from_liveliness_ke(ke)

    assert entity is not None
    assert entity.endpoint is not None
    assert entity.endpoint.type_name is None


def test_entity_from_liveliness_ke_invalid_short():
    """Test parsing invalid liveliness key (too short)."""
    ke = "@zrm_lv/0/abc123"

    with pytest.raises(ValueError, match="Invalid liveliness key"):
        zrm.Entity.from_liveliness_ke(ke)


def test_entity_from_liveliness_ke_invalid_admin_space():
    """Test parsing liveliness key with wrong admin space."""
    ke = "@wrong/0/abc123/NN/test_node"

    with pytest.raises(AssertionError, match="Invalid admin space"):
        zrm.Entity.from_liveliness_ke(ke)


def test_entity_from_liveliness_ke_invalid_endpoint_short():
    """Test parsing endpoint key that's too short."""
    ke = "@zrm_lv/0/abc123/MP/test_node"
    entity = zrm.Entity.from_liveliness_ke(ke)

    # Should return None for incomplete endpoint
    assert entity is None


def test_entity_from_liveliness_ke_invalid_kind():
    """Test parsing liveliness key with invalid entity kind."""
    ke = "@zrm_lv/0/abc123/XX/test_node"
    entity = zrm.Entity.from_liveliness_ke(ke)

    # Should return None for invalid kind
    assert entity is None


def test_entity_kind_enum():
    """Test EntityKind enum values."""
    assert zrm.EntityKind.NODE == "NN"
    assert zrm.EntityKind.PUBLISHER == "MP"
    assert zrm.EntityKind.SUBSCRIBER == "MS"
    assert zrm.EntityKind.SERVICE == "SS"
    assert zrm.EntityKind.CLIENT == "SC"


def test_entity_roundtrip_node():
    """Test node entity roundtrip: create -> to_liveliness_ke -> from_liveliness_ke."""
    node = zrm.NodeEntity(domain_id=5, z_id="xyz789", name="test/node")
    ke = node.to_liveliness_ke()
    parsed = zrm.Entity.from_liveliness_ke(ke)

    assert parsed is not None
    assert parsed.node is not None
    assert parsed.node.name == node.name
    assert parsed.node.z_id == node.z_id
    assert parsed.node.domain_id == node.domain_id


def test_entity_roundtrip_endpoint():
    """Test endpoint entity roundtrip: create -> to_liveliness_ke -> from_liveliness_ke."""
    node = zrm.NodeEntity(domain_id=5, z_id="xyz789", name="test/node")
    endpoint = zrm.EndpointEntity(
        node=node,
        kind=zrm.EntityKind.SUBSCRIBER,
        topic="robot/sensors/lidar",
        type_name="sensor/msgs/LaserScan",
    )

    ke = endpoint.to_liveliness_ke()
    parsed = zrm.Entity.from_liveliness_ke(ke)

    assert parsed is not None
    assert parsed.endpoint is not None
    assert parsed.endpoint.topic == endpoint.topic
    assert parsed.endpoint.type_name == endpoint.type_name
    assert parsed.endpoint.kind == endpoint.kind
    assert parsed.endpoint.node.name == endpoint.node.name
