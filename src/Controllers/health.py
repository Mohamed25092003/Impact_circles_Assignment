from Models.health_schema import HealthResponse


def get_health() -> HealthResponse:
    return HealthResponse()
