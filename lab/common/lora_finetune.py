"""Offline LoRA fine-tuning of the bounded rewriter checkpoint.

FORBIDDEN.md's narrow exception, recorded 2026-10-16: a LoRA adapter on the
already-permitted flan-t5-small checkpoint, trained once here, before any
answering, on deterministically-generated synthetic data
(lab.common.synthetic_fusion_data) -- never online, never during an actual
answer. See that file's own docstring for why flan-t5-small and not
gemma3:270m (the latter is gate-restricted on HuggingFace and this
environment has no credentials that have accepted it).

This module only trains and saves an adapter; it does not decide whether
the result is adopted -- that is EXP-073's job, by comparing the fidelity
pass rate against the unmodified base checkpoint on held-out cases,
including the original EXP-048/064 4-fact-leaf failure.
"""

from __future__ import annotations

from pathlib import Path

from lab.common.real_rewriter import MODEL_NAME, build_prompt


def examples_to_pairs(examples: list[dict], glossary: dict | None = None) -> list[dict]:
    """Each synthetic example (lab.common.synthetic_fusion_data) already has
    a "target" field built by deterministic templated fusion, never by a
    model. This reuses the exact same build_prompt the real rewriter role
    calls, so training sees the identical prompt shape inference will.
    """
    glossary = glossary or {}
    pairs = []
    for example in examples:
        prompt, _src_text, _cite_ids = build_prompt(example, glossary)
        pairs.append({"prompt": prompt, "target": example["target"]})
    return pairs


def train_lora(
    train_pairs: list[dict],
    output_dir: Path,
    base_model: str = MODEL_NAME,
    rank: int = 8,
    epochs: int = 3,
    batch_size: int = 4,
    learning_rate: float = 1e-3,
) -> dict:
    import torch
    from datasets import Dataset
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer, DataCollatorForSeq2Seq, Seq2SeqTrainer, Seq2SeqTrainingArguments

    tokenizer = AutoTokenizer.from_pretrained(base_model)
    model = AutoModelForSeq2SeqLM.from_pretrained(base_model)

    lora_config = LoraConfig(
        r=rank,
        lora_alpha=rank * 2,
        target_modules=["q", "v"],
        lora_dropout=0.05,
        task_type="SEQ_2_SEQ_LM",
    )
    model = get_peft_model(model, lora_config)
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())

    def _tokenize(batch):
        inputs = tokenizer(batch["prompt"], truncation=True, max_length=512)
        labels = tokenizer(text_target=batch["target"], truncation=True, max_length=256)
        inputs["labels"] = labels["input_ids"]
        return inputs

    dataset = Dataset.from_list(train_pairs).map(_tokenize, batched=True, remove_columns=["prompt", "target"])

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    args = Seq2SeqTrainingArguments(
        output_dir=str(output_dir),
        per_device_train_batch_size=batch_size,
        num_train_epochs=epochs,
        learning_rate=learning_rate,
        logging_steps=10,
        save_strategy="no",
        report_to=[],
        no_cuda=not torch.cuda.is_available(),
    )
    trainer = Seq2SeqTrainer(
        model=model,
        args=args,
        train_dataset=dataset,
        data_collator=DataCollatorForSeq2Seq(tokenizer, model=model),
    )
    train_result = trainer.train()
    model.save_pretrained(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))

    return {
        "output_dir": str(output_dir),
        "trainable_params": trainable,
        "total_params": total,
        "trainable_fraction": round(trainable / total, 6),
        "train_loss": train_result.training_loss,
        "epochs": epochs,
        "n_train_examples": len(train_pairs),
    }


def load_lora(adapter_dir: Path, base_model: str = MODEL_NAME):
    from peft import PeftModel
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(str(adapter_dir))
    base = AutoModelForSeq2SeqLM.from_pretrained(base_model)
    model = PeftModel.from_pretrained(base, str(adapter_dir))
    model.eval()
    return tokenizer, model
