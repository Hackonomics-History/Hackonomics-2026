# PR 리뷰 문서: Hackonomics-2026 — gRPC 인증 어댑터, 포트 추상화, CI/CD

**날짜:** 2026-04-06
**브랜치:** `dev` → `main`
**저장소:** `Hackonomics-History/Hackonomics-2026`
**커밋:** `5ec07c1` (feat), `1639f17` (fix)

---

## 1. 개요

이번 PR은 Django 서비스가 Central-Auth 서비스를 HTTP 대신 **gRPC를 통해 호출**할 수 있도록 전송 계층을 추상화합니다.

### 핵심 목적

1. **전송 계층 추상화 (`AuthServiceAdapter` Protocol)** — HTTP와 gRPC 어댑터가 동일한 Protocol을 구현하도록 강제합니다. 모든 호출자는 전송 방식에 무관하게 동작합니다.

2. **gRPC 클라이언트 어댑터 (`GrpcAuthAdapter`)** — Central-Auth의 `auth.v1.AuthService` gRPC 엔드포인트를 호출합니다. 서킷브레이커(임계값 5, 복구 30초)와 재시도(최대 2회, 0.3초 대기)를 내장합니다.

3. **gRPC 오류 분류 (`grpc_errors.py`)** — 인프라 오류(UNAVAILABLE, DEADLINE_EXCEEDED)와 도메인 오류(UNAUTHENTICATED, NOT_FOUND 등)를 구분합니다. 인프라 오류만 서킷을 트립하고 재시도합니다.

4. **기능 플래그 전환 (`adapter_factory.py`)** — `CENTRAL_AUTH_USE_GRPC` 환경변수로 HTTP↔gRPC를 런타임 전환합니다. 기본값은 `false`(HTTP)로 하위 호환성을 유지합니다.

5. **테스트 스위트 확장 (12개 신규 테스트)** — 어댑터 팩토리, gRPC 어댑터, 서킷브레이커 gRPC 통합, 오류 분류 테스트를 추가합니다.

### 주요 변경 파일 수

| 구분 | 수량 |
|------|------|
| 신규 파일 | 12개 |
| 수정 파일 | 15개 |
| 총 삽입 | +1,348줄 |
| 총 삭제 | -56줄 |

---

## 2. 보안 검토 결과

**검토 도구:** `security-reviewer` 에이전트
**최종 결과: ✅ PASS (HIGH 항목 문서화 조치 완료)**

### 발견 사항

| 심각도 | 항목 | 파일 | 조치 |
|--------|------|------|------|
| CRITICAL | 없음 | — | — |
| HIGH | `grpc.insecure_channel` 사용 — 메타데이터 평문 전송 | `authentication/adapters/django/grpc_channel.py:55` | **조치 완료:** 인트라-클러스터 전용임을 상세 주석으로 문서화. 클러스터 외부 통신 시 TLS/mTLS 전환 가이드 첨부 |
| MEDIUM | CI 워크플로우에 테스트 DB 비밀번호 평문 기재 | `.github/workflows/deploy.yml:30` | 에페머럴 CI 러너에서만 사용되는 테스트 전용 값으로, 프로덕션에 영향 없음. 허용 수준으로 판단. 향후 `${{ secrets.TEST_DB_PASSWORD }}`로 이관 권고 |
| MEDIUM | `CENTRAL_AUTH_SERVICE_KEY` 시작 시 유효성 검증 부재 | `grpc_auth_service.py:57` | 향후 `AppConfig.ready()`에서 `ImproperlyConfigured` 발생 권고. 현재는 첫 RPC 호출 시 오류 발생 |
| LOW | 서킷브레이커 복구 타임아웃 30초 고정 | `grpc_auth_service.py:101` 외 | 설정 외부화 권고 (settings.py). 현재 값은 일반적 시나리오에서 적정 수준 |

### 보안 설계 긍정 사항

- **서킷브레이커가 도메인 오류를 트리핑하지 않음** — `is_grpc_infrastructure_error()`가 UNAUTHENTICATED, PERMISSION_DENIED 등 도메인 오류를 정확히 제외. 잘못된 자격증명으로 서킷을 오픈시키는 공격 불가 ✓
- **어댑터 팩토리 런타임 조작 불가** — `CENTRAL_AUTH_USE_GRPC`는 Django 설정으로 스타트업 시 1회 파싱. HTTP를 통한 동적 전환 경로 없음 ✓
- **X-Request-ID 전파** — 요청 컨텍스트 외부(Celery, 관리 커맨드)에서는 빈 문자열로 안전하게 처리 ✓
- **테스트 픽스처** — 모든 테스트 자격증명(`"test-key"`, `"acc"`, `"ref"`)은 상징적 값으로 실제 비밀 아님 ✓

---

## 3. 테스트 및 커버리지

**검증 방법:** `venv/bin/python3 -m pytest tests/ -q`

| 테스트 파일 | 결과 | 비고 |
|-------------|------|------|
| `tests/authentication/test_adapter_factory.py` | ✅ PASS | 신규 |
| `tests/authentication/test_grpc_auth_adapter.py` | ✅ PASS | 신규 |
| `tests/authentication/test_jwks_middleware.py` | ❌ FAIL (1건) | **기존 테스트** — 이번 PR과 무관한 JWKS 캐시 로직 회귀 |
| `tests/common/test_circuit_breaker_grpc.py` | ✅ PASS | 신규 |
| `tests/common/test_grpc_errors.py` | ✅ PASS | 신규 |
| 기타 기존 테스트 | ✅ PASS | — |
| **전체 합계** | **74 PASS / 1 FAIL** | — |

> **FAIL 분석:** `TestFetchAndCacheJwks.test_caches_fresh_jwks_on_success`는 이번 PR 변경 대상 파일과 무관한 기존 JWKS 미들웨어 테스트입니다. `test_jwks_middleware.py:46`에서 캐시 호출 인덱스 참조 오류 발생 — 별도 수정 필요.

**커버리지:** `pytest-cov` 미설치 환경에서 정확한 측정 불가. 신규 12개 테스트가 gRPC 어댑터와 서킷브레이커 핵심 경로를 커버함을 코드 검토를 통해 확인.

---

## 4. 주요 코드 변경점

### 4-1. 포트 추상화 (`authentication/adapters/ports.py`)

```python
@runtime_checkable
class AuthServiceAdapter(Protocol):
    def login(self, email, password, device_id, remember_me) -> dict: ...
    def signup(self, email, password) -> dict: ...
    def google_login(self, email, device_id) -> dict: ...
    def refresh(self, refresh_token) -> dict: ...
    def logout(self, refresh_token) -> None: ...
```

HTTP 어댑터와 gRPC 어댑터가 상속 없이 구조적 서브타이핑으로 이 Protocol을 만족합니다.

### 4-2. gRPC 어댑터 (`authentication/adapters/django/grpc_auth_service.py`)

**핵심 설계 결정:**
- 서킷브레이커와 재시도는 **인스턴스 메서드가 아닌 모듈 함수 레벨**에 적용 → 어댑터 인스턴스 간 상태 공유
- `_build_metadata()`: `x-service-key` + `x-request-id` 메타데이터를 모든 RPC에 자동 주입
- `_grpc_error_to_business()`: 인프라 오류는 ERROR 레벨, 도메인 오류는 WARNING 레벨로 차등 로깅

```
Login/Signup/... 호출
  → circuit_breaker 데코레이터 (UNAVAILABLE/TIMEOUT만 카운트)
    → retry_transient_grpc 데코레이터 (최대 2회, 0.3초)
      → gRPC stub 호출
```

### 4-3. gRPC 오류 분류 (`common/resilience/grpc_errors.py`)

| gRPC 코드 | 분류 | 서킷 트립 | 재시도 |
|-----------|------|-----------|--------|
| UNAVAILABLE | 인프라 | ✓ | ✓ |
| DEADLINE_EXCEEDED | 인프라 | ✓ | ✓ |
| UNAUTHENTICATED | 도메인 | ✗ | ✗ |
| ALREADY_EXISTS | 도메인 | ✗ | ✗ |
| NOT_FOUND | 도메인 | ✗ | ✗ |
| INVALID_ARGUMENT | 도메인 | ✗ | ✗ |
| PERMISSION_DENIED | 도메인 | ✗ | ✗ |

### 4-4. 어댑터 팩토리 (`authentication/adapters/django/adapter_factory.py`)

- `CENTRAL_AUTH_USE_GRPC=true` → `GrpcAuthAdapter` 반환
- `CENTRAL_AUTH_USE_GRPC=false` (기본) → 기존 `CentralAuthAdapter` (HTTP) 반환
- gRPC 모듈은 `CENTRAL_AUTH_USE_GRPC=true`일 때만 지연 임포트 → `grpcio` 미설치 환경에서 HTTP 어댑터 정상 동작

### 4-5. CI/CD 파이프라인 (`.github/workflows/deploy.yml`)

```
Push/Tag → pytest (PG+Redis 서비스 컨테이너) → docker buildx push → yq patch values.yaml → git push
```

- Postgres 16-alpine / Redis 7-alpine 서비스 컨테이너 사용
- `cpu-only torch` 사전 설치로 빌드 시간 최적화

---

## 5. 참조 링크

- 변경 파일 목록: `git show --stat dev`
- 연관 PR: [Central-Auth gRPC 서버](../../../Central-auth/docs/review/PR_20260406_grpc_server_resilience.md)
- 연관 PR: [Hackonomics-Infra GitOps](../../../Hackonomics-Infra/docs/review/PR_20260406_gitops_helm_argocd.md)
