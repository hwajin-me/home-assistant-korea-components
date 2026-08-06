# 🇰🇷 Korea Incubator

> 대한민국에서만 사용할 수 있는 Home Assistant 통합 구성요소

[![hacs][hacsbadge]][hacs]
[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)

한국전력, 아리수, 안전알림서비스 등 대한민국에서만 사용할 수 있는 다양한 서비스를 Home Assistant에서 모니터링할 수 있게 해주는 통합 구성요소입니다.

![Korea Services](https://github.com/hwajin-me/home-assistant-korea-components/blob/main/.github/images/services-overview.png?raw=true)

## 📋 지원 서비스

### ⚡ 한국전력공사 (KEPCO)
- **전력 사용량** 실시간 모니터링
- **전기요금** 예상 및 지난달 요금 조회
- **사용량 통계** 데이터 제공

### 💧 아리수 (서울시 상수도)
- **수도요금** 조회
- **사용량** 정보 확인
- **고객번호** 기반 인증

### 🚨 안전알림서비스 (행정안전부)
- **재난문자** 실시간 수신
- **지역별** 안전알림 필터링
- **시도/시군구/읍면동** 단위 설정 가능

### 🚛 굿스플로우 (택배조회)
- **택배 배송현황** 통합 조회
- **여러 택배사** 지원
- **실시간 배송 추적**

### 📦 CJ대한통운 (CJ O-NE 배송조회)
- **휴대폰 문자 인증**으로 CJ O-NE 계정 연결
- **배송대기/배송중 전체 항목**을 택배 한 건당 Sensor 하나로 자동 생성
- 각 Sensor Attribute로 상품·송수하인·기사·점소·예정시간·운임·반품 여부와 배송 상세 타임라인 전체 제공
- **최근 2일 배송완료 건별 Sensor**와 **최근 5일 배송완료 건수 Counter** 제공
- **배송 상태 변경 이벤트 문구**와 access token 자동 갱신 지원

### 🏠 가스앱 (도시가스)
- **가스 사용량** 모니터링
- **가스요금** 정보 조회
- **계약번호** 기반 인증

### 🗺️ 카카오맵 (길찾기)
- **실시간 교통정보** 기반 소요시간
- **출발지→목적지** 경로 정보
- **WGS84/WCONGNAMUL** 좌표계 지원

## 🚀 설치 방법

### HACS를 통한 설치 (권장)

1. **HACS** 메뉴로 이동
2. **통합 구성요소** 선택
3. 우측 상단 **⋮** 메뉴 → **사용자 지정 리포지토리**
4. 다음 정보 입력:
   - **리포지토리**: `hwajin-me/home-assistant-korea-components`
   - **카테고리**: `Integration`
5. **Korea Incubator** 검색 후 설치
6. **Home Assistant 재시작**

### 수동 설치

1. 이 리포지토리를 다운로드
2. `custom_components/korea_incubator` 폴더를 Home Assistant의 `custom_components` 디렉토리에 복사
3. Home Assistant 재시작

## ⚙️ 설정 방법

### 1. 통합 구성요소 추가

**설정** → **기기 및 서비스** → **통합 구성요소 추가** → **"Korea Incubator"** 검색

### 2. 서비스별 설정

#### ⚡ 한국전력공사 (KEPCO)
- **사용자 ID**: 한전 홈페이지 로그인 ID
- **비밀번호**: 한전 홈페이지 로그인 비밀번호

#### 💧 아리수 (서울시 상수도)
- **고객번호**: 수도요금 고지서의 고객번호
- **고객명**: 계약자 성명

#### 🚨 안전알림서비스
- **시도**: 거주 지역의 시/도 선택
- **시군구**: 거주 지역의 시/군/구 선택 (선택사항)
- **읍면동**: 거주 지역의 읍/면/동 선택 (선택사항)

#### 🚛 굿스플로우 (택배조회)
- **API 토큰**: 굿스플로우 API 키

#### 📦 CJ대한통운 (CJ O-NE 배송조회)
- **휴대폰 번호** 입력 후 문자로 받은 인증번호 입력
- 배송대기/배송중 배송은 개수 제한 없이 건별 Sensor로 표시
- 배송완료 건은 완료 후 48시간 동안 건별 Sensor로 표시
- 배송완료 Counter는 최근 5일 내 완료 건을 집계하며 주기적으로 감소
- 옵션에서 **조회 주기(3~30분)** 설정

#### 🏠 가스앱
- **토큰**: 가스앱 인증 토큰
- **회원 ID**: 가스앱 회원 ID
- **사용계약번호**: 가스 사용계약번호

#### 🗺️ 카카오맵
- **경로명**: 식별을 위한 경로 이름 (예: "집↔회사")
- **좌표계**: WGS84 또는 WCONGNAMUL 선택
- **출발지 좌표**: X(경도), Y(위도)
- **도착지 좌표**: X(경도), Y(위도)

## 📊 제공되는 센서

### ⚡ KEPCO 센서
```
sensor.kepco_current_usage        # 현재 사용량 (kWh)
sensor.kepco_last_month_bill      # 지난달 요금 (원)
sensor.kepco_predicted_bill       # 예상 요금 (원)
```

### 💧 아리수 센서
```
sensor.arisu_water_bill          # 수도요금
sensor.arisu_usage_amount        # 사용량
```

### 🚨 안전알림 센서
```
sensor.safety_alert_count        # 알림 개수
binary_sensor.safety_alert_new   # 새 알림 여부
```

### 🚛 굿스플로우 센서
```
sensor.goodsflow_packages        # 택배 현황
```

### 📦 CJ대한통운 센서
- 배송 요약, 배송대기/배송중 전체 목록, 최근 5일 배송완료 Counter
- 택배 건별 Sensor의 상태값은 현재 배송상태이며 Attribute에 상품명·운송장·상태 코드/내용·송수하인·위치·일시·기사·점소·배송예정시간·운임·반품 여부·상세 타임라인·원본 응답을 포함
- 배송완료 Counter의 `deliveries`에는 수령인 관계, 완료 안내, 서버가 제공한 경우 배송사진 상대 경로도 포함
- 최근 배송 이벤트 센서 (`announcement` 속성을 자동화/TTS에 사용 가능)

### 🏠 가스앱 센서
```
sensor.gasapp_usage             # 가스 사용량
sensor.gasapp_bill              # 가스요금
```

### 🗺️ 카카오맵 센서
```
sensor.kakaomap_duration        # 소요시간 (분)
sensor.kakaomap_distance        # 거리 (m)
sensor.kakaomap_traffic_state   # 교통상황
```

## 🎨 Lovelace 카드 예제

### 전력 사용량 카드
```yaml
type: entities
title: 전력 사용량
entities:
  - entity: sensor.kepco_current_usage
    name: 현재 사용량
  - entity: sensor.kepco_last_month_bill
    name: 지난달 요금
  - entity: sensor.kepco_predicted_bill
    name: 예상 요금
```

### 안전알림 카드
```yaml
type: conditional
conditions:
  - entity: binary_sensor.safety_alert_new
    state: "on"
card:
  type: markdown
  content: |
    ## 🚨 새로운 안전알림
    {{ states('sensor.safety_alert_count') }}건의 알림이 있습니다.
```

### 교통정보 카드
```yaml
type: glance
title: 교통정보
entities:
  - entity: sensor.kakaomap_duration
    name: 소요시간
  - entity: sensor.kakaomap_distance
    name: 거리
  - entity: sensor.kakaomap_traffic_state
    name: 교통상황
```

## 🔄 업데이트 주기

| 서비스 | 업데이트 주기 | 비고 |
|--------|-------------|------|
| 한전 (KEPCO) | 15분 | 로그인 세션 관리 |
| 아리수 | 30분 | 요금 정보 중심 |
| 안전알림 | 5분 | 실시간 알림 |
| 굿스플로우 | 15분 | 배송 상태 추적 |
| CJ대한통운 | 30분 (3~30분 설정 가능) | 진행 및 최근 2일 완료 건별 Sensor, 최근 5일 완료 Counter, 토큰 자동 갱신 |
| 가스앱 | 1시간 | 사용량 정보 |
| 카카오맵 | 1분 | 실시간 교통정보 |

## 🐛 문제 해결

### 로그인 실패
- 웹사이트에서 직접 로그인이 되는지 확인
- 특수문자가 포함된 비밀번호는 URL 인코딩 필요할 수 있음
- 2차 인증(OTP) 설정된 계정은 지원하지 않음

### 데이터 업데이트 안됨
- Home Assistant 로그에서 에러 메시지 확인
- 네트워크 연결 상태 점검
- API 서비스 장애 여부 확인

### 좌표 변환 오류 (카카오맵)
- WGS84 좌표 범위: 경도 124-132, 위도 33-43
- WCONGNAMUL 좌표는 카카오맵에서 확인 가능

## 📋 요구사항

- **Home Assistant** 2023.1.0 이상
- **Python** 3.11 이상
- **인터넷 연결** (각 서비스 API 접근)

## 🤝 기여하기

기여를 환영합니다! [CONTRIBUTING.md](CONTRIBUTING.md)를 참고해주세요.

### 새로운 서비스 추가
1. Fork this repository
2. Create feature branch: `git checkout -b feature/새서비스명`
3. Commit changes: `git commit -am '[새서비스명] 기능 추가'`
4. Push to branch: `git push origin feature/새서비스명`
5. Submit pull request

## 📜 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 참고하세요.

## ⚠️ 면책조항

- 이 프로젝트는 각 서비스의 공식 API가 아닌 웹 스크래핑 방식을 사용합니다
- 각 서비스 제공업체의 정책 변경에 따라 동작하지 않을 수 있습니다
- 개인정보는 Home Assistant 내부에서만 사용되며 외부로 전송되지 않습니다
- 사용자의 책임 하에 이용해주세요

## 🙏 감사의 말

이 프로젝트는 다음 서비스들의 데이터를 활용합니다:
- 한국전력공사
- 서울특별시 상수도사업본부
- 행정안전부 국민재난안전포털
- 카카오맵

---

**Made with ❤️ for Korean Home Assistant Users**

[hacs]: https://github.com/hacs/integration
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/hwajin-me/home-assistant-korea-components.svg?style=for-the-badge
[releases]: https://github.com/hwajin-me/home-assistant-korea-components/releases
[commits-shield]: https://img.shields.io/github/commit-activity/y/hwajin-me/home-assistant-korea-components.svg?style=for-the-badge
[commits]: https://github.com/hwajin-me/home-assistant-korea-components/commits/main
[license-shield]: https://img.shields.io/github/license/hwajin-me/home-assistant-korea-components.svg?style=for-the-badge
