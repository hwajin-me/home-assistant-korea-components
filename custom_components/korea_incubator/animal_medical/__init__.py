"""Animal hospital and animal pharmacy data services."""

CONF_INTERVAL = "scan_interval_minutes"
DEFAULT_INTERVAL = 60
MIN_INTERVAL = 1
MAX_INTERVAL = 1440

ANIMAL_MEDICAL_TYPES = {
    "hospital": {
        "name": "동물병원",
        "url": "https://apis.data.go.kr/1741000/animal_hospitals/info",
    },
    "pharmacy": {
        "name": "동물약국",
        "url": "https://apis.data.go.kr/1741000/animal_pharmacies/info",
    },
}
