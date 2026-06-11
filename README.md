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

- **클라우드 LLM**: Gemini(`analyzer.py`, `comment_analyzer.py`)와 GPT(`gpt_analyzer.py`)로 기사 중립성·댓글 감성을 분석합니다.
- **로컬 LLM**: Unsloth 기반 LoRA 파인튜닝 파이프라인(`train_lora.py`, Colab 노트북)으로 자체 모델을 학습하고,
  GGUF로 변환해 Ollama(`ai-engine/Ollama/Modelfile`)로 서빙합니다.
- **모델 비교**: `compare_ollama_models.py`로 로컬 모델들의 품질·속도를 벤치마크해 채택 모델을 선정했습니다.

분석 파이프라인은 `worker.py`가 스케줄러로 주기 실행합니다:
**RSS 크롤링 → 기사 클러스터링 → 기사 분석 → 댓글 수집·분석**

## 실행 방법

### 1. 환경 변수 설정

```bash
cp .env.example .env
# .env에 GEMINI_API_KEY, OPENAI_API_KEY, AI_ENGINE_ADMIN_TOKEN 입력
```

### 2. 전체 스택 실행

```bash
docker compose up -d db ai-engine ai-worker api-server

# RSS 소스 등록 (최초 1회)
docker compose exec -T db psql -U devuser -d news_db < db/live_rss_sources.sql
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
# Python (ai-engine)
cd ai-engine && pytest

# Java (api-server) — 통합/보안/부하 테스트 포함
cd api-server && ./gradlew test

# Frontend 유틸리티
npm --prefix frontend test
```

## 보안 설계

- API 키·토큰은 모두 환경 변수로 주입하며 코드에 하드코딩하지 않습니다.
- AI 엔진의 관리용 엔드포인트는 **허용 IP 대역(CIDR) + 관리자 토큰** 이중 검증을 거칩니다.
- Spring Boot API는 보안 헤더, 레이트 리밋, HTTP 메서드 보호 필터를 적용했습니다.

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
