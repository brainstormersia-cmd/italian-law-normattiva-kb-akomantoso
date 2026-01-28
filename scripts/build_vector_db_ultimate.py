import os
# Thread control PRIMA degli import pesanti
os.environ["OMP_NUM_THREADS"] = "4"
os.environ["MKL_NUM_THREADS"] = "4"

import json
import gc
import shutil
from itertools import islice
import chromadb
from chromadb.utils import embedding_functions
from tqdm import tqdm
import torch

# ==================== CONFIGURAZIONE ====================
JSONL_PATH = "/app/conoscenza_pronta_v3_finale.jsonl"
DB_PATH_TEMP = "/tmp/chroma_db_internal"  # GPU-friendly path
DB_PATH_FINAL = "/app/chroma_db"
COLLECTION_NAME = "normattiva_laws"

BATCH_SIZE = 64  # Ottimizzato per GPU (riduci a 32 se OOM)
MODEL_NAME = "intfloat/multilingual-e5-base"

MIN_TEXT_LEN = 10
TRUNCATE_META_TEXT = 1500

# ⚠️ LIMITE TOKEN E5-base: 512 token ≈ 2048 caratteri
# Lasciamo margine per "passage: " prefix e context
TRUNCATE_EMBED_TEXT = 2000  # Ridotto da 6000 per rispettare token limit

# ==================== UTILITY FUNCTIONS ====================
def clear_memory():
    """Pulizia aggressiva GPU + RAM"""
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.synchronize()
    gc.collect()

def checkpoint_path():
    return os.path.join(DB_PATH_TEMP, "processing_checkpoint.txt")

def load_checkpoint():
    p = checkpoint_path()
    if os.path.exists(p):
        try:
            with open(p, "r") as f:
                return int(f.read().strip() or 0)
        except:
            return 0
    return 0

def save_checkpoint(last_line_no: int):
    os.makedirs(DB_PATH_TEMP, exist_ok=True)
    with open(checkpoint_path(), "w") as f:
        f.write(str(last_line_no))

def safe_upsert(collection, ids, docs, metas):
    """Upsert con fallback ricorsivo per isolare errori"""
    try:
        collection.upsert(ids=ids, documents=docs, metadatas=metas)
        return 0
    except Exception as e:
        if len(ids) == 1:
            print(f"\n⚠️  Skipped problematic doc: {ids[0][:50]}... (Error: {str(e)[:80]})")
            return 1
        
        # Divide et impera
        mid = len(ids) // 2
        skipped = safe_upsert(collection, ids[:mid], docs[:mid], metas[:mid])
        skipped += safe_upsert(collection, ids[mid:], docs[mid:], metas[mid:])
        return skipped

# ==================== MAIN PROCESS ====================
def main():
    print("\n" + "="*70)
    print("🚀 GPU-ACCELERATED VECTORIZATION PIPELINE")
    print("="*70)
    
    # Verifica GPU
    if not torch.cuda.is_available():
        print("❌ CUDA non disponibile! Fallback su CPU...")
        device = "cpu"
        batch_size = 32  # Riduci batch su CPU
    else:
        device = "cuda"
        batch_size = BATCH_SIZE
        gpu_name = torch.cuda.get_device_name(0)
        gpu_mem = torch.cuda.get_device_properties(0).total_memory / 1e9
        print(f"✅ GPU: {gpu_name} ({gpu_mem:.1f} GB)")
    
    print(f"📏 Token limit config: {TRUNCATE_EMBED_TEXT} chars (~{TRUNCATE_EMBED_TEXT//4} tokens)")
    print(f"📦 Batch Size: {batch_size}")
    
    # Setup ChromaDB su path temporaneo veloce
    os.makedirs(DB_PATH_TEMP, exist_ok=True)
    client = chromadb.PersistentClient(path=DB_PATH_TEMP)
    
    print(f"⚙️  Caricamento modello su {device.upper()}...")
    emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=MODEL_NAME,
        device=device
    )
    
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=emb_fn,
        metadata={"hnsw:space": "cosine"}
    )
    
    # Checkpoint recovery
    last_processed = load_checkpoint()
    
    # Conta totale righe
    print("📊 Analisi file...")
    with open(JSONL_PATH, "r", encoding="utf-8") as f:
        total_lines = sum(1 for _ in f)
    
    print(f"🔄 Ripresa da riga: {last_processed:,} / {total_lines:,}")
    print("-" * 70)
    
    # Statistiche
    stats = {
        "processed": 0,
        "skipped_short": 0,
        "skipped_json": 0,
        "skipped_upsert": 0,
        "truncated": 0
    }
    
    batch_ids, batch_docs, batch_metas = [], [], []
    
    with open(JSONL_PATH, "r", encoding="utf-8") as f:
        file_gen = islice(f, last_processed, None)
        
        with tqdm(
            total=total_lines,
            initial=last_processed,
            desc="🔥 GPU Processing" if device == "cuda" else "💻 CPU Processing",
            unit="docs",
            colour="green" if device == "cuda" else "blue",
            ncols=100
        ) as pbar:
            
            for line_no, line in enumerate(file_gen, start=last_processed + 1):
                try:
                    line = line.strip()
                    if not line:
                        stats["skipped_json"] += 1
                        pbar.update(1)
                        continue
                    
                    item = json.loads(line)
                    txt = (item.get("text") or "").strip()
                    
                    if len(txt) <= MIN_TEXT_LEN:
                        stats["skipped_short"] += 1
                        pbar.update(1)
                        continue
                    
                    # Preparazione testo per embedding
                    ctx = (item.get("context") or "").strip()
                    vector_text = f"passage: {ctx} {txt}".strip()
                    
                    # Truncate intelligente rispettando token limit
                    if len(vector_text) > TRUNCATE_EMBED_TEXT:
                        vector_text = vector_text[:TRUNCATE_EMBED_TEXT]
                        stats["truncated"] += 1
                    
                    # Metadata puliti
                    metadata = {
                        "source": str(item.get("source", ""))[:200],
                        "source_id": str(item.get("source_id", ""))[:100],
                        "url": str(item.get("url", ""))[:500],
                        "original_text": txt[:TRUNCATE_META_TEXT]
                    }
                    
                    _id = str(item.get("id") or f"line:{line_no}")
                    
                    batch_ids.append(_id)
                    batch_docs.append(vector_text)
                    batch_metas.append(metadata)
                    
                    # Upsert batch completo
                    if len(batch_ids) >= batch_size:
                        skipped = safe_upsert(collection, batch_ids, batch_docs, batch_metas)
                        stats["skipped_upsert"] += skipped
                        stats["processed"] += len(batch_ids) - skipped
                        
                        save_checkpoint(line_no)
                        clear_memory()
                        
                        batch_ids, batch_docs, batch_metas = [], [], []
                        
                        # Update progress bar stats
                        pbar.set_postfix({
                            "inserted": f"{stats['processed']:,}",
                            "skip": stats['skipped_upsert'],
                            "trunc": stats['truncated']
                        })
                    
                    pbar.update(1)
                    
                except json.JSONDecodeError:
                    stats["skipped_json"] += 1
                    pbar.update(1)
                except Exception as e:
                    stats["skipped_json"] += 1
                    pbar.update(1)
            
            # Ultimo batch residuo
            if batch_ids:
                skipped = safe_upsert(collection, batch_ids, batch_docs, batch_metas)
                stats["skipped_upsert"] += skipped
                stats["processed"] += len(batch_ids) - skipped
                save_checkpoint(total_lines)
    
    # ⚠️ CRITICO: Chiusura forzata client prima dello spostamento
    print("\n💾 Chiusura database e flush su disco...")
    del collection
    del client
    clear_memory()
    
    print("\n" + "="*70)
    print("✅ VECTORIZATION COMPLETATA!")
    print("="*70)
    print(f"📊 Documenti inseriti:     {stats['processed']:,}")
    print(f"📊 Testi troncati:         {stats['truncated']:,}")
    print(f"⚠️  Testi troppo corti:    {stats['skipped_short']:,}")
    print(f"⚠️  Errori JSON/parsing:   {stats['skipped_json']:,}")
    print(f"⚠️  Fallback upsert:       {stats['skipped_upsert']:,}")
    
    # Spostamento finale DB
    print(f"\n📂 Spostamento database da temp a destinazione finale...")
    try:
        if os.path.exists(DB_PATH_FINAL):
            print(f"   🗑️  Rimozione database esistente in {DB_PATH_FINAL}...")
            shutil.rmtree(DB_PATH_FINAL)
        
        print(f"   📦 Copia da {DB_PATH_TEMP} a {DB_PATH_FINAL}...")
        shutil.copytree(DB_PATH_TEMP, DB_PATH_FINAL)
        
        # Verifica dimensione finale
        total_size = sum(
            os.path.getsize(os.path.join(dirpath, filename))
            for dirpath, _, filenames in os.walk(DB_PATH_FINAL)
            for filename in filenames
        ) / (1024 * 1024)  # MB
        
        print(f"✅ Database pronto in: {DB_PATH_FINAL}")
        print(f"📏 Dimensione totale: {total_size:.1f} MB")
        
    except Exception as e:
        print(f"❌ ERRORE durante spostamento database: {e}")
        print(f"⚠️  Il database rimane disponibile in: {DB_PATH_TEMP}")
        raise
    
    print("="*70 + "\n")
    
    # Riconnessione per verifica finale
    print("🔍 Verifica finale database...")
    client_final = chromadb.PersistentClient(path=DB_PATH_FINAL)
    collection_final = client_final.get_collection(name=COLLECTION_NAME)
    final_count = collection_final.count()
    print(f"✅ Verifica: {final_count:,} documenti in collection finale")
    
    if final_count != stats['processed']:
        print(f"⚠️  WARNING: Mismatch count (inseriti: {stats['processed']:,}, finale: {final_count:,})")
    
    print("\n🎉 PROCESSO COMPLETATO CON SUCCESSO!\n")

if __name__ == "__main__":
    main()