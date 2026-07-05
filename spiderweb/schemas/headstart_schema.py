"""Schema constants for the civic Head Start PR layer."""

LAYER_ID = "civic_headstart_pr"
SERVICE_NODE_TYPE = "headstart_service_location"
OPERATOR_NODE_TYPE = "headstart_operator"
EDGE_OPERATED_BY = "OPERATED_BY"
EDGE_ADMINISTERED_FROM = "ADMINISTERED_FROM"
STANDALONE_CONFIDENCE_CAP = 20.0

REQUIRED_FIELDS = {
    "hs_id",
    "service_location_name",
    "recipient_name",
    "latitude",
    "longitude",
}

PUBLIC_EXPORT_POLICY = {
    "precise_points_public": False,
    "public_export": "grid_only",
    "route_generation_allowed": False,
    "field_visit_routing_allowed": False,
}

PR_BOUNDS = {
    "min_lat": 17.7,
    "max_lat": 18.6,
    "min_lon": -67.4,
    "max_lon": -65.1,
}
