Devanshu Gupta
dgupta77@asu.edu |
623-290-3858 | linkedin.com/in/devanshu0gupta
| github.com/devanshugupta
## Summary
ML engineer at Amazon Prime Video building data and LLM pipelines for 1M+ users, with terabyte-scale Spark and Airflow pipeline engineering at Tata Consultancy Services. First-author EMNLP 2025 researcher.
## Research Publications
Weaver: Interweaving SQL and LLM for Table Reasoning [EMNLP 2025 - First Author]
TraceBack: Multi-Agent Decomposition for Fine-Grained Table Attribution [TACL 2026, under review]
## Work Experience
### Amazon, Prime Video | Machine Learning Engineer (06/2025 -- Present)
- Drove a five-team cross-org data contract joining explicit and voice feedback into assistant analytics, authoring the table schema and validating joins with Athena SQL against live data.
- Shipped an embedding retrieval and ranking pipeline (FAISS, ANN/kNN) feeding production models for 1M+ users at 0.5s end-to-end latency, lifting CTR 16%.
- Owned an automated evaluation loop labeling 50K+ conversations daily with LLM-as-judge and fact validation, raising defect discovery 60% without manual annotation.
- Resolved double-counted feedback events with latest-per-turn deduplication and fixed 3x session-table duplication, confirming no query-time regression through benchmarking.
- Optimized query-time retrieval by moving candidate filtering ahead of metadata fetch and bounding conversation cache to five turns, cutting cache payload 75% and memory 40% at peak.
### Tata Consultancy Services | Software Engineer (08/2021 -- 08/2023)
- Built scalable demand forecasting pipeline using Spark in Databricks and XGBoost, cutting supply chain costs by $4M.
- Designed distributed data pipelines on Airflow integrating 4+ data sources into unified storage, improving data consistency.
- Maintained Azure Data Lake Storage (ADLS Gen2) architecture storing terabytes of distributed data, ensuring high availability and scalable ingestion.
## Projects
### AdPrompter: Generative AI for Ads |
- Built the backend and rating components of an RL pipeline generating 50+ multimodal ad variants/product, improving Click Through Rate 25% with bias detection and text-to-video extensibility.
### Hybrid Music Recommender |
- Built a content-based recommender over 10K songs using 30 audio and metadata features (MFCC, spectral, tempo) with collaborative-filtering signals, a MySQL history store, and cold-start handling for new tracks.
### Image Search Engine |
- Built end-to-end image search system on 10K images using clustering + LSH vector indexing, reducing nearest-neighbor retrieval time from 1 hour to 30 seconds.
## Education
### Master of Science in Computer Science Arizona State University, Tempe, AZ, USA
05/2025 · GPA: 3.9/4
Coursework: Statistical Machine Learning, Cloud Computing, Data Mining, NLP, Multimedia & Web databases
### Bachelor of Technology in Computer Science & Engineering University Institute of Technology RGPV, India
06/2021 · GPA: 8.4/10
## Technical Skills
Languages: Python, SQL, Kotlin, Java, C++
Data: Spark, PySpark, Airflow, Kafka, Databricks, ETL, ADLS, PostgreSQL, DynamoDB
ML & LLM: PyTorch, TensorFlow, scikit-learn, Koog, XGBoost, RAG, LLM-as-Judge, LoRA Fine-tuning
Systems: Distributed Systems, REST, gRPC, Microservices, Docker, Kubernetes
Cloud: AWS (S3, EC2, Lambda, SageMaker, Athena), Azure (ADLS, Data Factory, Databricks)