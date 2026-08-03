Devanshu Gupta
dgupta77@asu.edu |
623-290-3858 | linkedin.com/in/devanshu0gupta
| github.com/devanshugupta
## Summary
ML Engineer at Amazon Prime Video training, fine-tuning, and evaluating production LLM and retrieval models serving 1M+ users, with first-author EMNLP 2025 research on table reasoning over unstructured data.
## Research Publications
Weaver: Interweaving SQL and LLM for Table Reasoning [EMNLP 2025 - First Author]
TraceBack: Multi-Agent Decomposition for Fine-Grained Table Attribution [TACL 2026, under review]
## Work Experience
### Amazon, Prime Video | Machine Learning Engineer (06/2025 -- Present)
- Trained a LoRA fine-tuned routing model for hybrid retrieval serving production traffic, improving relevance 5% and cutting latency 50%, adopted for production after winning an internal hackathon.
- Developed a multi-turn LLM evaluation framework processing 50K+ conversations daily with LLM-as-judge and automated fact validation, increasing defect discovery 60%.
- Diagnosed false title-unavailability via an 11-experiment ablation study, fixing web-search poisoning of model reasoning and cutting the error rate from 75% to zero.
- Deployed semantic query-to-title retrieval with multilingual E5 embeddings on SageMaker and ANN search over a FAISS index, feature-flagged with a 750ms timeout for zero live-turn degradation.
- Instituted PromptFoo LLM regression testing with a retry methodology that eliminated flaky tests, now run team-wide on every pipeline change before production.
### Tata Consultancy Services | Software Engineer (08/2021 -- 08/2023)
- Built scalable demand forecasting pipeline using Spark in Databricks and XGBoost, cutting supply chain costs by $4M.
- Designed distributed data pipelines on Airflow integrating 4+ data sources into unified storage, improving data consistency.
- Maintained Azure Data Lake Storage (ADLS Gen2) architecture storing terabytes of distributed data, ensuring high availability and scalable ingestion.
## Projects
### AdPrompter: Generative AI for Ads |
- Built the backend and rating components of an RL pipeline generating 50+ multimodal ad variants/product, improving Click Through Rate 25% with bias detection and text-to-video extensibility.
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
ML: PyTorch, TensorFlow, scikit-learn, Koog, LoRA fine-tuning, computer vision
LLM: RAG, evals, LLM-as-judge, prompt engineering
Retrieval: FAISS, embeddings, vector search
Cloud: AWS, SageMaker, Docker