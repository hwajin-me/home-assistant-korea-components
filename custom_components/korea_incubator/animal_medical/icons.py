"""Shared medical entity icons; unknown hours must not look closed."""


def operating_icon(state):
    return {
        "open": "mdi:store-check",
        "closed": "mdi:store-off",
        "break": "mdi:coffee-outline",
    }.get(state, "mdi:help-circle-outline")


def institution_icon(data):
    if data.get("service") == "pharmacy":
        return "mdi:pharmacy"
    if data.get("institution_type") == "pharmacy":
        return "mdi:pill"
    return "mdi:paw"
