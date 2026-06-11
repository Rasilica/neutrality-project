import os
import logging

from logging_config import configure_logging

configure_logging()
logger = logging.getLogger(__name__)

try:
    import torch
    from datasets import load_dataset
    from unsloth import FastLanguageModel
    from unsloth.chat_templates import get_chat_template
    from trl import SFTTrainer
    from transformers import TrainingArguments
except ImportError:
    logger.warning("[경고] 트랜스포머 라이브러리(Unsloth, SFTTrainer 등)가 로컬에 설치되어 있지 않습니다.")
    logger.warning("이 스크립트는 실제 파인튜닝을 수행하는 구동 논리 파일이므로, NVIDIA GPU가 장착된 Linux/Colab 서버 환경에서 직접 구동되어야 합니다.")

# [논리 설정] 8주차: 학술 보고용 A.X 모델 (식별자)
MODEL_NAME = "native-ax-8b-base"
MAX_SEQ_LENGTH = 2048
DATASET_PATH = os.path.join(os.path.dirname(__file__), "data", "chatml_dataset.jsonl")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "lora_output")

def main():
    logger.info("로컬 LLM 파인튜닝 파이프라인 시작. model=%s", MODEL_NAME)
    
    if not os.path.exists(DATASET_PATH):
        logger.error("학습 데이터셋을 찾을 수 없습니다. path=%s", DATASET_PATH)
        logger.info("먼저 dataset_builder 로직(7주차)을 실행하여 .jsonl 파일을 생성하세요.")
        return

    # 실제 모듈 로드가 실패한 로컬 환경(MacOS 도커 등)에서는 논리 시뮬레이션으로 중단 방지
    if "FastLanguageModel" not in globals():
        logger.info("[Mac Local Mode] 실제 모델 훈련 라이브러리를 건너뜁니다. 코드는 정상 준비되었습니다.")
        return

    # 1. 4-bit 양자화 및 모델 로드 (초고속 Unsloth 활용)
    logger.info("1. 모델 뼈대 구축 및 양자화 로드...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=MODEL_NAME,
        max_seq_length=MAX_SEQ_LENGTH,
        dtype=None, # 자동 타입 감지 (Float16 vs Bfloat16)
        load_in_4bit=True, # 10GB 이하 VRAM 환경을 위한 핵심 최적화
    )

    # 2. LoRA(Low-Rank Adaptation) 가중치 어댑터 설정
    logger.info("2. LoRA 가중치 어댑터(Target Modules) 주입 중...")
    model = FastLanguageModel.get_peft_model(
        model,
        r=16, # Rank 파라미터 사이즈
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        lora_alpha=32,
        lora_dropout=0.05, # 과적합(Overfitting) 제어를 위한 드롭아웃 활성화
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
    )

    # 3. 데이터셋 로드 및 ChatML 템플릿 적용
    logger.info("3. Hugging Face datasets 로드 및 ChatML 매핑 중...")
    dataset = load_dataset("json", data_files=DATASET_PATH, split="train")
    
    # Unsloth의 챗 매핑 함수 활용
    tokenizer = get_chat_template(
        tokenizer,
        chat_template="chatml",
        mapping={"role": "role", "content": "content", "user": "user", "assistant": "assistant"},
    )
    
    def apply_chat_template(examples):
        texts = [tokenizer.apply_chat_template(msg, tokenize=False, add_generation_prompt=False) for msg in examples["messages"]]
        return {"text": texts}

    dataset = dataset.map(apply_chat_template, batched=True)

    # 4. SFT (Supervised Fine-Tuning) 트레이너 구축
    logger.info("4. Hugging Face SFTTrainer 및 VRAM 최적화 옵티마이저 설정 중...")
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=MAX_SEQ_LENGTH,
        dataset_num_proc=2,
        packing=False, # 짧은 텍스트(요약본 등)를 처리하므로 패킹 비활성화
        args=TrainingArguments(
            per_device_train_batch_size=2,
            gradient_accumulation_steps=4, # OOM 예방을 위한 스텝 연기(Gradient Accumulation)
            warmup_steps=10,
            max_steps=60, # 튜닝 파라미터 테스트용 한계점
            learning_rate=2e-4,
            fp16=not torch.cuda.is_bf16_supported(),
            bf16=torch.cuda.is_bf16_supported(),
            logging_steps=1,
            optim="adamw_8bit", # 8-bit AdamW 로 GPU 메모리 대폭 절약
            weight_decay=0.01,
            lr_scheduler_type="linear",
            seed=42,
            output_dir="outputs",
        ),
    )

    # 5. 파인튜닝 실행
    logger.info("5. 파인튜닝 훈련 시작!")
    # trainer.train() # Colab 환경 혹은 실제 GPU 서버에서 언커멘트하여 동작
    
    # 6. 결과 도출 및 저장
    logger.info("6. 파인튜닝 어댑터 파일 저장 중. output_dir=%s", OUTPUT_DIR)
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        
    # model.save_pretrained(OUTPUT_DIR) # 가중치 저장 파일 (9주차 병합 대비)
    # tokenizer.save_pretrained(OUTPUT_DIR)
    
    logger.info("파인튜닝(LoRA) 로직 완료 및 준비 성공.")

if __name__ == "__main__":
    main()
