Devanshu Gupta
dgupta77@asu.edu |
623-290-3858 | linkedin.com/in/devanshu0gupta
| github.com/devanshugupta
## Summary
Data engineer with two years building large-scale ETL pipelines on Spark, Airflow, and Azure, plus Amazon ML data-contract work, focused on pipeline reliability and data quality.
## Research Publications
Weaver: Interweaving SQL and LLM for Table Reasoning [EMNLP 2025 - First Author]
TraceBack: Multi-Agent Decomposition for Fine-Grained Table Attribution [TACL 2026, under review]
## Work Experience
### Amazon, Prime Video | Machine Learning Engineer (06/2025 -- Present)
- Drove a five-team cross-org data contract joining explicit and voice feedback to assistant sessions, authoring the analytics-table schema and validating joins with Athena SQL against live data.
- Built embedding-based retrieval and ranking pipeline (FAISS, KNN, NDCG) for `Similar to X' recommendations serving 1M users at 0.5s end-to-end latency, improving CTR 16% via offline/online evaluation.
- Architected hybrid retrieval with an XGBoost classifier routing queries to parallel OpenSearch (FAISS) and catalog retrievers with multi-turn LLM reranking, improving relevance 5% and cutting latency 50%; adopted for production.
### Tata Consultancy Services | Software Engineer (08/2021 -- 08/2023)
- Developed distributed ETL pipelines on Airflow integrating 4+ heterogeneous data sources into unified storage, improving cross-team data consistency and availability.
- Rolled out data-quality validation and monitoring across ETL workflows, halving production pipeline failures and owning reliability from ingestion to consumption.
- Reworked a slow batch ETL job over large daily enterprise datasets from 2 hours to under 15 minutes through Spark parallelization.
- Delivered a demand-forecasting pipeline using Spark on Databricks and XGBoost, cutting supply-chain costs by $4M.
- Improved batch pipeline throughput 40% by optimizing the transformation, ingestion, and validation stages across production systems.
## Projects
### Hybrid Music Recommender |
- Built a content-based recommender over 10K songs using 30 audio and metadata features (MFCC, spectral, tempo) with collaborative-filtering signals, a MySQL history store, and cold-start handling for new tracks.
### Image Search Engine |
- Built end-to-end image search system on 10K images using clustering + LSH vector indexing, reducing nearest-neighbor retrieval time from 1 hour to 30 seconds.
### Elastic AWS Cloud Application for Face Recognition |
- Architected auto-scaling AWS (EC2, ELB, SQS, S3) Flask-based REST system handling 1,000 concurrent requests, enabling 30-second elastic shutdown and improved cost-efficient scaling.
## Education
### Master of Science in Computer Science Arizona State University, Tempe, AZ, USA
05/2025 · GPA: 3.9/4
Coursework: Statistical Machine Learning, Cloud Computing, Data Mining, NLP, Multimedia & Web databases
### Bachelor of Technology in Computer Science & Engineering University Institute of Technology RGPV, India
06/2021 · GPA: 8.4/10
## Technical Skills
Languages: Python, SQL, Kotlin
Data: Spark, PySpark, Airflow, ETL/ELT, data modeling, schema design, Kafka, Pandas
Warehouses/DBs: PostgreSQL, DynamoDB, ADLS, Databricks, Athena
Quality: data validation, monitoring
ML: PyTorch, scikit-learn, XGBoost