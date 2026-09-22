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
- 이번 달 포함 최근 12개월의 정기분 명세서를 최신순으로 조회해 가장 최근 발행분을 표시합니다. 미발행 시 마지막 정상 조회 값을 유지하며, 실제 조회 장애는 오류로 처리합니다.
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

### 💊 약국 (개별 선택)

- `리뷰`·`사진` 엔터티는 제거하고 `이름` 센서에 실제 상호와 대표 이미지를 표시합니다(동물병원·동물약국도 동일). 카카오가 반환하는 네이버 블로그 사진도 표시할 수 있도록 Kakao/Daum 및 `pstatic.net` CDN의 HTTPS 링크를 허용합니다. 이미지는 파일로 저장하지 않으며 화면 표시 시 CDN에 요청됩니다.
- 옵션에서 `네이버 장소 URL`에 장소 URL/숫자 ID를 입력하거나 `네이버 검색어`로 기관명·주소를 검색해 연결합니다. 자동완성 검색은 최대 10개 후보로 전체 결과가 아니므로 직접 주소를 확인해 선택해야 합니다. 네이버 기본정보·대표 사진·GPS·시간표는 기존 갱신 주기에 함께 조회합니다. URL과 검색어를 비우면 연동을 해제합니다.
- 네이버 상세 시간표는 비공식 웹 응답을 사용하며 접근 제한/구조 변경으로 실패할 수 있습니다. 오류를 로그와 `opening_hours_error`에 표시하고 잘못된 영업/휴무 판정을 막기 위해 운영 여부는 unknown으로 처리합니다. 2026-09-21 문서 요청 헤더를 보완한 뒤 쿠키 저장을 끈 `aiohttp` 세션에서 대표 사진·영업/휴게시간·추석 휴무의 직접 조회를 검증했습니다. 로그인 쿠키·일회성 토큰·브라우저 실행은 필요하지 않았습니다. 모든 환경의 지속적인 성공을 보장하지는 않습니다. [분석 및 검증 기록](tests/korea/animal_medical/NAVER_RESEARCH.md)
- 자동화용 `binary_sensor`: `현재 영업 중`, `운영시간 조회 문제`를 제공합니다. 시간 미확인은 `unknown`이며, 기존 운영 상태 enum 센서도 유지합니다.
- `다음 운영 시작 시각` / `다음 운영 종료 시각`은 확인된 시간표의 다음 경계를 timestamp로 제공합니다(휴게 시작·재개 포함). 확인된 미래 일정이 없으면 unknown입니다. `다음 휴무일`은 date, `정보 갱신`은 timestamp 타입입니다.
- 같은 기기에 읽기 전용 `영업시간` 캘린더를 제공합니다. 카카오가 제공하는 날짜별 시간표만 표시하며, 휴게시간을 제외한 실제 영업 구간을 일정으로 분리합니다. 자정 넘김·24시간 영업을 지원하며 주간 시간표를 미래 날짜로 반복 추정하지 않습니다. 캘린더 조회는 추가 API를 호출하지 않습니다.
- 설정 그룹 이름은 `약국`, 기기 이름은 실제 약국명이며 센서 이름은 한국어입니다.
- 기기당 16개 엔터티(센서 13개·이진 센서 2개·캘린더 1개)입니다. `이름`, `위치`, `연락처`, `상세정보`, `영업시간`, `영업 시작시간`, `영업 종료시간`, `휴게시간`, `정보 갱신`, `다음 휴무일`에 관련 정보를 묶습니다. `위치`는 GPS와 카카오·네이버 지도 URL을 함께 표시합니다. 영업/휴게시간은 오늘의 구간이며 자정을 넘으면 `익일`을 표시합니다. 기존 `다음 운영 시작/종료`는 미래의 상태 전환 시각으로 별도 유지합니다.
- 재로드 시 통합된 옛 개별 필드 엔터티와 중복 이진 센서 등록을 제거합니다. 기록 데이터베이스는 삭제하지 않지만 해당 엔터티를 참조하는 자동화·카드는 수정해야 합니다.
- `다음 휴무일`은 오늘을 포함한 확인된 완전 휴무일 중 가장 가까운 날짜이며 `closed_dates` 속성에 전체 목록을 표시합니다. `korea_incubator.check_medical_closed_day` 액션에 `config_entry_id`와 `date`(예: `2026-09-27`)를 전달하면 `is_closed`와 `status`를 응답합니다. 전날 야간 영업이 이어지면 완전 휴무가 아닙니다. 시간표 밖의 날짜·조회 실패는 `unknown`이며 공휴일을 추정하지 않습니다. API 추가 호출은 없습니다.
- 기존 지역별 **약국 수** 센서를 선택한 **약국 한 곳의 현재 운영 상태**로 변경했습니다.
- 공공데이터 API 키, 시도·시군구, 약국명, 도로명주소로 검색하고 이전/다음 페이지에서 선택합니다. API가 주소 검색을 지원하지 않아 주소 필터는 현재 결과 페이지에 적용됩니다.
- 약국 고유 ID(HPID)로 상세정보를 갱신합니다. 카카오 장소는 정확한 단일 매칭 시 자동 선택하며, 모호하면 목록·페이징으로 직접 선택합니다.
- 상태는 `open` / `closed` / `break`이며 날짜별 운영시간 미확인 시 `unknown`입니다. 요일별 공공데이터만으로 공휴일·휴게시간을 추정하지 않습니다.
- 속성: GPS, 주소·전화, 요일별 운영시간, 카카오 운영시간, 마지막/다음 갱신 시각 및 누락 방지를 위한 전체 `api_record`.
- 갱신 간격은 설정/옵션에서 1~1440분(기본 60분). 재시작 시 남은 간격을 유지하며 재로드·설정 변경 시 즉시 갱신합니다.
- **기존 지역 설정은 통합구성요소 메뉴 → 재구성에서 약국 한 곳을 선택해야 합니다.** 등록 성공 후 해당 항목의 옛 개수 엔터티 등록만 제거합니다(기록 데이터베이스는 삭제하지 않습니다).
- 기존 `search_pharmacy` 액션은 호환성을 유지합니다. 지역 검색 결과는 현재 영업 중인 약국만을 의미하지 않습니다.
- 여러 약국 등록 시 액션의 `config_entry_id`로 사용할 인증키의 설정 항목을 지정할 수 있습니다. 생략 시 첫 번째 로드된 항목을 사용하며 언로드된 항목의 키는 사용하지 않습니다.
- 상세 API에서 빠지는 `dutyEtc` 안내사항은 목록 API를 HPID로 대조해 병합합니다. 현재 상태는 카카오 날짜별 시간표 기준이며 공공 안내문과 다른 경우에도 원본(`public_notes`, `api_record`)을 보존합니다.
- 2026-09-21 실제 인증키로 검색·페이지 이동·상세 API와 약국 config flow 자동 매칭→등록 결과→센서 갱신을 검증했습니다. 공공데이터와 카카오는 실제 현장 운영 여부를 보장하지 않습니다.

### 🐾 동물병원 / 동물약국

- 동물약국은 하나의 `동물약국` 그룹, 동물병원은 하나의 `동물병원` 그룹 아래에 기관별 기기가 바로 나열됩니다. 상호별 하위 그룹은 만들지 않습니다.
- 업데이트 후 재시작하면 기존 활성 설정이 자동으로 합쳐집니다. 기기·엔티티 ID, 기관별 API 키·옵션·저장된 조회 데이터는 유지됩니다. 비활성화한 설정은 활성화할 때 이전됩니다.
- 추가한 기관은 기존 서비스 그룹에 들어갑니다. 재설정·옵션에서는 대상 기관을 선택하고, 개별 기관을 제거하려면 해당 기기를 삭제합니다.

- 날짜별 시간표에 명시된 `임시휴무`, `추석 휴무`, `설 연휴 휴진` 등도 다음 휴무일에 반영합니다. `closed_day_details` 속성과 휴무일 조회 액션의 `closure_reason`에 사유를 표시합니다. 공휴일이라는 사실만으로 휴무를 추정하지 않으며, 카카오가 제공하지 않은 미래 날짜나 모호한 안내문은 알 수 없음으로 유지합니다.

- 약국과 동일한 이진 상태·다음 운영 경계 센서 및 날짜/시각 타입을 제공합니다. 기존 운영 상태 enum 센서의 고유 ID와 `open`/`closed`/`break` 값은 유지합니다.
- 각 기기에 `영업시간` 캘린더를 제공합니다. 일반 약국과 동일하게 날짜별 영업 구간을 표시하며 휴게시간·휴무일은 영업 일정에서 제외합니다. 시간표를 확인할 수 없으면 캘린더를 사용 불가로 표시합니다. 재로드 후 Home Assistant 캘린더 화면/카드에서 선택할 수 있습니다.
- 설정 그룹 이름은 `동물병원` / `동물약국`, 기기 이름은 실제 상호입니다. 약국과 동일한 16개 엔터티로 통합하며 원본 25개 필드와 장소 상세정보는 속성으로 보존합니다. 카카오 접두어 없이 일반 정보로 표시합니다.
- 네이버 연결 시 확인된 네이버 날짜별 시간표·명절 휴무가 카카오 시간표보다 우선하며, 해당 일정은 현재 상태·다음 휴무일·휴무일 조회 액션·캘린더에 동일하게 반영합니다. 범위를 벗어난 날은 일반 주간 시간표로 무한 반복 추정하지 않습니다.
- 기존 기기와 운영 상태 센서의 고유 ID를 유지합니다. 사용자가 직접 설정한 표시 이름은 덮어쓰지 않습니다. 새로운 응답 필드도 상세정보의 원본 속성에 보존합니다.
- 행정안전부 [동물병원](https://www.data.go.kr/data/15154952/openapi.do) 및 [동물약국](https://www.data.go.kr/data/15155272/openapi.do) 인허가 정보 연동
- 설정에서 해당 API에 활용신청한 인증키를 입력하고 기관 종류 선택 (인코딩/디코딩 키 지원)
- **도로명주소 포함 검색**이 기본이며, **7자리 개방자치단체코드**로도 검색 가능
- 코드 확인: 각 API의 참고문서 **개방자치단체코드_영업상태코드.xlsx**, [행정표준코드 다운로드](https://www.code.go.kr/etc/codeFullDown.do). 법정동코드와 구분해서 입력
- 목록은 페이지당 최대 100건을 자동 요청하며 **이전/다음/다시 검색** 지원. 기관 한 곳당 설정 항목 하나 생성
- 기관 선택 후 **카카오 장소 자동 검색**. 전체 후보가 한 페이지이고 이름 + 주소 또는 전화번호가 일치하는 유일 후보만 자동 연결. 그 외에는 주소·전화번호가 표시된 목록의 **이전/다음 페이지**에서 직접 선택하거나 검색어 수정
- 검색 요청마다 gate-token을 새로 발급받아 서명된 URL과 `x-kmap-captcha-token` 헤더로 조회. 사용자 쿠키나 고정 토큰을 저장하지 않음
- 선택한 기관의 인허가 정보·카카오 운영시간과 주소·전화·인허가일·폐업일 등 상세 속성을 **설정한 분 단위 주기로 갱신** (1~1440분, 기본 60분; 최초 설정 및 옵션에서 변경)
- 마지막 성공한 API 조회 시각과 데이터를 저장하여 **재시작해도 남은 주기를 유지**. 이미 주기가 지났거나 캐시가 유효하지 않으면 즉시 조회
- **reload 및 설정 저장은 즉시 재조회**하며, 같은 옵션을 다시 저장해도 재조회. API 실패는 마지막 성공 시각을 변경하지 않음
- 센서에 마지막 성공 조회 시각·다음 정기 조회 예정 시각·갱신 주기 표시. 오류 발생 중에는 다음 예정 시각을 알 수 없음으로 표시
- HTTP 상태·API 코드·서버 오류 메시지를 설정 화면과 로그에 표시 (인증키 마스킹). 휴업/재개업/인허가취소·우편번호·상태코드도 개별 속성 제공
- 개별 상세 API가 없어 기관명/자치단체코드 조건의 목록에서 관리번호로 식별. 이름 변경 시 자치단체 전체 목록을 자동 페이징하여 재탐색
- 센서 상태는 `open`(운영 중), `closed`(운영 종료/휴무), `break`(휴게시간). 카카오의 날짜별 운영시간을 **Asia/Seoul 현재 시각 기준으로 매분 계산**하며 추가 API 호출은 하지 않음. 자정 넘는 영업·연말 날짜 전환 지원
- 운영시간이 없거나 해석 불가·조회 실패·날짜 범위가 만료된 경우 **알 수 없음** (`open_now: null`). 최초 새벽 조회에서 전날 야간 운영시간이 없는 경우에도 추정하지 않음. 카카오 표시 시간표 기반으로 실제 임시휴무·현장 상황까지 보장하지 않음
- 인허가상의 영업상태는 `operating_status` 속성으로 별도 유지. 공공데이터는 API 명세상 2일 전 기준으로 매일 현행화
- **EPSG:5174** 원본 좌표와 함께 WGS84 `latitude`/`longitude` 제공. 공공 좌표 누락 시 연결된 카카오 GPS 사용. 양쪽 모두 없거나 잘못된 경우 `location_available: false` 표시
- 기관별 전체 25개 필드를 개별 속성과 `api_record`로 제공. `opening_hours`·`opening_schedule`·`opening_hours_updated`·`opening_hours_error`·`kakao_details`에 운영시간과 장소 상세 노출
- 기존 항목 또는 잘못 연결된 장소는 통합 항목의 **재구성(Reconfigure)** 에서 다시 자동 검색/선택. 기존 카카오 미연결 항목의 현재 상태는 알 수 없음
- 카카오 웹 API는 비공식이므로 구조 변경·접근 제한으로 중단될 수 있음. 검색 실패는 설정 화면/로그에 표시하며 CAPTCHA가 요구되면 우회하지 않음
- API 오류나 기관 누락 시 센서를 사용 불가로 표시하고 다음 갱신에서 재시도. 인증키 만료 시 재인증 지원

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

하나의 **안전알림** 서비스 아래 지역별 기기가 바로 표시됩니다. 주소별 접이식 그룹은
생성하지 않습니다. 통합의 **항목 추가 → 안전알림**으로 지역을 추가하고, 해당 지역의
기기를 삭제하면 그 지역 설정도 제거됩니다. 기존 주소 그룹은 업데이트 후 자동 제거되며
지역 기기와 엔티티는 유지됩니다.
업데이트 후 Home Assistant를 재시작하면 기존의 활성 지역 설정이 자동으로 합쳐집니다.
기존 지역 기기와 엔티티 ID는 유지되며, 이전 버전에서 생성한 빈 상위 기기는 정리됩니다.
사용자가 비활성화한 설정은 활성화할 때 이전됩니다. 실행 중인 다른 지역 설정은
재시작 시 이전하므로, 최초 적용에는 전체 재시작을 권장합니다.

Safety Alert lists regional devices directly under one service, without address groups.
Add a region through Add entry → Safety Alert; delete its device to remove the region.
Existing address subentries are automatically flattened. Restart Home Assistant
after updating to migrate existing enabled regions automatically while retaining their
device and entity IDs. Disabled entries migrate when enabled. Adding or removing a
region reloads the service; a temporary API failure in one region does not block others.
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
- **도시가스사 코드**: 가스앱 API 요청의 `X-Company` 값 (예: 서울도시가스 `1`, 예스코 `6`)
- **사용계약번호**: 가스 사용계약번호

#### 🗺️ 카카오맵
- **REST API 키 또는 웹 쿠키**: Kakao Developers REST API 키나 `map.kakao.com` 길찾기 요청의 Cookie 헤더 중 하나
- **경로명**: 식별을 위한 경로 이름 (예: "집↔회사")
- **좌표계**: WGS84 또는 WCONGNAMUL 선택
- **출발지 좌표**: X(경도), Y(위도)
- **도착지 좌표**: X(경도), Y(위도)

### 3. 기존 항목 재설정

**설정 → 기기 및 서비스 → Korea → 해당 항목의 ⋮ 메뉴 → 재설정**에서 기존 항목을 삭제하지 않고 설정을 변경할 수 있습니다. 기존 설정이 입력되어 있으며, 완료하면 변경 사항을 저장하고 다시 불러옵니다. API 검증에 실패하거나 중간에 취소하면 기존 설정은 유지됩니다.

- 한전·가스앱·아리수·동행복권·CJ대한통운은 동일한 계정이나 고객번호의 인증 정보를 갱신합니다. 다른 계정은 새 항목으로 추가하세요.
- 지역·학교·날씨·유가·경로 설정은 기존 설정 절차에 따라 변경합니다.
- 대중교통은 기존 정류장·지하철 항목 중 유지할 항목을 선택한 뒤 새 항목을 추가할 수 있습니다.
- 안전알림은 변경할 지역을 선택하며, 다른 지역은 유지됩니다.
- 굿스플로우는 토큰을 교체해도 기존 기기·엔티티 식별자를 유지합니다.
- 동물병원·동물약국·약국은 API 키, 검색 지역, 기관, 조회 주기를 변경하고 카카오·네이버 장소 연결을 검토한 뒤 저장합니다. 기관을 변경해도 기존 엔티티 ID는 유지하고 이전 기관의 장소 연결은 제거합니다.
- 입력 오류나 일시적인 API 장애가 발생하면 수정한 값을 유지하므로 다시 입력할 필요 없이 재시도할 수 있습니다.
- 에어코리아·기상청 날씨·지진은 API 응답을 검증한 뒤 저장합니다. 정상 응답에 자료가 없는 경우는 오류로 처리하지 않습니다.
- 변경 후 선택에서 제외된 측정소·지역·학급·교통 항목의 엔티티를 정리합니다. 유지한 항목과 다른 설정 항목의 엔티티는 보존합니다.

Reconfiguration is available for every service in the integration. It validates changes before saving, keeps the existing config entry, and reloads it after completion. Medical entries allow editing credentials, institution selection, polling interval, and both map links. Account-based services require the same account/customer identity; add a new entry for a different account. Removed selections are cleaned up after successful platform setup, while retained and disabled entities remain registered.

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
- 최근 배송 이벤트 센서의 상태값은 `none`, `new_delivery`, `status_changed`, `tracking_updated`로 정규화되며 `status_key`, `status_code`, `previous_status_key`를 자동화에 사용 가능
- 사람이 읽거나 TTS로 방송할 문장은 `announcement` 속성으로 제공

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
| 동행복권 | 1시간 | 예치금 조회 및 로또 6/45·연금복권 720+ 자동 구매 |

## 🎰 동행복권 자동 구매

통합 구성요소 추가에서 **동행복권 (로또/연금복권)** 을 선택해 동행복권 아이디와 비밀번호를 등록합니다. 예치금 센서가 만들어진 뒤, 자동화에서 아래 서비스를 호출할 수 있습니다. 구매 금액은 계정 예치금에서 차감되며, 온라인 판매 시간과 동행복권의 구매 한도를 그대로 따릅니다.

```yaml
service: korea_incubator.buy_pension_720_auto
target:
  entity_id: sensor.donghaeng_lottery_계정아이디_balance
data:
  games: 5
```

로또 6/45 자동 구매에는 `korea_incubator.buy_lotto_645_auto`를 사용합니다. 결제 응답이 불명확하게 끝난 경우에는 서비스를 다시 호출하지 말고 동행복권 웹사이트의 구매내역을 먼저 확인하세요.

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
