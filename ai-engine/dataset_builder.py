import os
import json
import logging
from sqlalchemy.orm import Session
from models import Article, AnalysisResult

logger = logging.getLogger(__name__)

class DatasetBuilder:
    def __init__(self, db: Session):
        self.db = db
        # 컨테이너 내(또는 로컬) data 디렉토리 파악 및 생성
        self.data_dir = os.path.join(os.path.dirname(__file__), "data")
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

    def build_chatml_dataset(self) -> dict:
        """
        AI 분석 기 적재 데이터를 조회하여 A.X 모델 학습용 ChatML 포맷 JSONL 로 출력합니다.
        """
        output_file = os.path.join(self.data_dir, "chatml_dataset.jsonl")
        
        # Article과 AnalysisResult를 조인하여 성공적으로 분석된 정답 데이터 가져오기
        results = self.db.query(Article, AnalysisResult).join(
            AnalysisResult, Article.id == AnalysisResult.article_id
        ).filter(
            AnalysisResult.sentiment_score != None,
            AnalysisResult.bias_score != None,
            AnalysisResult.factuality_score != None
        ).all()

        if not results:
            return {"status": "success", "message": "No valid analysis data found to build dataset.", "count": 0}

        dataset_count = 0
        system_prompt = "당신은 엄격하고 객관적인 한국어 뉴스 분석 AI입니다. 입력된 기사의 감정 점수(-1~1), 편향 점수(0~1), 사실성 점수(0~1)를 평가하고 핵심 내용을 3문장 이내로 요약하여 JSON 형식으로 출력하세요."
        
        try:
            with open(output_file, "w", encoding="utf-8") as f:
                for article, analysis in results:
                    # 유저 프롬프트 (기본 컨텍스트)
                    user_content = f"[기사 제목]: {article.title}\n[기사 본문]: {article.content}"
                    
                    # 어시스턴트 정답지 (점수 및 요약)
                    assistant_content = json.dumps({
                        "sentiment_score": analysis.sentiment_score,
                        "bias_score": analysis.bias_score,
                        "factuality_score": analysis.factuality_score,
                        "summary": analysis.summary
                    }, ensure_ascii=False)

                    # ChatML Message 포맷 패키징
                    chatml_struct = {
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_content},
                            {"role": "assistant", "content": assistant_content}
                        ]
                    }

                    # JSONL(JSON Lines) 규격으로 한 줄씩 쓰기
                    f.write(json.dumps(chatml_struct, ensure_ascii=False) + "\n")
                    dataset_count += 1
                    
        except Exception as e:
            logger.error("Error writing dataset.", exc_info=True)
            return {"status": "error", "message": str(e), "count": dataset_count}

        return {
            "status": "success",
            "message": "ChatML dataset generated completely.",
            "count": dataset_count,
            "file_path": output_file
        }
