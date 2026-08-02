Devanshu Gupta
dgupta77@asu.edu |
623-290-3858 | linkedin.com/in/devanshu0gupta
| github.com/devanshugupta
## Summary
Machine Learning Engineer at Amazon Prime Video building GenAI systems, RAG, LLM agents, retrieval, and evaluation for a conversational assistant serving 1M+ users. First-author EMNLP 2025 researcher.
## Research Publications
Weaver: Interweaving SQL and LLM for Table Reasoning [EMNLP 2025 - First Author]
TraceBack: Multi-Agent Decomposition for Fine-Grained Table Attribution [TACL 2026, under review]
## Work Experience
### Amazon, Prime Video | Machine Learning Engineer (06/2025 -- Present)
- Developed hybrid retrieval with an XGBoost router across parallel OpenSearch and catalog retrievers with multi-turn LLM reranking, improving relevance 5% and cutting latency 50%; adopted for production.
- Improved RAG grounding quality by redesigning web-source parsing with attribution gating and domain fallback, recovering 117 dropped results/day and eliminating blank source cards in production.
- Migrated the assistant backend to a new Amazon Bedrock model (Claude Sonnet) with reserved-throughput overrides and A/B-gated prompt regression testing, owning the production model lifecycle.
- Led a multi-turn LLM evaluation framework processing 50K+ conversations/day with LLM-as-judge and automated fact validation, increasing defect discovery 60%.
- Optimized query-time retrieval by moving candidate filtering ahead of metadata fetch and bounding the conversation cache to 5 turns, cutting cache payload 75% and memory 40% under peak traffic.
### Tata Consultancy Services | Software Engineer (08/2021 -- 08/2023)
- Built scalable demand forecasting pipeline using Spark in Databricks and XGBoost, cutting supply chain costs by $4M.
- Maintained Azure Data Lake Storage (ADLS Gen2) architecture storing terabytes of distributed data, ensuring high availability and scalable ingestion.
- Raised batch pipeline throughput 40% by optimizing the transformation, ingestion, and validation stages across production systems.
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
Languages: Python, SQL, Kotlin, C++, Java
ML: PyTorch, TensorFlow, scikit-learn, Koog, LoRA Fine-tuning, Model Evaluation
GenAI: RAG, LLM Agents, Reranking, Prompt Engineering, Bedrock, FAISS, Vector Search
Backend: REST, gRPC, Microservices