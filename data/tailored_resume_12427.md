Devanshu Gupta
dgupta77@asu.edu |
623-290-3858 | linkedin.com/in/devanshu0gupta
| github.com/devanshugupta
## Summary
ML engineer at Amazon Prime Video training, evaluating, and deploying production models: retrieval and ranking at 1M+ users, LLM-as-judge evaluation, and A/B-driven model iteration.
## Research Publications
Weaver: Interweaving SQL and LLM for Table Reasoning [EMNLP 2025 - First Author]
TraceBack: Multi-Agent Decomposition for Fine-Grained Table Attribution [TACL 2026, under review]
## Work Experience
### Amazon, Prime Video | Machine Learning Engineer (06/2025 -- Present)
- Shipped embedding-based retrieval and ranking models (FAISS, KNN, NDCG) for recommendations serving 1M users at 0.5s latency, improving CTR 16% via offline and online evaluation.
- Trained a LoRA fine-tuned model as a production query router, improving relevance 5% and cutting latency 50%; won the internal hackathon and was adopted for production.
- Developed a multi-turn evaluation framework processing 50K+ conversations/day with automated model-quality validation, increasing defect discovery 60%.
- Launched semantic retrieval with multilingual E5 embeddings on a SageMaker endpoint, feature-flagged with a 750ms timeout and fail-open for zero live-turn degradation.
- Rolled out feature gating and A/B experimentation for controlled model rollouts and repeatable experiments across 10+ production ML features.
### Tata Consultancy Services | Software Engineer (08/2021 -- 08/2023)
- Built scalable demand forecasting pipeline using Spark in Databricks and XGBoost, cutting supply chain costs by $4M.
- Maintained Azure Data Lake Storage (ADLS Gen2) architecture storing terabytes of distributed data, ensuring high availability and scalable ingestion.
- Created Tableau dashboards on user-behavior metrics, surfacing actionable insights that informed product decisions.
## Projects
### AdPrompter: Generative AI for Ads |
- Built the backend and rating components of an RL pipeline generating 50+ multimodal ad variants/product, improving Click Through Rate 25% with bias detection and text-to-video extensibility.
### Elastic AWS Cloud Application for Face Recognition |
- Architected auto-scaling AWS (EC2, ELB, SQS, S3) Flask-based REST system handling 1,000 concurrent requests, enabling 30-second elastic shutdown and improved cost-efficient scaling.
### Hybrid Music Recommender |
- Built a content-based recommender over 10K songs using 30 audio and metadata features (MFCC, spectral, tempo) with collaborative-filtering signals, a MySQL history store, and cold-start handling for new tracks.
## Education
### Master of Science in Computer Science Arizona State University, Tempe, AZ, USA
05/2025 · GPA: 3.9/4
Coursework: Statistical Machine Learning, Cloud Computing, Data Mining, NLP, Multimedia & Web databases
### Bachelor of Technology in Computer Science & Engineering University Institute of Technology RGPV, India
06/2021 · GPA: 8.4/10
## Technical Skills
Languages: Python, SQL, Kotlin
ML: PyTorch, TensorFlow, scikit-learn, Koog, XGBoost, Fine-tuning (LoRA/PEFT), Model Evaluation (NDCG, LLM-as-judge)
Retrieval: FAISS, OpenSearch, Vector Search, RAG
Serving: SageMaker, AWS, A/B Testing