# 기여 가이드 (Contributing)

이 프로젝트에 기여해주셔서 감사합니다! 한국 내 서비스를 위한 Home Assistant 통합 구성요소 개발에 참여하실 수 있습니다.

## 🚀 프로젝트 구조

```
custom_components/korea_incubator/
├── __init__.py              # 메인 엔트리 포인트
├── config_flow.py           # 설정 플로우
├── sensor.py               # 센서 엔티티
├── binary_sensor.py        # 바이너리 센서 엔티티
├── const.py               # 상수 정의
├── utils.py               # 유틸리티 함수
├── arisu/                 # 아리수(서울시 상수도) 모듈
├── gasapp/                # 가스앱 모듈
├── goodsflow/             # 굿스플로우 택배조회 모듈
├── kakaomap/              # 카카오맵 길찾기 모듈
├── kepco/                 # 한국전력공사 모듈
└── safety_alert/          # 행정안전부 안전알림 모듈
```

## 📋 기여 방법

### 1. 새로운 서비스 추가하기

새로운 한국 서비스를 추가하려면:

1. **서비스 모듈 생성**
   ```bash
   mkdir custom_components/korea_incubator/새서비스명/
   cd custom_components/korea_incubator/새서비스명/
   ```

2. **필수 파일 구조**
   ```
   새서비스명/
   ├── __init__.py         # 모듈 초기화
   ├── api.py             # API 클라이언트
   ├── device.py          # 디바이스 클래스
   └── exceptions.py      # 예외 클래스
   ```

3. **API 클라이언트 구현** (`api.py`)
   ```python
   import aiohttp
   from .exceptions import 새서비스AuthError, 새서비스ConnectionError
   
   class 새서비스ApiClient:
       def __init__(self, session: aiohttp.ClientSession):
           self.session = session
           
       async def async_login(self, username: str, password: str) -> bool:
           # 로그인 로직 구현
           pass
           
       async def async_get_data(self) -> dict:
           # 데이터 조회 로직 구현
           pass
   ```

4. **디바이스 클래스 구현** (`device.py`)
   ```python
   from homeassistant.helpers.device_registry import DeviceInfo
   from homeassistant.helpers.update_coordinator import UpdateFailed
   from ..const import DOMAIN, LOGGER
   
   class 새서비스Device:
       def __init__(self, hass, entry_id: str, session):
           # 초기화 로직
           
       async def async_update(self):
           # 데이터 업데이트 로직
           
       @property
       def device_info(self) -> DeviceInfo:
           # 디바이스 정보 반환
   ```

5. **예외 클래스 정의** (`exceptions.py`)
   ```python
   class 새서비스Error(Exception):
       """Base exception for 새서비스."""
       
   class 새서비스AuthError(새서비스Error):
       """Authentication error."""
       
   class 새서비스ConnectionError(새서비스Error):
       """Connection error."""
   ```

### 2. Config Flow에 서비스 추가

`config_flow.py`에 새 서비스 설정 단계를 추가:

```python
async def async_step_새서비스(self, user_input=None):
    """Handle 새서비스 configuration."""
    errors = {}
    
    if user_input is not None:
        # 인증 로직
        
    return self.async_show_form(
        step_id="새서비스",
        data_schema=vol.Schema({
            vol.Required("username"): str,
            vol.Required("password"): str,
        }),
        errors=errors,
    )
```

### 3. 메인 모듈에 통합

`__init__.py`에 새 서비스 케이스 추가:

```python
elif service == "새서비스":
    device = 새서비스Device(
        hass, entry.entry_id, session
    )
    # 업데이트 로직 구현
```

## 🔧 개발 환경 설정

### 1. 환경 준비
```bash
# 리포지토리 클론
git clone https://github.com/hwajin-me/home-assistant-korea-components.git
cd home-assistant-korea-components

# 가상환경 생성 (선택사항)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 의존성 설치
pip install -r requirements.txt
```

### 2. 테스트 실행
```bash
# 전체 테스트
pytest

# 특정 서비스 테스트
pytest tests/korea/kepco/
pytest tests/korea/safety_alert/
```

### 3. 코드 스타일
- **PEP 8** 준수
- **Type hints** 사용 권장
- **Docstring** 작성
- **한국어 주석** 허용

## 📝 코딩 가이드라인

### 1. 명명 규칙
- **클래스명**: PascalCase (`KepcoDevice`)
- **함수명**: snake_case (`async_get_data`)
- **상수명**: UPPER_CASE (`DOMAIN`)
- **파일명**: snake_case (`config_flow.py`)

### 2. 에러 처리
```python
try:
    result = await api_client.async_get_data()
except 서비스AuthError as err:
    LOGGER.error(f"Authentication failed: {err}")
    raise UpdateFailed(f"Authentication error: {err}")
except Exception as err:
    LOGGER.error(f"Unexpected error: {err}")
    raise UpdateFailed(f"Unexpected error: {err}")
```

### 3. 로깅
```python
from ..const import LOGGER

# 디버그 로그
LOGGER.debug(f"Data updated successfully for {self.username}")

# 에러 로그
LOGGER.error(f"Authentication failed: {err}")
```

### 4. 세션 관리
```python
async def async_close_session(self):
    """Close the aiohttp session."""
    if self.session and not self.session.closed:
        await self.session.close()
        self.session = None
```

## 🧪 테스트 작성

### 1. 테스트 구조
```
tests/korea/새서비스명/
├── test_api.py
└── test_device.py
```

### 2. API 테스트 예시
```python
import pytest
from unittest.mock import AsyncMock
from custom_components.korea_incubator.새서비스.api import 새서비스ApiClient

@pytest.mark.asyncio
async def test_login_success():
    mock_session = AsyncMock()
    client = 새서비스ApiClient(mock_session)
    
    result = await client.async_login("username", "password")
    assert result is True
```

## 🎯 번역 기여

번역 파일 위치: `custom_components/korea_incubator/translations/`

지원 언어:
- `ko.json` - 한국어 (기본)
- `en.json` - 영어
- `ja.json` - 일본어

## 📤 Pull Request 가이드라인

### 1. 브랜치 명명
- `feature/서비스명-기능` (예: `feature/kepco-billing`)
- `fix/서비스명-버그` (예: `fix/safety-alert-parsing`)
- `docs/문서타입` (예: `docs/readme-update`)

### 2. 커밋 메시지
```
[서비스명] 기능 설명

- 상세 변경 내용 1
- 상세 변경 내용 2

관련 이슈: #123
```

### 3. PR 체크리스트
- [ ] 테스트 코드 작성/업데이트
- [ ] 문서 업데이트 (필요시)
- [ ] 번역 파일 업데이트 (필요시)
- [ ] 기존 테스트 통과
- [ ] 코드 스타일 준수

## 🐛 버그 리포트

버그를 발견하면 [GitHub Issues](https://github.com/hwajin-me/home-assistant-korea-components/issues)에 다음 정보와 함께 제보해주세요:

- **서비스명**
- **Home Assistant 버전**
- **에러 메시지/로그**
- **재현 단계**
- **예상 동작**

## 💡 기능 제안

새로운 기능이나 서비스 추가 제안은 Issues에서 `enhancement` 라벨로 등록해주세요.

## 📞 문의

- **GitHub Issues**: 버그 리포트, 기능 제안
- **Discussions**: 일반적인 질문, 아이디어 논의
