"""Fuel price sub-module constants."""
OPINET_AVG_URL = "http://www.opinet.co.kr/api/avgAllPrice.do"
OPINET_LOWPRICE_URL = "http://www.opinet.co.kr/api/lowTop10.do"
FUEL_SCAN_INTERVAL = 3600  # 1시간
FUEL_TYPES = {"B027": "휘발유", "D047": "경유", "B034": "고급휘발유", "K015": "등유", "C004": "LPG"}
SIDO_CODES = {
    "01": "서울", "02": "경기", "03": "강원", "04": "충북", "05": "충남",
    "06": "전북", "07": "전남", "08": "경북", "09": "경남", "10": "부산",
    "11": "제주", "12": "대구", "13": "인천", "14": "광주",
    "15": "대전", "16": "울산", "17": "세종",
}
