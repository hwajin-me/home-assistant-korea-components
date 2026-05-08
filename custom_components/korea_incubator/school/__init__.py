"""School info (NEIS) sub-module."""
NEIS_BASE = "https://open.neis.go.kr/hub"
SCHOOL_SCAN_INTERVAL = 21600  # 6h
ENDPOINTS = {
    "school_info": "schoolInfo", "meal": "mealServiceDietInfo",
    "calendar": "SchoolSchedule",
    "timetable": {"elementary": "elsTimetable", "middle": "misTimetable", "high": "hisTimetable"},
    "classroom_info": "tiClrminfo",
}
SCHOOL_LEVELS = {"elementary": "초등학교", "middle": "중학교", "high": "고등학교"}
ALLERGY_MAP = {
    1:"난류", 2:"우유", 3:"메밀", 4:"땅콩", 5:"대두", 6:"밀", 7:"고등어",
    8:"게", 9:"새우", 10:"돼지고기", 11:"복숭아", 12:"토마토", 13:"아황산류",
    14:"호두", 15:"닭고기", 16:"쇠고기", 17:"오징어", 18:"조개류"
}
