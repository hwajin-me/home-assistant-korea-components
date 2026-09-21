# 테스트 실행과 회귀 검사

Python 3.13 / Home Assistant 2026.2.3에서 검증합니다.
2026-09-21 전체 결과: **687 passed, 23 skipped, 실패·수집 오류·런타임 경고 0**.
`animal_medical`, `pharmacy`, `llm_api.pharmacy_tool`의 문장/분기 커버리지는 **100%**입니다.
통과와 전체 로직 100% 검증을 혼동하지 않도록 범위를 구분합니다.

```sh
python -m pip install -r test-requirements.txt homeassistant==2026.2.3
python -m pytest tests
python -m pytest tests --cov=custom_components.korea_incubator --cov-branch --cov-report=term-missing
python -m pytest tests/korea/animal_medical --cov=custom_components.korea_incubator.animal_medical --cov=custom_components.korea_incubator.pharmacy --cov=custom_components.korea_incubator.llm_api.pharmacy_tool --cov-branch --cov-fail-under=100
```

설정은 `pyproject.toml`로 일원화했습니다. 잘못된 헤더의 중복 `pytest.ini`를
제거했고, `importlib` 수집으로 서비스별 `test_api.py` 등 파일명 충돌을 방지합니다.
비동기 테스트는 auto 모드이며 미대기 코루틴·미종료 리소스 경고는 실패 처리합니다.

## 외부 요청 격리

기본 실행은 `integration` 표시된 23개 실서버 테스트를 제외합니다.
단위 테스트에서는 aiohttp 및 동기/비동기 curl_cffi의 외부 HTTP 요청을 차단하고
loopback 테스트 서버만 허용합니다. 실서버 검증은 별도로 명시적으로 실행하세요:

```sh
python -m pytest --integration -m integration
```

기본 23개 실서버 테스트는 실행하지 않았습니다. 별도로 실제 인증키를 사용한
의료 3종 API/config flow 검증을 실행했습니다: [실서버 검증 결과](korea/animal_medical/LIVE_VALIDATION.md).
CI의 `tests.yml`은 기본 오프라인 검사를 실행합니다.

## 수정한 기존 문제

- 약국 후속 검토: 재구성 시 옵션에 가려지는 갱신 간격, 여러 약국의 검색 액션 인증키
  선택·해제, 불완전한 빈 페이지, 언로드 실패 시 대화형 API 조기 해제를 수정했습니다.
  손상된 운영시간 캐시는 거부하고 새 조회로 복구합니다. 관련 회귀 테스트 21개를 추가했습니다.
- 수집 오류 10개: 제거된 `pytest.config` 사용을 없애고 공통 collection hook에서
  실서버 테스트 실행 여부를 결정합니다. 수집 복구 후 숨겨졌던 실패도 함께 수정했습니다.
- 날짜: `pytz`를 `tzinfo`로 직접 대입해 발생하던 서울 과거 오프셋과 HA 호스트
  시간대에 따른 날짜 밀림을 수정했습니다. ZoneInfo 기반 한국 날짜를 보존하며
  일반 timestamp, UTC/offset, 소수초, 윤년, 월 단위 값과 연도 경계를 검사합니다.
- KEPCO: aiohttp와 존재하지 않는 RSA helper를 가정한 테스트를 실제 curl_cffi 계약과
  RSAKey로 재작성했습니다. 개인키로 로그인 암호문을 복호화해 UTF-8·패딩을 검사합니다.
  빈 인증정보·누락된 HTML 필드·HTTP/연결 오류·인증 만료 재시도 상한을 검증합니다.
- KEPCO 제품 코드: 인증 오류에만 한 번 재로그인하며 통신/JSON 오류를 인증 만료로
  오인하지 않습니다. 민감한 요청/응답·비밀번호 로그 제거 및 암호학적 난수 패딩 적용.
- HA 초기화: 공통 coordinator에 config_entry를 전달하고 async mock·플랫폼별 기대값·
  세션 소유권 검증을 수정했습니다. 센서 고유 ID는 기존 실제 값을 유지합니다.
- GoodsFlow/GasApp/Arisu: 실제 호출 메서드와 동기/비동기 응답 메서드에 맞춰 mock을
  수정하고, Arisu 파싱 실패는 CSRF 단계가 아닌 청구서 파싱 단계에서 검증합니다.
- Safety Alert: 오래된 JSON/mock 대신 실제 HTML/curl 전송 계약을 검사합니다.
  천 단위 쉼표가 있는 건수를 처리하며, 점검/오류 HTML을 빈 재난문자로 오인하지 않습니다.
- 번역: 동행복권 입력 설명을 보완하고 로그인 오류 키를 HA의 공통 config.error 위치로
  이동했습니다. 영어·한국어·원본 키의 일치를 검사합니다.
