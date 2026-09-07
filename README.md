# 하이브리드 AI 뉴스 중립성 분석 플랫폼

뉴스 기사를 자동으로 수집하고, 클라우드 LLM(Gemini, GPT)과 로컬 LLM(LoRA 파인튜닝 모델)을 함께 사용해
기사·댓글의 중립성을 분석하는 플랫폼입니다. 진로탐색학점제 프로젝트로 개발했습니다.

## 아키텍처

```
                ┌─────────────────────────────────────────────┐
                │                Docker Compose                │
                │                                             │
 RSS 피드 ──────▶  ai-worker (Python, APScheduler)            │
                │   크롤링 → 클러스터링 → AI 분석 → 댓글 분석    │
                │        │                                    │
                │        ▼                                    │
                │  PostgreSQL 15 ◀──── ai-engine (FastAPI)    │
                │        │              :8000 (관리용 API)     │
                │        ▼                                    │
                │  api-server (Spring Boot) :8081             │
                └────────┼────────────────────────────────────┘
                         ▼
                  frontend (정적 대시보드) :5173
```

| 모듈 | 기술 스택 | 역할 |
|------|----------|------|
| [`ai-engine/`](ai-engine) | Python, FastAPI, SQLAlchemy | RSS 크롤러, 기사 클러스터링, Gemini/GPT 분석기, 댓글 수집·분석, 관리용 API |
| [`api-server/`](api-server) | Java, Spring Boot, JPA | 분석 결과 조회 REST API (보안 헤더, 레이트 리밋, 메서드 보호 필터 포함) |
| [`frontend/`](frontend) | Vanilla JS | 기사·분석 결과 시연용 대시보드 |
| [`db/`](db) | PostgreSQL | 스키마 초기화, 실서비스 RSS 소스, 마이그레이션 SQL |

## 하이브리드 AI 구성

- **클라우드 LLM**: 지원되는 `google-genai` SDK와 OpenAI Responses API의 구조화 출력을 사용합니다. 모든 점수·비율·요약은 Pydantic 스키마로 검증한 뒤에만 저장합니다.
- **로컬 LLM**: Unsloth 기반 LoRA 파인튜닝 파이프라인(`train_lora.py`, Colab 노트북)으로 자체 모델을 학습하고,
  GGUF로 변환해 Ollama(`ai-engine/Ollama/Modelfile`)로 서빙합니다.
- **모델 비교**: `compare_ollama_models.py`로 로컬 모델들의 품질·속도를 벤치마크해 채택 모델을 선정했습니다.

분석 파이프라인은 `worker.py`가 스케줄러로 주기 실행합니다:
**RSS 크롤링 → 기사 클러스터링 → 기사 분석 → 댓글 수집·분석**

## 실행 방법

### 1. 환경 변수 설정

```bash
cp .env.example .env
# DB 비밀번호와 AI_ENGINE_ADMIN_TOKEN을 안전한 임의 값으로 교체
# 사용할 공급자의 GEMINI_API_KEY 또는 OPENAI_API_KEY 입력
```

### 2. 전체 스택 실행

```bash
docker compose up -d db ai-engine ai-worker api-server

# RSS 소스 등록 (최초 1회)
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  < db/live_rss_sources.sql
```

기존 PostgreSQL 볼륨을 계속 사용하는 경우, 애플리케이션 업데이트 전에 ID 타입과 데이터 검증 제약을 순서대로 적용합니다. 범위를 벗어난 기존 분석값이나 `(article_id, model_used)` 중복이 있으면 데이터 삭제 없이 두 번째 마이그레이션이 중단됩니다.

```bash
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  < db/migrate_serial_ids_to_bigint.sql
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  < db/harden_analysis_constraints.sql
```

### 3. 대시보드 실행

```bash
npm --prefix frontend run serve
# http://localhost:5173 접속
```

| 서비스 | 주소 |
|--------|------|
| AI 엔진 (FastAPI Docs) | http://localhost:8000/docs |
| 비즈니스 API | http://localhost:8081 |
| 대시보드 | http://localhost:5173 |

## 테스트

```bash
# Python 3.12 (ai-engine)
cd ai-engine
uv venv --python 3.12 .venv
uv pip sync --python .venv/bin/python --require-hashes requirements-dev.txt
.venv/bin/pytest

# 운영 서비스 코드의 80% 커버리지 게이트
.venv/bin/pytest --cov=. --cov-config=.coveragerc --cov-fail-under=80

# Java (api-server) — 통합/보안/부하 테스트 포함
cd api-server && ./gradlew test

# Frontend 유틸리티
npm --prefix frontend test
```

크롤링·클러스터링·LLM 분석처럼 오래 걸리는 관리 작업은 `202 Accepted`와 `job_id`를 즉시 반환합니다. `GET http://localhost:8000/api/jobs/{job_id}`에 관리자 토큰을 보내 `queued`, `running`, `succeeded`, `failed` 상태와 결과를 조회합니다.

현재 job 상태 저장소는 AI 엔진 프로세스 메모리 기반이며 재시작 시 이력이 사라집니다. 다중 인스턴스 운영 전에는 `job_manager.py`를 Redis 또는 PostgreSQL 기반 저장소로 교체해야 합니다.

Python 직접 의존성을 바꿀 때는 `requirements.in`/`requirements-dev.in`을 수정하고 CI와 같은 Python 버전으로 해시 잠금을 다시 생성합니다.

```bash
cd ai-engine
uv pip compile --python-version 3.12 --universal --generate-hashes requirements.in -o requirements.txt
uv pip compile --python-version 3.12 --universal --generate-hashes requirements-dev.in -o requirements-dev.txt
```

## 보안 설계

- API 키·토큰은 모두 환경 변수로 주입하며 코드에 하드코딩하지 않습니다.
- PostgreSQL 포트와 애플리케이션 포트는 기본적으로 루프백에만 바인딩되며, Compose 서비스 이름은 프로젝트별로 격리됩니다.
- AI 엔진의 관리용 엔드포인트는 **허용 IP 대역(CIDR) + 관리자 토큰** 이중 검증을 거칩니다.
- Spring Boot API는 보안 헤더, 레이트 리밋, HTTP 메서드 보호 필터를 적용했습니다.
- 대시보드의 외부 기사 링크는 HTTP/HTTPS 프로토콜만 허용합니다.
- RSS·기사·댓글 크롤러는 `CRAWLER_ALLOWED_HOSTS`의 호스트만 접근하고, DNS 결과가 공인 IP인지 확인합니다.
- 모든 HTTP 리다이렉트는 자동 추적하지 않고 목적지의 호스트와 IP를 다시 검증해 SSRF를 차단합니다.

새 뉴스 출처를 추가할 때는 해당 RSS 및 기사 호스트를 `CRAWLER_ALLOWED_HOSTS`에 쉼표로 구분해 추가하세요. 하위 도메인은 명시한 상위 호스트의 범위에 포함되지만, 사설·루프백·링크 로컬 주소로 해석되는 호스트는 항상 거부됩니다.

## 디렉토리 구조

```
.
├── ai-engine/          # FastAPI 분석 엔진 + LoRA 학습 파이프라인
│   ├── crawler.py          # RSS 크롤러
│   ├── clustering.py       # 기사 클러스터링
│   ├── analyzer.py         # Gemini 기사 분석
│   ├── gpt_analyzer.py     # GPT 기사 분석
│   ├── comment_*.py        # 댓글 수집·분석
│   ├── train_lora.py       # 로컬 LLM LoRA 파인튜닝
│   ├── *_colab.ipynb       # Colab 학습/GGUF 변환 노트북
│   ├── compare_ollama_models.py  # 로컬 모델 벤치마크
│   └── worker.py           # 파이프라인 스케줄러
├── api-server/         # Spring Boot REST API
├── frontend/           # 시연용 대시보드
├── db/                 # 스키마·시드·마이그레이션 SQL
└── docker-compose.yml
```
