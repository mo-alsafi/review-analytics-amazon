# Data Dictionary — Amazon Appliances Reviews

## 1. Dataset Overview

| Property | Description |
|---|---|
| Dataset | Amazon Reviews 2023 |
| Source | McAuley Lab, UCSD |
| Category | Appliances |
| Number of records | 2,128,605 |
| Number of columns | 10 |
| Storage format | Parquet |
| Review period | October 23, 2000 – September 12, 2023 |

## 2. Column Definitions

| Column | Data Type | Description | Available at Review Posting? |
|---|---|---|---|
| `rating` | DOUBLE | Customer's product rating, ranging from 1 to 5 stars. | Yes |
| `title` | VARCHAR | Short heading describing the customer's review. | Yes |
| `text` | VARCHAR | Main body of the customer's written review. May be empty. | Yes |
| `images` | STRUCT[] | List of images attached to the review, including image URLs and attachment type. | Uncertain; exact submission timing is not recorded. |
| `asin` | VARCHAR | Amazon Standard Identification Number identifying the reviewed product or variation. | Yes |
| `parent_asin` | VARCHAR | Parent product identifier used to group related product variations. | Yes |
| `user_id` | VARCHAR | Identifier representing the customer who submitted the review. | Yes |
| `timestamp` | BIGINT | Review creation timestamp stored as Unix time in milliseconds. | Yes |
| `helpful_vote` | BIGINT | Number of helpful votes received by the review. This value can accumulate after publication. | No; not reliably available at initial posting. |
| `verified_purchase` | BOOLEAN | Indicates whether the review is associated with a verified purchase. | Expected to be available at posting, but exact historical timing is not documented. |

## 3. Data Quality Observations

The initial validation identified the following:

| Observation | Count | Notes |
|---|---:|---|
| Total reviews | 2,128,605 | Complete dataset |
| Invalid ratings | 0 | All ratings are between 1 and 5 |
| Missing titles | 0 | All reviews have titles |
| Missing review bodies | 0 | No SQL NULL values in `text` |
| Blank review bodies | 2,065 | Records contain empty or whitespace-only text |
| Missing timestamps | 0 | All reviews have timestamps |
| Missing product identifiers | 0 | Both `asin` and `parent_asin` are populated |
| Missing reviewer identifiers | 0 | All reviews have a `user_id` |
| Missing verified-purchase values | 0 | All values are Boolean and non-null |

Blank review bodies are retained because their titles may still contain useful sentiment information.

## 4. Analytical Considerations

### Rating

Ratings will be used to generate initial training labels:

- 1–2 stars: Negative
- 3 stars: Neutral
- 4–5 stars: Positive

However, star ratings are not considered ground truth. Written sentiment can disagree with the assigned rating, so model evaluation will use a human-labeled gold set.

### Text and Title

Both fields will be considered when constructing the sentiment analysis input.

Reviews with empty bodies will not automatically be discarded if their titles contain usable text.

### Helpful Votes

Helpful votes are post-publication information that can accumulate over time.

They will be excluded from sentiment model features to avoid using information that would not reliably be available when a review is first posted.

### Product Identifiers

`asin` identifies the reviewed product or variation, while `parent_asin` provides a grouping identifier for related variations.

Parent product grouping will be considered when designing product-held-out validation to reduce information leakage between related products.

### Verified Purchase

This field will be retained for descriptive analysis and subgroup evaluation.

Its exact historical availability will need to be verified before considering it as a model feature.

### Timestamp

The original timestamp is stored in Unix milliseconds.

It will be converted to a datetime representation for time-based analysis, chronological splitting, and trend evaluation.

## 5. Modeling Feature Policy

The initial sentiment classification protocol will use review text and title only.

| Field | Modeling decision | Reason |
|---|---|---|
| `title` | Include | Contains written customer sentiment |
| `text` | Include | Contains written customer sentiment |
| `rating` | Exclude as a feature | Used to generate training labels |
| `helpful_vote` | Exclude | Post-publication information |
| `images` | Exclude | Image analysis is outside the initial project scope |
| `asin` | Exclude | Product identifier, not text sentiment |
| `parent_asin` | Exclude | Used for grouping and split design |
| `user_id` | Exclude | Reviewer identifier |
| `timestamp` | Exclude as a sentiment feature | Used for chronological splitting and trend analysis |
| `verified_purchase` | Exclude initially | Reserved for subgroup analysis; availability needs further verification |

---

**Document status:** Initial data dictionary based on the inspected Parquet schema and Phase 1 validation results.