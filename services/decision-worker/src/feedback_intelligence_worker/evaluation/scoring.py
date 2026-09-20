"""Provider-neutral scoring for frozen human-labelled evaluation splits."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from feedback_intelligence_worker.decision.schema import DecisionSchema, Primitive

SPLITS = {"development", "calibration", "locked_test", "all"}
PREDICTION_FORMAT = "feedback-evaluation-prediction/1.0.0"
REPORT_FORMAT = "feedback-evaluation-report/1.0.0"
SELECTIVE_THRESHOLDS = (0.0, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99)


def score_evaluation(
    *,
    records_path: Path,
    labels_path: Path,
    predictions_path: Path,
    schema: DecisionSchema,
    split: str,
    unlock_locked_test: bool = False,
    reference_kind: str = "human_gold",
    reference_model: str | None = None,
    allow_partial: bool = False,
) -> dict[str, Any]:
    """Validate one engine run and score it against one complete gold split."""
    if split not in SPLITS:
        raise ValueError(f"Unknown evaluation split: {split}")
    if reference_kind not in {"human_gold", "ai_reference"}:
        raise ValueError(f"Unknown reference kind: {reference_kind}")
    if reference_kind == "ai_reference" and not reference_model:
        raise ValueError("AI-reference scoring requires a reference model")
    if reference_kind == "human_gold" and reference_model is not None:
        raise ValueError("Human-gold scoring cannot declare a reference model")
    if allow_partial and reference_kind != "ai_reference":
        raise ValueError("Partial scoring is only available for an AI reference")
    if split == "all" and reference_kind != "ai_reference":
        raise ValueError("The combined split is only available for an AI reference")
    if split == "locked_test" and reference_kind == "human_gold" and not unlock_locked_test:
        raise ValueError("Locked-test scoring requires --unlock-locked-test")

    records = _unique_rows(records_path)
    labels = _unique_rows(labels_path)
    predictions = _unique_rows(predictions_path)
    if set(records) != set(labels):
        raise ValueError("Evaluation record and label id sets differ")

    selected = (
        records
        if split == "all"
        else {key: row for key, row in records.items() if row.get("split") == split}
    )
    if not selected:
        raise ValueError(f"Evaluation split is empty: {split}")
    target_record_count = len(selected)
    if allow_partial:
        if not predictions:
            raise ValueError("Partial prediction file is empty")
        extra = sorted(set(predictions) - set(selected))
        if extra:
            raise ValueError(f"Partial predictions contain ids outside {split}; extra={extra}")
        selected = {key: selected[key] for key in predictions}
    elif set(predictions) != set(selected):
        missing = sorted(set(selected) - set(predictions))
        extra = sorted(set(predictions) - set(selected))
        raise ValueError(f"Prediction ids do not match {split}; missing={missing}, extra={extra}")

    gold: dict[str, dict[str, Any]] = {}
    for feedback_id in sorted(selected):
        record = selected[feedback_id]
        label = labels[feedback_id]
        if label.get("split") != record.get("split"):
            raise ValueError(f"Split mismatch for {feedback_id}")
        gold[feedback_id] = _resolved_gold(label, record, schema, feedback_id)

    engine: dict[str, Any] | None = None
    parsed: dict[str, dict[str, Any] | None] = {}
    errors: dict[str, int] = {}
    latencies: list[float] = []
    input_tokens = output_tokens = 0
    costs: list[float] = []
    for feedback_id, row in predictions.items():
        if row.get("schema_version") != PREDICTION_FORMAT:
            raise ValueError(f"Unsupported prediction format for {feedback_id}")
        if row.get("split") != selected[feedback_id].get("split"):
            raise ValueError(f"Prediction split mismatch for {feedback_id}")
        current_engine = _object(row.get("engine"), f"engine for {feedback_id}")
        if current_engine.get("schema_sha256") != schema.sha256:
            raise ValueError(f"Prediction schema hash mismatch for {feedback_id}")
        if engine is None:
            engine = current_engine
        elif engine != current_engine:
            raise ValueError("Every prediction row must use identical engine metadata")
        status = row.get("status")
        execution = _object(row.get("execution"), f"execution for {feedback_id}")
        latency = _number(execution.get("latency_ms"), f"latency for {feedback_id}")
        if latency < 0:
            raise ValueError(f"Latency cannot be negative for {feedback_id}")
        latencies.append(latency)
        input_tokens += _optional_nonnegative_int(execution.get("input_tokens"), "input_tokens")
        output_tokens += _optional_nonnegative_int(execution.get("output_tokens"), "output_tokens")
        cost = execution.get("cost_usd")
        if cost is not None:
            numeric_cost = _number(cost, f"cost for {feedback_id}")
            if numeric_cost < 0:
                raise ValueError(f"Cost cannot be negative for {feedback_id}")
            costs.append(numeric_cost)
        if status == "error":
            error_type = _text(row, "error_type")
            if row.get("answers") is not None:
                raise ValueError(f"Failed prediction must have null answers: {feedback_id}")
            errors[error_type] = errors.get(error_type, 0) + 1
            parsed[feedback_id] = None
        elif status == "success":
            if row.get("error_type") is not None:
                raise ValueError(f"Successful prediction cannot have error_type: {feedback_id}")
            parsed[feedback_id] = _prediction_answers(row.get("answers"), schema, feedback_id)
        else:
            raise ValueError(f"Invalid prediction status for {feedback_id}")

    assert engine is not None
    question_reports: dict[str, Any] = {}
    for question in schema.questions:
        truth = [gold[key][question.question_id]["value"] for key in sorted(selected)]
        answers = [_answer(parsed[key], question.question_id) for key in sorted(selected)]
        if question.primitive is Primitive.CHOICE:
            classes = [option.option_id for option in question.options]
            question_reports[question.question_id] = _choice_report(truth, answers, classes)
        elif question.primitive is Primitive.SCORE:
            levels = [level.value for level in question.levels]
            question_reports[question.question_id] = _score_report(truth, answers, levels)
        else:
            question_reports[question.question_id] = _noul_report(truth, answers)

    language_slices: dict[str, Any] = {}
    languages = sorted({_text(row, "language") for row in selected.values()})
    for language in languages:
        ids = sorted(key for key, row in selected.items() if row.get("language") == language)
        primary_truth = [str(gold[key]["primary_topic"]["value"]) for key in ids]
        primary_predictions = []
        for key in ids:
            primary_answer = _answer(parsed[key], "primary_topic")
            primary_predictions.append(
                str(primary_answer["value"]) if primary_answer is not None else None
            )
        primary_question = next(q for q in schema.questions if q.question_id == "primary_topic")
        classes = [option.option_id for option in primary_question.options]
        language_slices[language] = {
            "record_count": len(ids),
            "success_count": sum(parsed[key] is not None for key in ids),
            "primary_topic": _classification(primary_truth, primary_predictions, classes),
        }

    success_count = sum(value is not None for value in parsed.values())
    report: dict[str, Any] = {
        "schema_version": REPORT_FORMAT,
        "sample_version": "feedback-decision-1.0.0",
        "split": split,
        "partial_evaluation": allow_partial,
        "locked_test_unlocked": split == "locked_test" and unlock_locked_test,
        "reference": {"kind": reference_kind, "model": reference_model},
        "engine": engine,
        "inputs": {
            "records_sha256": _sha256(records_path),
            "labels_sha256": _sha256(labels_path),
            "predictions_sha256": _sha256(predictions_path),
            "decision_schema_sha256": schema.sha256,
        },
        "summary": {
            "record_count": len(selected),
            "target_record_count": target_record_count,
            "success_count": success_count,
            "error_count": len(selected) - success_count,
            "error_rate": (len(selected) - success_count) / len(selected),
            "primary_topic_macro_f1": question_reports["primary_topic"]["macro_f1"],
            "primary_topic_accuracy": question_reports["primary_topic"]["accuracy"],
        },
        "questions": question_reports,
        "slices": {"language": language_slices},
        "operations": {
            "latency_ms": _percentiles(latencies),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_cost_usd": sum(costs) if len(costs) == len(selected) else None,
            "cost_usd_per_1000_records": (
                sum(costs) * 1000 / len(selected) if len(costs) == len(selected) else None
            ),
            "errors_by_type": dict(sorted(errors.items())),
        },
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    report["report_sha256"] = hashlib.sha256(canonical).hexdigest()
    return report


def render_report_markdown(report: dict[str, Any]) -> str:
    summary = _object(report.get("summary"), "report summary")
    engine = _object(report.get("engine"), "report engine")
    reference = _object(report.get("reference"), "report reference")
    questions = _object(report.get("questions"), "report questions")
    provenance = (
        "This interim report uses AI-reviewed reference labels and is not human gold."
        if reference.get("kind") == "ai_reference"
        else "This report uses completed human-reviewed gold labels."
    )
    lines = [
        "# Feedback decision evaluation",
        "",
        f"- Split: `{report['split']}`",
        f"- Reference: `{report['reference']['kind']}` / `{report['reference']['model'] or 'n/a'}`",
        f"- Engine: `{engine.get('provider')}` / `{engine.get('resolved_model')}`",
        f"- Records: {summary['record_count']}",
        f"- Target records: {summary['target_record_count']}",
        f"- Partial evaluation: `{str(report['partial_evaluation']).lower()}`",
        f"- Successful predictions: {summary['success_count']}",
        f"- Prediction errors: {summary['error_count']}",
        f"- Primary-topic macro-F1: {_format_metric(summary['primary_topic_macro_f1'])}",
        f"- Primary-topic accuracy: {_format_metric(summary['primary_topic_accuracy'])}",
        "",
        "| Question | Primitive | Main quality metric | Brier | ECE |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for question_id, value in questions.items():
        item = _object(value, question_id)
        primitive = str(item["primitive"])
        if primitive == "choice":
            main = f"macro-F1 {_format_metric(item['macro_f1'])}"
        elif primitive == "score":
            main = f"MAE {_format_metric(item['mae'])}"
        else:
            main = f"F1 {_format_metric(item['f1'])}"
        lines.append(
            f"| `{question_id}` | {primitive} | {main} | "
            f"{_format_metric(item.get('brier'))} | {_format_metric(item.get('ece'))} |"
        )
    lines.extend(
        [
            "",
            (
                f"{provenance} It is generated from a frozen split and one prediction file. "
                "Prediction failures stay in the denominator. Calibration and selective metrics "
                "are descriptive and should be interpreted with the reported sample counts."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _resolved_gold(
    label: dict[str, Any], record: dict[str, Any], schema: DecisionSchema, feedback_id: str
) -> dict[str, Any]:
    required = 2 if record.get("requires_second_pass") is True else 1
    if label.get("requires_second_pass") != record.get("requires_second_pass"):
        raise ValueError(f"Second-pass requirement mismatch for {feedback_id}")
    annotations = label.get("annotations")
    if not isinstance(annotations, list) or len(annotations) != required:
        raise ValueError(f"Incomplete human annotations for {feedback_id}")
    validated: list[dict[str, Any]] = []
    passes: set[int] = set()
    for item in annotations:
        annotation = _object(item, "annotation")
        pass_number = annotation.get("pass")
        if pass_number not in {1, 2} or pass_number in passes:
            raise ValueError(f"Invalid annotation pass for {feedback_id}")
        passes.add(pass_number)
        _text(annotation, "annotator_id")
        _text(annotation, "annotated_at")
        validated.append(_gold_answers(annotation, schema, feedback_id))
    if passes != set(range(1, required + 1)):
        raise ValueError(f"Required annotation passes are missing for {feedback_id}")
    disagreement = len(validated) == 2 and validated[0] != validated[1]
    adjudication = label.get("adjudication")
    if disagreement:
        if not isinstance(adjudication, dict):
            raise ValueError(f"Unadjudicated disagreement for {feedback_id}")
        _text(adjudication, "adjudicator_id")
        _text(adjudication, "adjudicated_at")
        _text(adjudication, "reason")
        return _gold_answers(adjudication, schema, feedback_id)
    if adjudication is not None:
        raise ValueError(f"Adjudication without disagreement for {feedback_id}")
    return validated[0]


def _gold_answers(
    annotation: dict[str, Any], schema: DecisionSchema, feedback_id: str
) -> dict[str, Any]:
    answers = _object(annotation.get("answers"), f"gold answers for {feedback_id}")
    expected = {question.question_id for question in schema.questions}
    if set(answers) != expected:
        raise ValueError(f"Gold answer ids do not match schema for {feedback_id}")
    for question in schema.questions:
        answer = _object(answers[question.question_id], question.question_id)
        if answer.get("type") != question.primitive.value:
            raise ValueError(f"Wrong gold primitive for {question.question_id}")
        value = answer.get("value")
        if question.primitive is Primitive.CHOICE:
            if value not in {option.option_id for option in question.options}:
                raise ValueError(f"Invalid gold choice for {question.question_id}")
        elif question.primitive is Primitive.SCORE:
            if isinstance(value, bool) or value not in {level.value for level in question.levels}:
                raise ValueError(f"Invalid gold score for {question.question_id}")
        elif not isinstance(value, bool):
            raise ValueError(f"Invalid gold Noul for {question.question_id}")
    return answers


def _prediction_answers(value: object, schema: DecisionSchema, feedback_id: str) -> dict[str, Any]:
    answers = _object(value, f"prediction answers for {feedback_id}")
    expected = {question.question_id for question in schema.questions}
    if set(answers) != expected:
        raise ValueError(f"Prediction answer ids do not match schema for {feedback_id}")
    parsed: dict[str, Any] = {}
    for question in schema.questions:
        raw = _object(answers[question.question_id], question.question_id)
        if raw.get("type") != question.primitive.value:
            raise ValueError(f"Wrong prediction primitive for {question.question_id}")
        if question.primitive is Primitive.CHOICE:
            classes = [option.option_id for option in question.options]
            probabilities = _distribution(raw.get("probabilities"), classes, question.question_id)
            choice = raw.get("choice")
            if choice not in classes:
                raise ValueError(f"Invalid predicted choice for {question.question_id}")
            confidence = _probability(raw.get("confidence"), question.question_id)
            parsed[question.question_id] = {
                "value": choice,
                "probabilities": probabilities,
                "confidence": confidence,
            }
        elif question.primitive is Primitive.SCORE:
            levels = [level.value for level in question.levels]
            probabilities = _distribution(
                raw.get("probabilities"), [str(level) for level in levels], question.question_id
            )
            score = _number(raw.get("score"), question.question_id)
            if not min(levels) <= score <= max(levels):
                raise ValueError(f"Predicted score outside rubric for {question.question_id}")
            confidence = _probability(raw.get("confidence"), question.question_id)
            parsed[question.question_id] = {
                "value": score,
                "level": max(levels, key=lambda level: probabilities[str(level)]),
                "probabilities": probabilities,
                "confidence": confidence,
            }
        else:
            probability = _probability(raw.get("noul"), question.question_id)
            parsed[question.question_id] = {
                "value": probability >= 0.5,
                "probability": probability,
                "confidence": max(probability, 1 - probability),
            }
    return parsed


def _choice_report(truth: list[Any], answers: list[Any], classes: list[str]) -> dict[str, Any]:
    labels = [str(value) for value in truth]
    predictions = [str(answer["value"]) if answer is not None else None for answer in answers]
    report = _classification(labels, predictions, classes)
    probabilities = [answer["probabilities"] if answer is not None else None for answer in answers]
    confidence_correct = [
        (float(answer["confidence"]), answer["value"] == gold)
        for gold, answer in zip(labels, answers, strict=True)
        if answer is not None
    ]
    report.update(
        {
            "primitive": "choice",
            "brier": _multiclass_brier(labels, probabilities, classes),
            "ece": _ece(confidence_correct),
            "selective": _selective(confidence_correct),
        }
    )
    return report


def _score_report(truth: list[Any], answers: list[Any], levels: list[int]) -> dict[str, Any]:
    gold = [int(value) for value in truth]
    predicted_levels = [int(answer["level"]) if answer is not None else None for answer in answers]
    successful = [
        (g, answer) for g, answer in zip(gold, answers, strict=True) if answer is not None
    ]
    confidence_correct = [
        (float(answer["confidence"]), int(answer["level"]) == g) for g, answer in successful
    ]
    return {
        "primitive": "score",
        "total_count": len(gold),
        "evaluated_count": len(successful),
        "mae": (
            sum(abs(float(answer["value"]) - g) for g, answer in successful) / len(successful)
            if successful
            else None
        ),
        "quadratic_weighted_kappa": _quadratic_weighted_kappa(gold, predicted_levels, levels),
        "accuracy": sum(p == g for p, g in zip(predicted_levels, gold, strict=True)) / len(gold),
        "brier": _multiclass_brier(
            [str(value) for value in gold],
            [answer["probabilities"] if answer is not None else None for answer in answers],
            [str(level) for level in levels],
        ),
        "ece": _ece(confidence_correct),
        "selective": _selective(confidence_correct),
    }


def _noul_report(truth: list[Any], answers: list[Any]) -> dict[str, Any]:
    gold = [bool(value) for value in truth]
    predicted = [bool(answer["value"]) if answer is not None else None for answer in answers]
    probabilities = [
        float(answer["probability"]) if answer is not None else None for answer in answers
    ]
    tp = sum(p is True and g for p, g in zip(predicted, gold, strict=True))
    fp = sum(p is True and not g for p, g in zip(predicted, gold, strict=True))
    fn = sum(p is not True and g for p, g in zip(predicted, gold, strict=True))
    tn = sum(p is False and not g for p, g in zip(predicted, gold, strict=True))
    confidence_correct = [
        (float(answer["confidence"]), bool(answer["value"]) == g)
        for g, answer in zip(gold, answers, strict=True)
        if answer is not None
    ]
    successful_pairs = [
        (g, probability)
        for g, probability in zip(gold, probabilities, strict=True)
        if probability is not None
    ]
    return {
        "primitive": "noul",
        "total_count": len(gold),
        "evaluated_count": len(successful_pairs),
        "precision": _ratio(tp, tp + fp),
        "recall": _ratio(tp, tp + fn),
        "f1": _f1(tp, fp, fn),
        "accuracy": (tp + tn) / len(gold),
        "auroc": _auroc(successful_pairs),
        "auprc": _auprc(successful_pairs),
        "brier": (
            sum((probability - int(g)) ** 2 for g, probability in successful_pairs)
            / len(successful_pairs)
            if successful_pairs
            else None
        ),
        "ece": _ece(confidence_correct),
        "selective": _selective(confidence_correct),
        "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
    }


def _classification(
    truth: list[str], predictions: list[str | None], classes: list[str]
) -> dict[str, Any]:
    per_class: dict[str, Any] = {}
    matrix = {actual: {predicted: 0 for predicted in classes} for actual in classes}
    for actual, predicted in zip(truth, predictions, strict=True):
        if predicted is not None:
            matrix[actual][predicted] += 1
    f1_values: list[float] = []
    for class_name in classes:
        tp = sum(
            actual == class_name and predicted == class_name
            for actual, predicted in zip(truth, predictions, strict=True)
        )
        fp = sum(
            actual != class_name and predicted == class_name
            for actual, predicted in zip(truth, predictions, strict=True)
        )
        fn = sum(
            actual == class_name and predicted != class_name
            for actual, predicted in zip(truth, predictions, strict=True)
        )
        f1 = _f1(tp, fp, fn)
        f1_values.append(f1)
        per_class[class_name] = {
            "support": sum(actual == class_name for actual in truth),
            "precision": _ratio(tp, tp + fp),
            "recall": _ratio(tp, tp + fn),
            "f1": f1,
        }
    return {
        "total_count": len(truth),
        "evaluated_count": sum(value is not None for value in predictions),
        "accuracy": sum(
            actual == predicted for actual, predicted in zip(truth, predictions, strict=True)
        )
        / len(truth),
        "macro_f1": sum(f1_values) / len(f1_values),
        "per_class": per_class,
        "confusion_matrix": matrix,
    }


def _multiclass_brier(
    truth: list[str], probabilities: list[dict[str, float] | None], classes: list[str]
) -> float | None:
    rows = [(gold, values) for gold, values in zip(truth, probabilities, strict=True) if values]
    if not rows:
        return None
    return sum(
        sum((values[class_name] - float(class_name == gold)) ** 2 for class_name in classes)
        / len(classes)
        for gold, values in rows
    ) / len(rows)


def _ece(values: list[tuple[float, bool]], bins: int = 10) -> float | None:
    if not values:
        return None
    total = len(values)
    result = 0.0
    for index in range(bins):
        low = index / bins
        high = (index + 1) / bins
        group = [
            item
            for item in values
            if low <= item[0] <= high and (index == bins - 1 or item[0] < high)
        ]
        if group:
            confidence = sum(item[0] for item in group) / len(group)
            accuracy = sum(item[1] for item in group) / len(group)
            result += len(group) / total * abs(confidence - accuracy)
    return result


def _selective(values: list[tuple[float, bool]]) -> list[dict[str, float | int | None]]:
    total = len(values)
    result: list[dict[str, float | int | None]] = []
    for threshold in SELECTIVE_THRESHOLDS:
        accepted = [correct for confidence, correct in values if confidence >= threshold]
        result.append(
            {
                "threshold": threshold,
                "accepted": len(accepted),
                "coverage": len(accepted) / total if total else 0.0,
                "accuracy": sum(accepted) / len(accepted) if accepted else None,
                "risk": 1 - sum(accepted) / len(accepted) if accepted else None,
            }
        )
    return result


def _quadratic_weighted_kappa(
    truth: list[int], predictions: list[int | None], levels: list[int]
) -> float | None:
    pairs = [
        (actual, predicted)
        for actual, predicted in zip(truth, predictions, strict=True)
        if predicted is not None
    ]
    if not pairs or len(levels) < 2:
        return None
    index = {value: position for position, value in enumerate(levels)}
    actual_counts = {value: 0 for value in levels}
    predicted_counts = {value: 0 for value in levels}
    observed = 0.0
    scale = (len(levels) - 1) ** 2
    for actual, predicted in pairs:
        actual_counts[actual] += 1
        predicted_counts[predicted] += 1
        observed += (index[actual] - index[predicted]) ** 2 / scale
    expected = sum(
        actual_counts[actual]
        * predicted_counts[predicted]
        / len(pairs)
        * ((index[actual] - index[predicted]) ** 2 / scale)
        for actual in levels
        for predicted in levels
    )
    return 1 - observed / expected if expected else (1.0 if observed == 0 else None)


def _auroc(pairs: list[tuple[bool, float]]) -> float | None:
    positives = [score for label, score in pairs if label]
    negatives = [score for label, score in pairs if not label]
    if not positives or not negatives:
        return None
    wins = sum(
        (positive > negative) + 0.5 * (positive == negative)
        for positive in positives
        for negative in negatives
    )
    return wins / (len(positives) * len(negatives))


def _auprc(pairs: list[tuple[bool, float]]) -> float | None:
    positives = sum(label for label, _ in pairs)
    if not positives:
        return None
    ordered = sorted(pairs, key=lambda item: item[1], reverse=True)
    true_positives = 0
    precision_sum = 0.0
    for rank, (label, _) in enumerate(ordered, start=1):
        if label:
            true_positives += 1
            precision_sum += true_positives / rank
    return precision_sum / positives


def _percentiles(values: list[float]) -> dict[str, float | None]:
    return {
        name: _percentile(values, quantile)
        for name, quantile in (("p50", 0.5), ("p95", 0.95), ("p99", 0.99))
    }


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _distribution(value: object, keys: list[str], label: str) -> dict[str, float]:
    raw = _object(value, f"probabilities for {label}")
    if set(raw) != set(keys):
        raise ValueError(f"Probability keys do not match schema for {label}")
    result = {key: _probability(raw[key], label) for key in keys}
    if abs(sum(result.values()) - 1.0) > 0.02:
        raise ValueError(f"Probabilities must sum approximately to one for {label}")
    return result


def _unique_rows(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        raise ValueError(f"JSONL file does not exist: {path}")
    result: dict[str, dict[str, Any]] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"Expected object at {path}:{number}")
        feedback_id = _text(value, "feedback_id")
        if feedback_id in result:
            raise ValueError(f"Duplicate feedback id at {path}:{number}")
        result[feedback_id] = value
    return result


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: dict[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result.strip():
        raise ValueError(f"{key} must be non-blank text")
    return result


def _number(value: object, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be a finite number")
    return result


def _answer(value: dict[str, Any] | None, question_id: str) -> dict[str, Any] | None:
    return value.get(question_id) if value is not None else None


def _probability(value: object, label: str) -> float:
    result = _number(value, label)
    if not 0 <= result <= 1:
        raise ValueError(f"{label} must be within [0, 1]")
    return result


def _optional_nonnegative_int(value: object, label: str) -> int:
    if value is None:
        return 0
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer or null")
    return value


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _f1(tp: int, fp: int, fn: int) -> float:
    return _ratio(2 * tp, 2 * tp + fp + fn)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _format_metric(value: object) -> str:
    return "n/a" if value is None else f"{_number(value, 'metric'):.4f}"


def write_report(report: dict[str, Any], output: Path, markdown: Path | None = None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if markdown is not None:
        markdown.parent.mkdir(parents=True, exist_ok=True)
        markdown.write_text(render_report_markdown(report), encoding="utf-8")
