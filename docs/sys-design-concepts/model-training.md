# System Design Concepts — model-training

> Quiz log for the `model-training` service.
> Reference: "Designing Data-Intensive Applications" — Martin Kleppmann
> Concepts scored ≥ 80% are deprioritised in future sessions.

---

## Concept Coverage

| Concept | Times Tested | Best Score | Last Tested |
|---|---|---|---|
| Columnar storage / Parquet | 1 | 100% | 2026-05-04 |
| Batch vs stream processing | 1 | 0% | 2026-05-04 |
| Temporal vs random split | 1 | 100% | 2026-05-04 |
| Temporal leakage (scenario) | 1 | 100% | 2026-05-04 |
| Training/serving skew | 1 | 100% | 2026-05-04 |
| Feature schema contract | 1 | 100% | 2026-05-04 |
| Model versioning / promotion gates | 1 | 100% | 2026-05-04 |
| Offline vs online feature store | 1 | 100% | 2026-05-04 |
| Data lineage / reproducibility | 1 | 100% | 2026-05-04 |
| Feature vector ordering | 1 | 0% | 2026-05-04 |
| Artifact store proxy | 1 | 100% | 2026-05-04 |
| Genre leakage protection | 1 | 100% | 2026-05-04 |

---

## Sessions

### 2026-05-04 · End-to-end batch ML training pipeline

**Score: 10/12 (83%)**
**Concepts tested:** Columnar storage / Parquet, Batch vs stream processing, Temporal vs random split, Temporal leakage, Training/serving skew, Feature schema contract, Model versioning / promotion gates, Offline vs online feature store, Data lineage / reproducibility, Feature vector ordering, Artifact store proxy, Genre leakage protection

---

**Q1 · [Concept] · Columnar storage / Parquet**
Why is Parquet chosen for the offline feature store over a row-oriented format like CSV or JSONL?

- A) Parquet compresses better because it uses gzip, which CSV cannot
- B) Parquet stores data column-by-column, so the training pipeline can read only needed columns without scanning unneeded fields
- C) Parquet is the only format that supports date-based directory partitioning
- D) Parquet enforces schema at write time while CSV does not

**User answered:** B · **Correct:** B · ✓

> Parquet's columnar layout means reading only `avg_watch_duration` and `watch_count_10min` physically reads only those two column chunks — skipping all others. CSV/JSONL are row-oriented: reading any column requires scanning every byte of every row. This is why Parquet is the standard offline store format in feature stores.
> DDIA ref: Chapter 3 — Column-Oriented Storage

---

**Q2 · [Trade-off] · Batch vs stream processing**
The training pipeline reads from Parquet snapshots rather than consuming directly from Kafka. What is the primary trade-off?

- A) Batch training is slower but produces simpler, more reproducible runs against a stable, versioned snapshot
- B) Batch training produces better models because Parquet stores more features than Kafka messages carry
- C) Batch training is cheaper because Kafka charges per message consumed
- D) Batch training avoids schema validation problems that appear when reading Kafka directly

**User answered:** B · **Correct:** A · ✗

> Parquet doesn't store more features than Kafka. The real advantage is reproducibility: training against a stable, bounded snapshot means re-running on the same files produces the same dataset. The trade-off is freshness — Parquet lags real-time by flush cycle latency. DDIA Ch 10 captures this as the core batch processing property: bounded, replayable input → deterministic output.
> DDIA ref: Chapter 10 — Batch Processing

---

**Q3 · [Concept] · Temporal vs random split**
Why does the pipeline use a chronological split rather than a random 80/20 split?

- A) Chronological split is faster — sorting dates is O(n log n) while random sampling requires an RNG
- B) Chronological split prevents the model from seeing future data during training — a random split would produce overly optimistic metrics
- C) Random splits produce imbalanced class distributions; chronological splits do not
- D) MLflow requires chronological splits to log metrics correctly

**User answered:** B · **Correct:** B · ✓

> A random split lets the model train on May data and validate on April data — validating on the past while trained on the future. Chronological split mirrors real deployment: always trained on history, always predicting forward.
> DDIA ref: Chapter 11 — Stream Processing (ordering guarantees)

---

**Q4 · [Scenario] · Temporal leakage**
A new engineer replaces the chronological split with sklearn's random train_test_split. Training AUC stays at ~0.95. What is the most likely production consequence?

- A) No consequence — AUC is high so the model is clearly working well
- B) The model performs worse than expected because temporal degradation is masked by future data in training
- C) The model fails to load because MLflow expects chronological metadata
- D) The model overfits because random splits always use a fixed seed

**User answered:** B · **Correct:** B · ✓

> The high AUC is the danger signal. Future rows in the training set let the model learn temporal patterns unavailable at real prediction time. In production, where it always predicts forward, those learned shortcuts disappear and performance degrades.

---

**Q5 · [Trade-off] · Training/serving skew**
session_genre_vector is stored as JSON and expanded into per-genre columns at training time. What skew risk does this create?

- A) JSON parsing is slow, increasing training time and causing timeouts
- B) A new genre at inference time with no training rows creates a missing feature — the API must zero-fill or reject
- C) JSON is not schema-enforced, so malformed vectors could corrupt model weights
- D) Redis stores session_genre_vector as a hash, not a string, so values differ between training and serving

**User answered:** B · **Correct:** B · ✓

> The schema contract bakes in the genre list at training time. A new genre in production has no model weight — the API must explicitly handle it. This is a forward compatibility problem: the producer (feature pipeline) can add values; the consumer (model) was compiled against an older schema.
> DDIA ref: Chapter 4 — Encoding and Evolution (forward compatibility)

---

**Q6 · [Concept] · Feature schema contract as schema registry**
What role does feature_schema.json logged in MLflow play that a schema registry also plays?

- A) It enforces features are present in every Kafka message before reaching the feature pipeline
- B) It provides a versioned, model-co-located record of expected features — allowing the inference API to validate the feature vector before scoring
- C) It compresses feature data to reduce Redis memory footprint
- D) It replaces Parquet schema validation and is the only place feature types are defined

**User answered:** B · **Correct:** B · ✓

> Co-locating the schema with the model artifact in MLflow means the schema version always travels with the model version — the key property a registry provides. Without it, a model retrained on a different feature set could silently produce garbage predictions.
> DDIA ref: Chapter 4 — Encoding and Evolution

---

**Q7 · [Scenario] · Model versioning / promotion gates**
A corrupted model is accidentally registered as version 4 with the staging alias. What happens?

- A) The inference API ignores it — corrupted features are detected via feature_schema.json
- B) The inference API continues serving version 3 — MLflow aliases are immutable once set
- C) Within ~30s the inference API loads version 4 and serves degraded recommendations — alias promotion was the only gate
- D) MLflow's built-in AUC check rejects models below 0.5

**User answered:** C · **Correct:** C · ✓

> The alias is the only gate. feature_schema.json validates shape, not quality. A CI-enforced quality threshold before set_registered_model_alias would close this gap.
> DDIA ref: Chapter 12 — Future of Data Systems (end-to-end correctness)

---

**Q8 · [Trade-off] · Offline vs online feature store**
What is the main risk of the dual-store design (Redis for inference, Parquet for training)?

- A) Redis and Parquet can drift out of sync — the model trains on a different distribution than it serves
- B) Redis is more expensive than Parquet at scale
- C) Redis may contain stale features during Kafka lag, making training data less fresh than inference data
- D) Parquet enforces types while Redis does not, so training and inference run on different type systems

**User answered:** A · **Correct:** A · ✓

> Both stores must be kept in sync by the feature pipeline. A failed Parquet flush or an added Redis field not reflected in the schema means training and serving diverge. This is why PARQUET_SCHEMA and the Redis hash format are defined from the same source.
> DDIA ref: Chapter 3 — Storage and Retrieval; Chapter 11 — Stream Processing

---

**Q9 · [Concept] · Data lineage / reproducibility**
MLflow logs training_date_range_days, validation_split_days, and parquet_base_path alongside each model. What property does this support?

- A) Latency — fewer params makes the MLflow API call faster
- B) Reproducibility — given the same params and Parquet snapshot, a future run produces an equivalent model
- C) Fairness — logging input params ensures no demographic bias is encoded
- D) Monitoring — MLflow uses these to populate Grafana automatically

**User answered:** B · **Correct:** B · ✓

> If model version 7 behaves unexpectedly, the logged params tell you exactly which date range and split produced it — you can reconstruct the training dataset and retrain to compare. Deterministic function + logged, bounded input = replayable audit trail.
> DDIA ref: Chapter 10 — Batch Processing

---

**Q10 · [Scenario] · Feature vector ordering**
The inference API assembles the feature vector in alphabetical order rather than schema order. What happens?

- A) Nothing — LightGBM uses feature names, not positions, so column order does not affect predictions
- B) The model silently produces incorrect predictions because the booster was trained on schema-ordered input
- C) MLflow raises a validation error because feature order doesn't match the logged schema
- D) The inference API crashes because the feature vector length mismatches the model's expected input

**User answered:** B · **Correct:** A · ✗

> LightGBM's booster stores feature names alongside each split threshold and uses names — not positional indices — to route predictions. Column order is irrelevant as long as names match. This differs from raw numpy arrays without named columns, where swapping order silently corrupts predictions.

---

**Q11 · [Trade-off] · Artifact store proxy**
Why configure MLflow with --serve-artifacts and mlflow-artifacts:/ instead of a direct local path?

- A) mlflow-artifacts:/ is required for model versioning; direct paths only support experiment tracking
- B) It decouples artifact storage from the client — uploads go via HTTP regardless of whether storage is a local volume, S3, or GCS
- C) It encrypts artifact data in transit
- D) Direct local paths are deprecated in MLflow 2.x

**User answered:** B · **Correct:** B · ✓

> When the artifact root is a local path, the client writes directly to it — requiring shared filesystem access. The Docker volume is inside the container; the host-side script cannot reach it. --serve-artifacts proxies all uploads via HTTP so any client reaching localhost:5001 can upload regardless of storage topology.

---

**Q12 · [Trade-off] · Genre leakage protection**
What would go wrong if genres were derived from the full dataset (train + val combined) before splitting?

- A) Nothing — more data gives a more complete schema contract
- B) Data leakage: val-only genres appear as all-zero training columns — the model learns spurious signal, not real genre preference
- C) Training time increases because the feature matrix has more columns
- D) The schema contract would include genres not in Redis, breaking inference

**User answered:** B · **Correct:** B · ✓

> A genre appearing only in the val period gets added as a column, but all training rows have zero for it. The model learns `genre_new = 0` correlates with training-period outcomes — noise. At inference time, a real non-zero value hits a weight anchored to corrupted signal. A subtler form of the same temporal leakage from Q3/Q4.
