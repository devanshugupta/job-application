Devanshu Gupta
dgupta77@asu.edu |
623-290-3858 | linkedin.com/in/devanshu0gupta
| github.com/devanshugupta
## Summary
Machine Learning Engineer at Amazon Prime Video building production retrieval, ranking, and recommendation systems serving 1M+ users. First-author EMNLP 2025 researcher in vector search and content understanding.
## Research Publications
Weaver: Interweaving SQL and LLM for Table Reasoning [EMNLP 2025 - First Author]
TraceBack: Multi-Agent Decomposition for Fine-Grained Table Attribution [TACL 2026, under review]
## Work Experience
### Amazon, Prime Video | Machine Learning Engineer (06/2025 -- Present)
- Shipped embedding-based retrieval and ranking pipeline (FAISS, KNN, NDCG) for Similar-to-X recommendations serving 1M users at 0.5s latency, improving CTR 16% via offline and online evaluation.
- Developed hybrid retrieval with an XGBoost classifier routing queries to parallel OpenSearch and catalog retrievers with LLM reranking, improving relevance 5% and cutting latency 50%.
- Trained a LoRA fine-tuned query router for the hybrid retrieval system, improving relevance 5% and cutting latency 50%; won internal hackathon and adopted for production.
- Cut duplicate recommendations 30% through caching and latest-per-turn deduplication, improving result freshness for the conversational assistant.
- Shipped semantic query-to-title retrieval with multilingual E5 embeddings on a SageMaker endpoint and ANN search over a FAISS index, feature-flagged for zero live-turn degradation.
### Tata Consultancy Services | Software Engineer (08/2021 -- 08/2023)
- Built scalable demand forecasting pipeline using Spark in Databricks and XGBoost, cutting supply chain costs by $4M.
- Designed distributed data pipelines on Airflow integrating 4+ data sources into unified storage, improving data consistency.
- Maintained Azure Data Lake Storage (ADLS Gen2) architecture storing terabytes of distributed data, ensuring high availability and scalable ingestion.
## Projects
### Hybrid Music Recommender ()
- Developed a content-based recommender over 10K songs using 30 audio and metadata features with collaborative-filtering signals and cold-start handling for new tracks.
### Image Search Engine ()
- Developed image search over 10K images using clustering and LSH vector indexing, reducing nearest-neighbor retrieval time from 1 hour to 30 seconds.
## Education
### Master of Science in Computer Science Arizona State University, Tempe, AZ, USA
05/2025 · GPA: 3.9/4
Coursework: Statistical Machine Learning, Cloud Computing, Data Mining, NLP, Multimedia & Web databases
### Bachelor of Technology in Computer Science & Engineering University Institute of Technology RGPV, India
06/2021 · GPA: 8.4/10
## Technical Skills
Languages: Python, SQL, Kotlin
ML: PyTorch, TensorFlow, scikit-learn, Koog, XGBoost, ranking (NDCG, Recall@K), LoRA/PEFT, model evaluation
Retrieval: FAISS, OpenSearch, vector search, hybrid retrieval, embeddings
Data: Spark, PySpark, Airflow