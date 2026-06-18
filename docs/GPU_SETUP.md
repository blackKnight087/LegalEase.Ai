# GPU setup (NVIDIA RTX 4050, 6 GB VRAM)

LegalEase can offload speech-to-text (Whisper) and optionally OCR to your GPU while keeping KB embeddings on CPU to save VRAM for Ollama chat.

## 1. Install CUDA PyTorch (Windows)

CPU-only `torch` from `pip install -r requirements.txt` does not use your GPU. For RTX 4050:

```powershell
py -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
py -m pip install faster-whisper
```

Verify:

```powershell
py -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

Expected: `True NVIDIA GeForce RTX 4050 Laptop GPU`

## 2. Ollama on GPU (chat)

**Automatic (recommended):** `.\run_backend.ps1` starts Ollama on GPU when it is not already running (`OLLAMA_AUTO_START=1`, `OLLAMA_NUM_GPU=999` in `.env`).

Manual only if you disabled auto-start:

```powershell
$env:OLLAMA_NUM_GPU=999
ollama serve
```

If you use the **Ollama tray app**, quit it once and let the backend auto-start Ollama with GPU — otherwise the tray instance may keep using RAM instead of VRAM.

Use a **quantized** model (Q4) so 8B fits in ~4 GB VRAM alongside Whisper.

## 3. `.env` profile (6 GB VRAM)

**GPU-only Legal stack (recommended for KB + coach):**

```env
LEGALEEASE_GPU_ONLY=1
GPU_PROFILE=legal_gpu
OLLAMA_NUM_GPU=999
OLLAMA_AUTO_START=1
NEURAL_FINETUNE_DEVICE=cuda
RAG_EMBEDDING_DEVICE=cpu
STT_DEVICE=cpu
```

| Component | Device | Notes |
|-----------|--------|--------|
| KB answers (`legalease-tuned`) | **GPU VRAM** | Auto-starts with `run_backend.ps1` |
| Gemini coach / retrieval hints | **Google cloud** | Not on your GPU — API only |
| Neural embedding training | **GPU** | Pauses Ollama VRAM briefly while training |
| KB search embeddings | **CPU** | Frees VRAM for the 8B chat model |

| Profile | Embeddings | STT | Ollama |
|---------|------------|-----|--------|
| `legal_gpu` | CPU | CPU | GPU (all layers) |
| `balanced` | CPU | CUDA | GPU (`OLLAMA_NUM_GPU`) |
| `max_stt` | CPU | CUDA | CPU layers |
| `max_chat` | CPU | CPU | GPU |

## 4. Check from API

After login: `GET /api/v1/health/gpu` — shows `cuda_available`, VRAM, `stt_device`, `embeddings_device`.

## 5. ffmpeg

```powershell
winget install Gyan.FFmpeg
```

Required for browser webm mic recordings.

## 6. VRAM budget

Do not enable GPU for embeddings + large Ollama + Whisper + OCR at once on 6 GB. Priority: **Ollama > STT > OCR > embedding GPU**.
