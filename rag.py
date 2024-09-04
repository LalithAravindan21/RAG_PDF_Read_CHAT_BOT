# -*- coding: utf-8 -*-
"""rag_bot.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1m0YztOTy-NnfL4zH8m8TK8lx6ts8c6BA
"""

import os
import torch
import tensorflow as tf
from auto_gptq import AutoGPTQForCausalLM
from langchain import HuggingFacePipeline, PromptTemplate
from langchain.chains import RetrievalQA
from langchain.document_loaders import PyPDFDirectoryLoader
from langchain.embeddings import HuggingFaceInstructEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.vectorstores import Chroma
from pdf2image import convert_from_path
from transformers import AutoTokenizer, TextStreamer, pipeline

# Check if GPU is available
DEVICE = "cuda:0" if tf.config.list_physical_devices("GPU") else "cpu"

# Ensure directory for PDFs
if not os.path.exists("pdfs"):
    os.makedirs("pdfs")

# Load PDF files (Replace the URLs with actual PDF file paths on Azure VM)
pdf_files = ["tesla-earnings-report.pdf", "nvidia-earnings-report.pdf", "meta-earnings-report.pdf"]

# Convert PDFs to images (For visualization, optional)
meta_images = convert_from_path("pdfs/meta-earnings-report.pdf", dpi=88)
nvidia_images = convert_from_path("pdfs/nvidia-earnings-report.pdf", dpi=88)
tesla_images = convert_from_path("pdfs/tesla-earnings-report.pdf", dpi=88)

# Load documents
loader = PyPDFDirectoryLoader("pdfs")
docs = loader.load()

# Embeddings
embeddings = HuggingFaceInstructEmbeddings(
    model_name="hkunlp/instructor-large", model_kwargs={"device": DEVICE}
)

# Text splitting
text_splitter = RecursiveCharacterTextSplitter(chunk_size=1024, chunk_overlap=64)
texts = text_splitter.split_documents(docs)

# Chroma vector store (if using persistent storage)
# db = Chroma.from_documents(texts, embeddings, persist_directory="db")

# Load GPTQ model
model_name_or_path = "TheBloke/Llama-2-13B-chat-GPTQ"
model_basename = "model"
tokenizer = AutoTokenizer.from_pretrained(model_name_or_path, use_fast=True)

model = AutoGPTQForCausalLM.from_quantized(
    model_name_or_path,
    revision="gptq-4bit-128g-actorder_True",
    model_basename=model_basename,
    use_safetensors=True,
    trust_remote_code=True,
    inject_fused_attention=False,
    device=DEVICE,
    quantize_config=None,
)

# Set up text generation pipeline
streamer = TextStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True)
text_pipeline = pipeline(
    "text-generation",
    model=model,
    tokenizer=tokenizer,
    max_new_tokens=1024,
    temperature=0,
    top_p=0.95,
    repetition_penalty=1.15,
    streamer=streamer,
)

# LLM pipeline
llm = HuggingFacePipeline(pipeline=text_pipeline, model_kwargs={"temperature": 0})

# System prompt for the QA chain
DEFAULT_SYSTEM_PROMPT = """
You are a helpful, respectful and honest assistant. Always answer as helpfully as possible, while being safe. Your answers should not include any harmful, unethical, racist, sexist, toxic, dangerous, or illegal content. Please ensure that your responses are socially unbiased and positive in nature.
"""

def generate_prompt(prompt: str, system_prompt: str = DEFAULT_SYSTEM_PROMPT) -> str:
    return f"""
[INST] <>
{system_prompt}
<>

{prompt} [/INST]
""".strip()

SYSTEM_PROMPT = "Use the following pieces of context to answer the question at the end. If you don't know the answer, just say that you don't know, don't try to make up an answer."

template = generate_prompt(
    """
{context}

Question: {question}
""",
    system_prompt=SYSTEM_PROMPT,
)

prompt = PromptTemplate(template=template, input_variables=["context", "question"])

qa_chain = RetrievalQA.from_chain_type(
    llm=llm,
    chain_type="stuff",
    retriever=db.as_retriever(search_kwargs={"k": 2}),
    return_source_documents=True,
    chain_type_kwargs={"prompt": prompt},
)

# Example query
result = qa_chain("What is the per share revenue for Meta during 2023?")
print(result["source_documents"][0].page_content)