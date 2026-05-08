"""Transit sub-module constants."""
SUBWAY_BULK_URL = "http://swopenAPI.seoul.go.kr/api/subway/{key}/json/realtimeStationArrival/0/500/{station}"
SUBWAY_SCAN_INTERVAL = 120

BUS_STOP_URL = "http://ws.bus.go.kr/api/rest/stationinfo/getStationByName"
BUS_ROUTE_BY_STATION_URL = "http://ws.bus.go.kr/api/rest/stationinfo/getRouteByStation"
BUS_ARRIVAL_URL = "http://ws.bus.go.kr/api/rest/arrive/getArrInfoByRoute"
BUS_SCAN_INTERVAL = 60

DIRECTION_UP = "상행"
DIRECTION_DOWN = "하행"
DIRECTION_INNER = "내선"
DIRECTION_OUTER = "외선"
DIRECTIONS = [DIRECTION_UP, DIRECTION_DOWN, DIRECTION_INNER, DIRECTION_OUTER]

SUBWAY_LINES = {
    "1001": "1호선", "1002": "2호선", "1003": "3호선", "1004": "4호선",
    "1005": "5호선", "1006": "6호선", "1007": "7호선", "1008": "8호선",
    "1009": "9호선", "1063": "경의중앙선", "1065": "공항철도",
    "1067": "경춘선", "1075": "수인분당선", "1077": "신분당선", "1092": "우이신설선",
}
