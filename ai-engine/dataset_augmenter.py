import os
import json
import random
import glob
import logging

from logging_config import configure_logging

configure_logging()
logger = logging.getLogger(__name__)

# 설정 값
EXTERNAL_LABELS_DIR = "/Users/min/folder/study/AI_data/159.문장_유형(추론,_예측_등)_판단_데이터/_extracted_labels"
TARGET_JSONL = "/Users/min/folder/school/3-1/진로탐색/dev/ai-engine/data/chatml_dataset.jsonl"
SAMPLE_SIZE = 1000
SYSTEM_PROMPT = "당신은 엄격하고 객관적인 한국어 뉴스 분석 AI입니다. 입력된 기사의 감정 점수(-1~1), 편향 점수(0~1), 사실성 점수(0~1)를 평가하고 핵심 내용을 3문장 이내로 요약하여 JSON 형식으로 출력하세요."

def parse_and_augment():
    # 폴더 내의 모든 JSON 파일 리스트 수집
    all_files = glob.glob(os.path.join(EXTERNAL_LABELS_DIR, "*.json"))
    
    if not all_files:
        logger.error("JSON 파일을 찾을 수 없습니다. path=%s", EXTERNAL_LABELS_DIR)
        return

    logger.info("외부 데이터를 발견했습니다. total=%s sample_size=%s", len(all_files), SAMPLE_SIZE)
    
    # 랜덤 샘플링
    sampled_files = random.sample(all_files, min(SAMPLE_SIZE, len(all_files)))
    
    augmented_data = []
    
    for file_path in sampled_files:
        with open(file_path, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
            except Exception:
                logger.error("Failed to parse JSON file. path=%s", file_path, exc_info=True)
                continue
                
        annotations = data.get("annotation", [])
        if not annotations:
            continue
            
        full_text = ""
        fact_count = 0
        sentiment_sum = 0
        bias_count = 0
        sentences_for_summary = []
        
        for idx, ann in enumerate(annotations):
            text = ann.get("text", "").strip()
            if not text:
                continue
                
            full_text += text + " "
            label = ann.get("label", "")
            value = ann.get("value", {})
            polarity = value.get("극성", "")
            
            # 사실성 평가 (사실형 비율)
            if "사실" in label:
                fact_count += 1
                
            # 감정 평가 (-1 ~ 1)
            if "긍정" in polarity:
                sentiment_sum += 1
            elif "부정" in polarity:
                sentiment_sum -= 1
                
            # 편향성 평가 (평가형/분석형이거나 주관성이 강한 경우 편향 증가로 휴리스틱 처리)
            if "평가" in label or "추론" in label:
                bias_count += 1
                
            # 요약을 위해 가장 긴 1~3문장 수집 (임시 휴리스틱)
            sentences_for_summary.append(text)
            
        total_sentences = len(annotations)
        if total_sentences == 0:
            continue
            
        # 점수 정규화
        factuality_score = round(fact_count / total_sentences, 2)
        sentiment_score = round(sentiment_sum / total_sentences, 2)
        bias_score = round(bias_count / total_sentences, 2)
        
        # 길이 순으로 정렬하여 가장 긴 2문장 요약
        sentences_for_summary.sort(key=len, reverse=True)
        summary = " ".join(sentences_for_summary[:2])
        
        title = data.get("metaData", {}).get("CATEGORY", "종합") + " 뉴스 기사"
        
        # User 프롬프트 생성
        user_prompt = f"[기사 제목]: {title}\n[기사 본문]: {full_text.strip()}"
        
        # Assistant 정답지 생성
        assistant_response = {
            "sentiment_score": sentiment_score,
            "bias_score": bias_score,
            "factuality_score": factuality_score,
            "summary": summary
        }
        
        # ChatML 구조
        chatml_record = {
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": json.dumps(assistant_response, ensure_ascii=False)}
            ]
        }
        
        augmented_data.append(chatml_record)
        
    logger.info("데이터 변환 성공. count=%s", len(augmented_data))
    
    # 기존 jsonl 파일에 Append
    os.makedirs(os.path.dirname(TARGET_JSONL), exist_ok=True)
    with open(TARGET_JSONL, 'a', encoding='utf-8') as out_f:
        for record in augmented_data:
            out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
            
    logger.info("데이터를 추가했습니다. target=%s", TARGET_JSONL)

if __name__ == "__main__":
    parse_and_augment()
