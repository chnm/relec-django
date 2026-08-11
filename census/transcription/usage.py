"""Pricing snapshots and read-only Claude usage reporting."""

import json
import math
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import models

from census.models import TranscriptionJob, TranscriptionRun


PRICING_SCHEMA_VERSION = 1
RATE_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_creation_1h_input_tokens",
    "cache_read_input_tokens",
)
MILLION = Decimal("1000000")
MONEY_QUANTUM = Decimal("0.000001")
COST_CHART_COLORS = (
    "#0060b1",
    "#7c3aed",
    "#0f766e",
    "#b45309",
    "#be123c",
    "#4d7c0f",
)
USAGE_EXPORT_FIELDS = (
    "run_key",
    "model",
    "contract_version",
    "application_revision",
    "job_custom_id",
    "schedule_pk",
    "resource_id",
    "state",
    "attempt",
    "queued_at",
    "submitted_at",
    "completed_at",
    "duration_seconds",
    "input_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
    "total_input_tokens",
    "output_tokens",
    "estimated_cost",
    "currency",
    "pricing_effective_date",
    "pricing_valid_through",
    "pricing_service_tier",
    "pricing_source",
    "input_rate_per_million",
    "output_rate_per_million",
    "cache_creation_rate_per_million",
    "cache_creation_1h_rate_per_million",
    "cache_read_rate_per_million",
    "usage_json",
    "error_type",
    "error_message",
)


class PricingConfigurationError(ValueError):
    """Raised when a run cannot freeze a usable pricing snapshot."""


def _decimal_rate(value, field):
    try:
        rate = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise PricingConfigurationError(
            f"Claude pricing rate {field!r} must be a decimal number."
        ) from exc
    if not rate.is_finite() or rate < 0:
        raise PricingConfigurationError(
            f"Claude pricing rate {field!r} must be a non-negative decimal."
        )
    return rate


def pricing_snapshot_for_model(catalog, model, *, as_of=None):
    """Validate a configured catalog and select immutable rates for one model."""
    if not isinstance(catalog, dict):
        raise PricingConfigurationError("Claude pricing must be a JSON object.")
    if catalog.get("schema_version") != PRICING_SCHEMA_VERSION:
        raise PricingConfigurationError(
            f"Claude pricing schema_version must be {PRICING_SCHEMA_VERSION}."
        )

    models = catalog.get("models")
    model_config = models.get(model) if isinstance(models, dict) else None
    if not isinstance(model_config, dict):
        raise PricingConfigurationError(
            f"No Claude Batch pricing is configured for model {model!r}."
        )
    rates = model_config.get("rates")
    if not isinstance(rates, dict):
        raise PricingConfigurationError(
            f"Claude pricing for model {model!r} must include rates."
        )

    missing = [field for field in RATE_FIELDS if field not in rates]
    if missing:
        raise PricingConfigurationError(
            "Claude pricing is missing rate(s): " + ", ".join(missing) + "."
        )
    normalized_rates = {
        field: format(_decimal_rate(rates[field], field), "f") for field in RATE_FIELDS
    }

    required_metadata = ("currency", "unit", "service_tier", "effective_date", "source")
    metadata = {
        field: model_config.get(field, catalog.get(field))
        for field in required_metadata
    }
    missing_metadata = [field for field, value in metadata.items() if not value]
    if missing_metadata:
        raise PricingConfigurationError(
            "Claude pricing is missing metadata: " + ", ".join(missing_metadata) + "."
        )
    if metadata["unit"] != "per_million_tokens":
        raise PricingConfigurationError(
            "Claude pricing unit must be 'per_million_tokens'."
        )
    valid_through = model_config.get("valid_through")
    if valid_through:
        try:
            valid_through_date = date.fromisoformat(str(valid_through))
        except ValueError as exc:
            raise PricingConfigurationError(
                "Claude pricing valid_through must use YYYY-MM-DD."
            ) from exc
        if valid_through_date < (as_of or date.today()):
            raise PricingConfigurationError(
                f"Claude pricing for model {model!r} expired on {valid_through}."
            )

    snapshot = {
        "schema_version": PRICING_SCHEMA_VERSION,
        "currency": str(metadata["currency"]),
        "unit": metadata["unit"],
        "service_tier": str(metadata["service_tier"]),
        "effective_date": str(metadata["effective_date"]),
        "source": str(metadata["source"]),
        "model": model,
        "rates": normalized_rates,
    }
    if valid_through:
        snapshot["valid_through"] = str(valid_through)
    return snapshot


def configured_pricing_snapshots(catalog, models):
    """Return valid snapshots and validation messages for the launch UI."""
    snapshots = {}
    errors = {}
    for model in models:
        try:
            snapshots[model] = pricing_snapshot_for_model(catalog, model)
        except PricingConfigurationError as exc:
            errors[model] = str(exc)
    return snapshots, errors


def _run_snapshot(run):
    snapshot = (run.metadata or {}).get("pricing_snapshot")
    if not isinstance(snapshot, dict) or snapshot.get("model") != (
        run.metadata or {}
    ).get("model"):
        return None
    if snapshot.get("schema_version") != PRICING_SCHEMA_VERSION:
        return None
    rates = snapshot.get("rates")
    if not isinstance(rates, dict) or any(field not in rates for field in RATE_FIELDS):
        return None
    try:
        return {
            **snapshot,
            "rates": {
                field: _decimal_rate(rates[field], field) for field in RATE_FIELDS
            },
        }
    except PricingConfigurationError:
        return None


def job_cost_breakdown(job):
    """Estimate one job from its run's frozen rates and provider token usage."""
    if not any(
        value is not None
        for value in (
            job.input_tokens,
            job.output_tokens,
            job.cache_creation_input_tokens,
            job.cache_read_input_tokens,
        )
    ):
        return None

    snapshot = _run_snapshot(job.run)
    if snapshot is None:
        return None
    valid_through = snapshot.get("valid_through")
    billed_at = job.submitted_at or job.completed_at
    if valid_through and billed_at:
        try:
            if billed_at.date() > date.fromisoformat(valid_through):
                return None
        except ValueError:
            return None
    rates = snapshot["rates"]
    usage = job.usage if isinstance(job.usage, dict) else {}
    cache_detail = usage.get("cache_creation")
    cache_detail = cache_detail if isinstance(cache_detail, dict) else {}

    cache_total = job.cache_creation_input_tokens or 0
    cache_5m = min(int(cache_detail.get("ephemeral_5m_input_tokens") or 0), cache_total)
    cache_1h = min(
        int(cache_detail.get("ephemeral_1h_input_tokens") or 0),
        max(cache_total - cache_5m, 0),
    )
    cache_unspecified = max(cache_total - cache_5m - cache_1h, 0)
    token_counts = {
        "input_tokens": job.input_tokens or 0,
        "output_tokens": job.output_tokens or 0,
        "cache_creation_input_tokens": cache_unspecified + cache_5m,
        "cache_creation_1h_input_tokens": cache_1h,
        "cache_read_input_tokens": job.cache_read_input_tokens or 0,
    }
    costs = {
        field: (Decimal(count) * rates[field] / MILLION)
        for field, count in token_counts.items()
    }
    total = sum(costs.values(), Decimal("0")).quantize(MONEY_QUANTUM)
    return {
        "currency": snapshot["currency"],
        "total": total,
        "components": costs,
        "token_counts": token_counts,
        "pricing_snapshot": snapshot,
    }


def _percentile(values, percentile):
    if not values:
        return 0
    ordered = sorted(values)
    index = max(math.ceil(percentile * len(ordered)) - 1, 0)
    return ordered[index]


def _summarize_jobs(jobs):
    terminal_failure_states = {
        TranscriptionJob.State.FAILED,
        TranscriptionJob.State.EXPIRED,
        TranscriptionJob.State.CANCELED,
        TranscriptionJob.State.INVALID,
        TranscriptionJob.State.NEEDS_RECOVERY,
    }
    jobs = list(jobs)
    succeeded = sum(job.state == TranscriptionJob.State.SUCCEEDED for job in jobs)
    failed = sum(job.state in terminal_failure_states for job in jobs)
    input_totals = [job.total_input_tokens for job in jobs if job.usage is not None]
    output_totals = [job.output_tokens or 0 for job in jobs if job.usage is not None]
    priced_jobs = 0
    priced_successes = 0
    unpriced_jobs = 0
    total_cost = Decimal("0")
    currencies = set()
    for job in jobs:
        if job.usage is None:
            continue
        cost = job_cost_breakdown(job)
        if cost is None:
            unpriced_jobs += 1
            continue
        priced_jobs += 1
        if job.state == TranscriptionJob.State.SUCCEEDED:
            priced_successes += 1
        total_cost += cost["total"]
        currencies.add(cost["currency"])

    completed = [job.completed_at for job in jobs if job.completed_at]
    submitted = [job.submitted_at for job in jobs if job.submitted_at]
    duration_seconds = None
    if submitted and completed:
        duration_seconds = max((max(completed) - min(submitted)).total_seconds(), 0)

    total_jobs = len(jobs)
    usage_jobs = len(input_totals)
    return {
        "total_jobs": total_jobs,
        "succeeded": succeeded,
        "failed": failed,
        "pending": total_jobs - succeeded - failed,
        "success_rate": (Decimal(succeeded) * 100 / total_jobs) if total_jobs else None,
        "usage_jobs": usage_jobs,
        "priced_jobs": priced_jobs,
        "priced_successes": priced_successes,
        "unpriced_jobs": unpriced_jobs,
        "total_input_tokens": sum(input_totals),
        "total_output_tokens": sum(output_totals),
        "mean_input_tokens": (sum(input_totals) / usage_jobs) if usage_jobs else 0,
        "median_input_tokens": _percentile(input_totals, 0.5),
        "p95_input_tokens": _percentile(input_totals, 0.95),
        "mean_output_tokens": (sum(output_totals) / usage_jobs) if usage_jobs else 0,
        "median_output_tokens": _percentile(output_totals, 0.5),
        "p95_output_tokens": _percentile(output_totals, 0.95),
        "total_cost": total_cost.quantize(MONEY_QUANTUM),
        "currency": (
            currencies.pop()
            if len(currencies) == 1
            else "Mixed"
            if currencies
            else "USD"
        ),
        "cost_per_success": (
            (total_cost / priced_successes).quantize(MONEY_QUANTUM)
            if priced_successes
            else None
        ),
        "duration_seconds": duration_seconds,
        "throughput_per_minute": (
            Decimal(succeeded) * 60 / Decimal(str(duration_seconds))
            if succeeded and duration_seconds
            else None
        ),
    }


def _cost_per_success_chart(run_summaries, *, limit=10):
    """Prepare a compact, dependency-free chart from recent priced runs."""
    priced_runs = [
        summary for summary in run_summaries if summary["cost_per_success"] is not None
    ][:limit]
    if not priced_runs:
        return []

    maximum = max(summary["cost_per_success"] for summary in priced_runs)
    model_colors = {}
    chart = []
    for summary in priced_runs:
        model = summary["model"] or "Unknown model"
        if model not in model_colors:
            model_colors[model] = COST_CHART_COLORS[
                len(model_colors) % len(COST_CHART_COLORS)
            ]
        value = summary["cost_per_success"]
        width = Decimal("0") if maximum == 0 else value * 100 / maximum
        chart.append(
            {
                "run": summary["run"],
                "model": model,
                "color": model_colors[model],
                "cost_per_success": value,
                "total_cost": summary["total_cost"],
                "priced_successes": summary["priced_successes"],
                "width_percent": format(width.quantize(Decimal("0.01")), "f"),
                "currency": summary["currency"],
            }
        )
    return chart


def usage_report():
    """Build overall and per-run efficiency reporting from immutable evidence."""
    runs = list(
        TranscriptionRun.objects.filter(kind="agent").prefetch_related(
            models.Prefetch(
                "transcription_jobs",
                queryset=TranscriptionJob.objects.select_related("run").only(
                    "id",
                    "run_id",
                    "state",
                    "usage",
                    "input_tokens",
                    "output_tokens",
                    "cache_creation_input_tokens",
                    "cache_read_input_tokens",
                    "submitted_at",
                    "completed_at",
                ),
            )
        )
    )
    all_jobs = []
    run_summaries = []
    for run in runs:
        jobs = list(run.transcription_jobs.all())
        all_jobs.extend(jobs)
        summary = _summarize_jobs(jobs)
        summary.update(
            {
                "run": run,
                "model": (run.metadata or {}).get("model", ""),
                "prompt_version": (run.metadata or {}).get("contract_version", ""),
                "pricing_snapshot": (run.metadata or {}).get("pricing_snapshot"),
            }
        )
        run_summaries.append(summary)

    overall = _summarize_jobs(all_jobs)
    overall["total_runs"] = len(runs)
    return {
        "overall": overall,
        "runs": run_summaries,
        "cost_per_success_chart": _cost_per_success_chart(run_summaries),
    }


def historical_cost_estimates(*, report=None, minimum_successes=3):
    """Return model-level cost-per-success estimates when evidence is sufficient."""
    report = report or usage_report()
    aggregates = {}
    for summary in report["runs"]:
        model = summary["model"]
        if not model or not summary["priced_successes"]:
            continue
        aggregate = aggregates.setdefault(
            model,
            {
                "total_cost": Decimal("0"),
                "priced_successes": 0,
                "currencies": set(),
            },
        )
        aggregate["total_cost"] += summary["total_cost"]
        aggregate["priced_successes"] += summary["priced_successes"]
        aggregate["currencies"].add(summary["currency"])

    estimates = {}
    for model, aggregate in aggregates.items():
        successes = aggregate["priced_successes"]
        if successes < minimum_successes or len(aggregate["currencies"]) != 1:
            continue
        estimates[model] = {
            "cost_per_success": format(
                (aggregate["total_cost"] / successes).quantize(MONEY_QUANTUM),
                "f",
            ),
            "priced_successes": successes,
            "currency": next(iter(aggregate["currencies"])),
        }
    return estimates


def usage_export_rows():
    """Return one flat, reproducible reporting row per Claude job."""
    jobs = (
        TranscriptionJob.objects.filter(run__kind="agent")
        .select_related("run", "census_schedule")
        .only(
            "run__key",
            "run__metadata",
            "census_schedule__resource_id",
            "custom_id",
            "census_schedule_id",
            "state",
            "attempt",
            "queued_at",
            "submitted_at",
            "completed_at",
            "usage",
            "input_tokens",
            "output_tokens",
            "cache_creation_input_tokens",
            "cache_read_input_tokens",
            "error_type",
            "error_message",
        )
    )
    for job in jobs:
        metadata = job.run.metadata or {}
        snapshot = metadata.get("pricing_snapshot") or {}
        rates = snapshot.get("rates") or {}
        cost = job_cost_breakdown(job)
        duration_seconds = None
        if job.submitted_at and job.completed_at:
            duration_seconds = max(
                (job.completed_at - job.submitted_at).total_seconds(), 0
            )
        yield {
            "run_key": job.run.key,
            "model": metadata.get("model"),
            "contract_version": metadata.get("contract_version"),
            "application_revision": metadata.get("application_revision"),
            "job_custom_id": job.custom_id,
            "schedule_pk": job.census_schedule_id,
            "resource_id": job.census_schedule.resource_id,
            "state": job.state,
            "attempt": job.attempt,
            "queued_at": job.queued_at.isoformat() if job.queued_at else None,
            "submitted_at": job.submitted_at.isoformat() if job.submitted_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "duration_seconds": duration_seconds,
            "input_tokens": job.input_tokens,
            "cache_creation_input_tokens": job.cache_creation_input_tokens,
            "cache_read_input_tokens": job.cache_read_input_tokens,
            "total_input_tokens": job.total_input_tokens,
            "output_tokens": job.output_tokens,
            "estimated_cost": format(cost["total"], "f") if cost else None,
            "currency": cost["currency"] if cost else snapshot.get("currency"),
            "pricing_effective_date": snapshot.get("effective_date"),
            "pricing_valid_through": snapshot.get("valid_through"),
            "pricing_service_tier": snapshot.get("service_tier"),
            "pricing_source": snapshot.get("source"),
            "input_rate_per_million": rates.get("input_tokens"),
            "output_rate_per_million": rates.get("output_tokens"),
            "cache_creation_rate_per_million": rates.get("cache_creation_input_tokens"),
            "cache_creation_1h_rate_per_million": rates.get(
                "cache_creation_1h_input_tokens"
            ),
            "cache_read_rate_per_million": rates.get("cache_read_input_tokens"),
            "usage_json": json.dumps(job.usage, sort_keys=True) if job.usage else None,
            "error_type": job.error_type,
            "error_message": job.error_message,
        }
