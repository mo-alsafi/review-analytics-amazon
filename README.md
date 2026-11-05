
# Customer Review Analytics — Amazon Appliances

## Business Problem

The marketplace category team needs to identify which customer problems
should receive priority investigation and determine whether star ratings
reliably represent customer experience.

## Project Objectives

- Measure customer sentiment from written reviews.
- Identify and validate recurring complaint themes.
- Analyze complaint prevalence, severity, and trends.
- Identify products requiring further investigation.
- Evaluate sentiment classification against human-labeled reviews.
- Assess the reliability of star ratings compared with written sentiment.

## Dataset

- **Source:** Amazon Reviews 2023 — McAuley Lab, UCSD
- **Category:** Appliances
- **Review period:** May 1996 – September 2023 (dataset-wide)
- **Format:** JSONL.GZ
- **Processing format:** Parquet

Raw review data is excluded from this repository.

## Analytical Protocol

The project uses:

- Human-labeled gold-set evaluation.
- Time-based and product-held-out validation.
- Sentiment classification baselines.
- Validated complaint-theme extraction.
- Statistical uncertainty for product-level comparisons.
- Historical backtesting of product alerts.

## Repository Structure

```text
data/
notebooks/
src/
sql/
tests/
reports/
```

## Reproduction

Environment setup and pipeline execution instructions will
be documented as the project develops.

## Limitations

Customer reviews represent reported experiences, not verified
product defects or established root causes.

## Dataset Citation

Hou, Y., Li, J., He, Z., Yan, A., Chen, X., & McAuley, J. (2024).
Bridging Language and Items for Retrieval and Recommendation.
arXiv:2403.03952.

https://arxiv.org/abs/2403.03952
