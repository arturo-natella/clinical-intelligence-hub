import os
import json
from pathlib import Path
import logging

try:
    import chromadb
    from chromadb.utils import embedding_functions
except ImportError:
    logging.warning("ChromaDB not installed yet. Skipping RAG setup for now.")

class RAGEngine:
    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.db_dir = self.data_dir / "chroma_db"
        self.db_dir.mkdir(exist_ok=True)
        
        try:
            # Persistent local vector database
            self.chroma_client = chromadb.PersistentClient(path=str(self.db_dir))
            
            # Using standard all-MiniLM-L6-v2 for fast local embeddings
            self.embed_fn = embedding_functions.DefaultEmbeddingFunction()
            
            self.collection = self.chroma_client.get_or_create_collection(
                name="patient_records", 
                embedding_function=self.embed_fn
            )
            self._is_ready = True
        except Exception as e:
            logging.error(f"Failed to initialize ChromaDB: {str(e)}")
            self._is_ready = False

    def embed_profile(self, profile_data: dict):
        """Builds vector embeddings for every item in the clinical timeline."""
        if not self._is_ready: return
        
        docs = []
        ids = []
        metadatas = []
        
        # Embed Medications
        for idx, med in enumerate(profile_data.get('clinical_timeline', {}).get('medications', [])):
            if isinstance(med, dict):
                docs.append(f"Medication: {med.get('name', '')} {med.get('dosage', '')}")
                ids.append(f"med_{idx}")
                metadatas.append({"type": "medication", "status": med.get('status', '')})
                
        # Embed Labs
        for idx, lab in enumerate(profile_data.get('clinical_timeline', {}).get('labs', [])):
            if isinstance(lab, dict):
                docs.append(f"Lab Result: {lab.get('name', '')} was {lab.get('value', '')} {lab.get('unit', '')} on {lab.get('date', '')}")
                ids.append(f"lab_{idx}")
                metadatas.append({"type": "lab_result"})

        # Embed Symptoms & Diary Logs
        for idx, symp in enumerate(profile_data.get('clinical_timeline', {}).get('symptoms_and_diary', [])):
            if isinstance(symp, dict):
                docs.append(f"Note/Symptom: {symp.get('description', '')} on {symp.get('date', '')}")
                ids.append(f"symp_{idx}")
                metadatas.append({"type": "clinical_note"})
                
        if docs:
            # Upsert handles inserting new or updating existing
            self.collection.upsert(
                documents=docs,
                metadatas=metadatas,
                ids=ids
            )
            logging.info(f"Embedded {len(docs)} clinical records into local vector space.")

    def query(self, question: str, n_results: int = 5) -> str:
        """Retrieves the most semantically relevant records to the user's question."""
        if not self._is_ready: 
            return "Local database offline."
            
        results = self.collection.query(
            query_texts=[question],
            n_results=n_results
        )
        
        if not results['documents'] or not results['documents'][0]:
            return "No relevant records found."
            
        context = "Relevant Patient Records Found:\n"
        for doc in results['documents'][0]:
            context += f"- {doc}\n"
            
        return context
