import json
from pathlib import Path


def notebook_source() -> str:
    notebook_path = Path(__file__).with_name("train_gemma4_colab.ipynb")
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    return "\n".join(
        "".join(cell.get("source", []))
        for cell in notebook["cells"]
    )


def test_gemma4_colab_notebook_uses_dev_jinro_drive_workspace():
    source = notebook_source()

    assert 'DRIVE_ROOT = Path("/content/drive/MyDrive/dev-jinro")' in source
    assert 'DATASET_PATH = DATA_DIR / "chatml_dataset.jsonl"' in source
    assert 'OUTPUT_ROOT = DRIVE_ROOT / "outputs" / "gemma4_news_analyzer"' in source


def test_gemma4_colab_notebook_does_not_use_old_temporary_or_project_drive_paths():
    source = notebook_source()

    assert "/content/chatml_dataset.jsonl" not in source
    assert "/content/gemma4_news_analyzer" not in source
    assert "Career exploration" not in source


def test_gemma4_colab_notebook_uses_native_transformers_peft_without_unsloth_patches():
    source = notebook_source()

    assert "from unsloth import" not in source
    assert "FastLanguageModel" not in source
    assert "get_chat_template" not in source
    assert "AutoModelForCausalLM.from_pretrained" in source
    assert "prepare_model_for_kbit_training" in source
    assert 'MODEL_LOAD_BACKEND = "transformers_peft"' in source


def test_gemma4_colab_notebook_targets_inner_linear_modules_for_gemma4_wrappers():
    source = notebook_source()

    assert '"q_proj.linear"' in source
    assert '"k_proj.linear"' in source
    assert '"v_proj.linear"' in source
    assert '"o_proj.linear"' in source
    assert '"gate_proj.linear"' in source
    assert '"up_proj.linear"' in source
    assert '"down_proj.linear"' in source
    assert 'target_modules=LORA_TARGET_MODULES' in source


def test_gemma4_colab_notebook_uses_low_memory_training_defaults():
    source = notebook_source()

    assert "MAX_SEQ_LENGTH = 768" in source
    assert "GRADIENT_ACCUMULATION_STEPS = 16" in source
    assert 'optim="paged_adamw_8bit"' in source or 'optim = "paged_adamw_8bit"' in source
    assert "torch.cuda.empty_cache()" in source
    assert "model.gradient_checkpointing_enable" in source
