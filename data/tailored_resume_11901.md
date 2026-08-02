Devanshu Gupta
dgupta77@asu.edu |
623-290-3858 | linkedin.com/in/devanshu0gupta
| github.com/devanshugupta
## Summary
Machine Learning Engineer building data pipelines, Spark processing, and Airflow orchestration that generate training data and power ML workflows at scale. Amazon Prime Video ML experience and first-author EMNLP 2025.
## Research Publications
Weaver: Interweaving SQL and LLM for Table Reasoning [EMNLP 2025 - First Author]
TraceBack: Multi-Agent Decomposition for Fine-Grained Table Attribution [TACL 2026, under review]
## Work Experience
### Amazon, Prime Video | Machine Learning Engineer (06/2025 -- Present)
- Built embedding-based retrieval and ranking pipeline (FAISS, KNN, NDCG) for `Similar to X' recommendations serving 1M users at 0.5s end-to-end latency, improving CTR 16% via offline/online evaluation.
- Architected hybrid retrieval with an XGBoost classifier routing queries to parallel OpenSearch (FAISS) and catalog retrievers with multi-turn LLM reranking, improving relevance 5% and cutting latency 50%; adopted for production.
- Trained a LoRA fine-tuned model as the query router for the hybrid retrieval system, improving relevance 5% and cutting latency 50%; won internal hackathon and was adopted for production.
### Tata Consultancy Services | Software Engineer (08/2021 -- 08/2023)
- Developed distributed Airflow data pipelines integrating 4+ sources into unified storage that fed downstream model training, improving data consistency across enterprise datasets.
- Optimized a PySpark ETL job from 2 hours to under 15 minutes through Spark parallelization, then lifted overall batch throughput 40% across production systems.
- Delivered a Spark and Databricks demand-forecasting pipeline with XGBoost over large daily datasets, cutting supply-chain costs $4M.
- Rolled out automated data-quality validation and monitoring across ETL workflows, halving production pipeline failures and improving reliability.
- Managed an Azure Data Lake (ADLS Gen2) architecture storing terabytes of distributed data, ensuring high availability and scalable ingestion.
## Projects
### Image Search Engine |
- Built end-to-end image search system on 10K images using clustering + LSH vector indexing, reducing nearest-neighbor retrieval time from 1 hour to 30 seconds.
### Elastic AWS Cloud Application for Face Recognition |
- Architected auto-scaling AWS (EC2, ELB, SQS, S3) Flask-based REST system handling 1,000 concurrent requests, enabling 30-second elastic shutdown and improved cost-efficient scaling.
### AdPrompter: Generative AI for Ads |
- Built the backend and rating components of an RL pipeline generating 50+ multimodal ad variants/product, improving Click Through Rate 25% with bias detection and text-to-video extensibility.
## Education
### Master of Science in Computer Science Arizona State University, Tempe, AZ, USA
05/2025 · GPA: 3.9/4
Coursework: Statistical Machine Learning, Cloud Computing, Data Mining, NLP, Multimedia & Web databases
### Bachelor of Technology in Computer Science & Engineering University Institute of Technology RGPV, India
06/2021 · GPA: 8.4/10
## Technical Skills
Languages: Python, SQL, Kotlin, Java
ML: PyTorch, TensorFlow, scikit-learn, XGBoost, Koog, Model Training, Model Evaluation
Data: Spark, PySpark, Airflow, Kafka, Databricks, ADLS, Pandas, NumPy
Systems: Distributed Systems, Docker