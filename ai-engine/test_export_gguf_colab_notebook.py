import json
from pathlib import Path


def notebook_source() -> str:
    notebook_path = Path(__file__).with_name("export_gguf_colab.ipynb")
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    return "\n".join(
        "".join(cell.get("source", []))
        for cell in notebook["cells"]
    )


def test_export_notebook_uses_current_drive_workspace_and_adapter_output():
    source = notebook_source()

    assert 'DRIVE_ROOT = Path("/content/drive/MyDrive/dev-jinro")' in source
    assert 'OUTPUT_ROOT = DRIVE_ROOT / "outputs" / "gemma4_news_analyzer"' in source
    assert 'ADAPTER_DIR = OUTPUT_ROOT / "lora_adapter"' in source
    assert 'LOCAL_ARCHIVE_HINT = "/Volumes/PortableSSD/Downloads/gemma4_news_analyzer_outputs.zip"' in source


def test_export_notebook_merges_peft_lora_before_gguf_conversion():
    source = notebook_source()

    assert "from peft import PeftModel" in source
    assert "PeftModel.from_pretrained" in source
    assert "merge_and_unload()" in source
    assert "save_pretrained" in source


def test_export_notebook_removes_incompatible_colab_torchao_before_peft():
    source = notebook_source()

    assert "pip -q uninstall -y torchao" in source
    assert "importlib.metadata" in source
    assert "torchao is not installed" in source


def test_export_notebook_requires_transformers_v5_for_gemma4():
    source = notebook_source()

    assert '"transformers>=5.5.0"' in source
    assert "require_transformers_v5_for_gemma4" in source
    assert "Transformers v5+" in source


def test_export_notebook_does_not_install_llama_cpp_pinned_transformers_v4_requirements():
    source = notebook_source()

    assert "requirements-convert_hf_to_gguf.txt" not in source
    assert "requirements_file.exists()" not in source
    assert "transformers==4.57.6" not in source


def test_export_notebook_streams_subprocess_logs_for_conversion_failures():
    source = notebook_source()

    assert "def run_streamed" in source
    assert "subprocess.Popen" in source
    assert "stderr=subprocess.STDOUT" in source
    assert "Recent output" in source


def test_export_notebook_uses_llama_cpp_conversion_and_q4_k_m_quantization():
    source = notebook_source()

    assert "https://github.com/ggml-org/llama.cpp" in source
    assert "convert_hf_to_gguf.py" in source
    assert "llama-quantize" in source
    assert "Q4_K_M" in source
    assert "gemma4_news_analyzer.Q4_K_M.gguf" in source


def test_export_notebook_does_not_use_old_unsloth_or_career_paths():
    source = notebook_source()

    assert "from unsloth import" not in source
    assert "FastLanguageModel" not in source
    assert "Career exploration" not in source
