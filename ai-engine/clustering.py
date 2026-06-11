import logging
from typing import List, Dict
from sqlalchemy.orm import Session
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import DBSCAN

from models import Article, ArticleGroup, ArticleGroupMember

logger = logging.getLogger(__name__)

class ArticleClusterer:
    def __init__(self, db: Session):
        self.db = db
        # DBSCAN parameters: eps (거리 타겟), min_samples (클러스터 최소 기사 수)
        # 뉴스 제목과 내용 텍스트의 TF-IDF 코사인 거리 기반이므로 eps 설정이 중요합니다.
        self.eps = 0.5
        self.min_samples = 2

    def run(self) -> dict:
        """
        그룹핑되지 않은 기사들을 불러와 TF-IDF + DBSCAN 클러스터링을 수행하고,
        새로운 사건 그룹(ArticleGroup)을 만들어 DB에 저장합니다.
        """
        # 아직 그룹이 없는 기사만 조회
        # (실제 운영 환경에서는 날짜 필터링 조건을 추가해 최근 n일 기사만 클러스터링하도록 최적화 권장)
        articles = self.db.query(Article).outerjoin(ArticleGroupMember, Article.id == ArticleGroupMember.article_id).filter(ArticleGroupMember.group_id == None).all()

        if not articles:
            return {"status": "success", "message": "No new articles to cluster.", "clusters_created": 0}

        # 1. 텍스트 코퍼스 생성 (제목 + 스니펫)
        # 본문이 길면 TF-IDF 연산이 무거워지므로 제목 위주 + 본문 일부를 사용합니다.
        corpus = []
        for a in articles:
            content_snippet = a.content[:200] if a.content else ""
            text = f"{a.title} {content_snippet}"
            corpus.append(text)

        # 수집된 기사가 1개 이하면 군집화 불가능
        if len(corpus) < 2:
            return {"status": "success", "message": "Not enough articles to form clusters.", "clusters_created": 0}

        try:
            # 2. 벡터화 (TF-IDF)
            vectorizer = TfidfVectorizer(max_features=1000)
            X = vectorizer.fit_transform(corpus)

            # 3. DBSCAN 클러스터링
            # metric='cosine'을 사용하여 문서 간 코사인 유사도 거리로 밀도를 측정
            clustering = DBSCAN(eps=self.eps, min_samples=self.min_samples, metric='cosine')
            labels = clustering.fit_predict(X)

            # 4. 클러스터별 그룹 생성 및 DB 저장
            clusters_created = 0
            # labels 내의 고유값들을 확인 (-1은 노이즈/분류 안됨)
            unique_labels = set(labels)
            
            for label in unique_labels:
                if label == -1:
                    continue  # 노이즈는 무시

                # 현재 클러스터에 속한 기사들 필터링
                cluster_articles = [articles[i] for i, l in enumerate(labels) if l == label]
                
                if not cluster_articles:
                    continue

                # 그룹 토픽 이름은 클러스터의 첫 번째 기사 제목으로 임시 설정
                # (추후 5주차에 AI를 이용해 제목을 이쁘게 요약하도록 고도화 가능)
                topic_title = cluster_articles[0].title

                new_group = ArticleGroup(topic_title=topic_title)
                self.db.add(new_group)
                self.db.flush() # id 할당받기 위해 flush

                # 그룹 멤버 매핑 테이블에 저장
                for ca in cluster_articles:
                    member = ArticleGroupMember(article_id=ca.id, group_id=new_group.id)
                    self.db.add(member)

                clusters_created += 1

            self.db.commit()
            return {"status": "success", "clusters_created": clusters_created, "processed_articles": len(articles)}

        except Exception as e:
            logger.error("Error during clustering.", exc_info=True)
            self.db.rollback()
            return {"status": "error", "message": str(e), "clusters_created": 0}
