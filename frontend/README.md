# 최종 시연 프론트엔드

Spring Boot 기사 조회 API를 브라우저에서 시연하기 위한 정적 대시보드임.

## 실행

```bash
npm --prefix frontend run serve
```

브라우저에서 `http://localhost:5173`을 열면 됨.

## API 서버 준비

기본 API 주소는 `http://localhost:8081`임. Docker Compose로 API 서버를 실행하고 실제 SBS RSS 크롤링/분석을 완료한 뒤 사용함.

```bash
docker compose up -d db ai-engine ai-worker api-server
docker compose exec -T db psql -U devuser -d news_db < db/migrate_serial_ids_to_bigint.sql
docker compose exec -T db psql -U devuser -d news_db < db/live_rss_sources.sql
```

새 Docker 볼륨으로 처음 실행하는 경우에는 `db/init/01_schema.sql`이 최신 스키마를 만들기 때문에 마이그레이션 명령은 생략할 수 있음.

## 테스트

브라우저 코드의 순수 유틸리티 함수는 Node 내장 테스트 러너로 검증함.

```bash
npm --prefix frontend test
```
