import base64
import json
import os
import sys
import requests
from pathlib import Path
from typing import Optional, List, Tuple

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    env_file = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip("'\""))

DEFAULT_OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
DEFAULT_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2-vision")
DEFAULT_STYLE = os.getenv("CAPTION_STYLE", "engaging")
ADD_HASHTAGS = os.getenv("ADD_HASHTAGS", "true").lower() in ("true", "1", "yes")
MAX_HASHTAGS = int(os.getenv("MAX_HASHTAGS", "15"))

KNOWN_VISION_MODELS = [
    "llama3.2-vision",
    "llava",
    "minicpm-v",
    "qwen2.5-vl",
    "bakllava",
    "moondream",
]


def encode_image_to_base64(image_path: str) -> str:
    """Read an image file and encode it as a base64 string."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def get_ollama_models(host: str) -> List[str]:
    """Fetch list of installed models from Ollama."""
    try:
        res = requests.get(f"{host}/api/tags", timeout=3)
        if res.status_code == 200:
            return [m.get("name", "") for m in res.json().get("models", [])]
    except Exception:
        pass
    return []


def select_best_model(available_models: List[str], requested_model: str) -> Tuple[Optional[str], bool]:
    """
    Select best model to use from available models.
    Returns: (selected_model_name, is_vision_model)
    """
    # 1. Exact or prefix match for requested model
    for m in available_models:
        if requested_model == m or m.startswith(f"{requested_model}:"):
            # Check if it's a known vision model
            is_vis = any(vm in m.lower() for vm in KNOWN_VISION_MODELS) or "vision" in m.lower()
            return m, is_vis

    # 2. Check if any other vision model is available
    for vm in KNOWN_VISION_MODELS:
        for m in available_models:
            if vm in m.lower() or "vision" in m.lower():
                return m, True

    # 3. Fall back to installed text model
    preferred_text = ["llama3.1", "llama3", "qwen3", "gemma", "mistral"]
    for pref in preferred_text:
        for m in available_models:
            if pref in m.lower():
                return m, False

    # 4. If any model is available, use the first one
    if available_models:
        return available_models[0], False

    return None, False


def build_system_prompt(style: str) -> str:
    """Create a tailored system prompt based on desired caption style."""
    base_guidelines = (
        "You are an expert Instagram social media manager and content creator for @poetghazipur61. "
        "Create a thoughtful, emotional, and captivating Instagram post combining Hindi/Urdu shayari "
        "and English reflections. "
        "Format requirements:\n"
        "1. Hook: Start with a punchy, scroll-stopping line or couplet.\n"
        "2. Story/Poetry: 2-4 lines of expressive poetry or shayari capturing emotions, depth, and beauty.\n"
        "3. Call-To-Action (CTA): A conversational question encouraging comments or shares.\n"
        "4. Use tasteful, relevant emojis naturally throughout.\n"
    )

    if style == "aesthetic":
        tone = "Tone: Dreamy, artistic, poetic, understated."
    elif style == "witty":
        tone = "Tone: Playful, clever, humorous, lighthearted."
    elif style == "minimalist":
        tone = "Tone: Concise, elegant, 1-2 powerful sentences max."
    elif style == "informative":
        tone = "Tone: Educational, curious, insightful, detail-oriented."
    else:
        tone = "Tone: Deep, emotional, soulful, and poetic."

    hashtag_rule = (
        f"At the very end, include {MAX_HASHTAGS} highly relevant, trending hashtags on a new line "
        f"(including #poetghazipur61 #shayari #poetry #feelings)."
        if ADD_HASHTAGS
        else "Do not include hashtags."
    )

    return f"{base_guidelines}\n{tone}\n{hashtag_rule}\nOutput ONLY the final caption text without meta commentary."


def get_preset_caption(image_path: str) -> str:
    """Return a high quality aesthetic fallback caption."""
    stem = Path(image_path).stem.replace("_", " ").title()
    return (
        f"✨ {stem} — A moment of silence, thought, and inspiration.\n\n"
        f"हर तस्वीर एक कहानी कहती है, कुछ अनकहे जज़्बात बयां करती है। ✍️☕\n\n"
        f"What story does this picture whisper to you today?\n\n"
        f"#poetghazipur61 #poetry #words #reflections #aesthetic #thoughts "
        f"#shayari #inspiration #morningthoughts #visualstories #creativemind"
    )


def generate_caption(
    image_path: str,
    model: Optional[str] = None,
    style: Optional[str] = None,
    host: Optional[str] = None,
) -> str:
    """
    Generate an Instagram caption and hashtags for the given image using Ollama.
    Falls back gracefully if the requested vision model is not installed.
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found at path: {image_path}")

    target_host = (host or DEFAULT_OLLAMA_HOST).rstrip("/")
    target_model = model or DEFAULT_OLLAMA_MODEL
    target_style = style or DEFAULT_STYLE

    # Check available models in Ollama
    available_models = get_ollama_models(target_host)
    if not available_models:
        print(f"  ℹ️ Ollama is offline or has no models at {target_host}. Using creative preset caption.")
        return get_preset_caption(image_path)

    chosen_model, is_vision = select_best_model(available_models, target_model)
    if not chosen_model:
        return get_preset_caption(image_path)

    prompt = build_system_prompt(target_style)
    stem_title = Path(image_path).stem.replace("_", " ").title()

    try:
        if is_vision:
            print(f"  🧠 Using Ollama vision model: {chosen_model}")
            image_base64 = encode_image_to_base64(image_path)
            payload = {
                "model": chosen_model,
                "prompt": (
                    "Analyze this image and write an Instagram caption following the specified format:\n"
                    f"{prompt}"
                ),
                "images": [image_base64],
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "top_p": 0.9,
                },
            }
        else:
            print(f"  ℹ️ Model '{target_model}' not installed; generating caption with installed AI model '{chosen_model}'...")
            payload = {
                "model": chosen_model,
                "prompt": (
                    f"Write a poetic Instagram caption for a photo titled '{stem_title}'.\n"
                    f"{prompt}"
                ),
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "top_p": 0.9,
                },
            }

        response = requests.post(
            f"{target_host}/api/generate",
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=120,
        )

        if response.status_code == 200:
            result_json = response.json()
            caption = result_json.get("response", "").strip()
            if caption:
                return caption

        print(f"  ⚠️ Ollama returned status {response.status_code}. Using preset caption fallback.")
    except Exception as e:
        print(f"  ⚠️ Ollama error ({e}). Using preset caption fallback.")

    return get_preset_caption(image_path)


if __name__ == "__main__":
    target = None
    if len(sys.argv) > 1:
        target = Path(sys.argv[1])
    else:
        target = Path(__file__).resolve().parent / "images"

    if target.is_dir():
        exts = {".jpg", ".jpeg", ".png", ".webp"}
        imgs = [f for f in sorted(target.iterdir()) if f.is_file() and f.suffix.lower() in exts]
        if not imgs:
            print(f"No image files (.jpg, .png) found in folder: {target}")
            sys.exit(1)
        target = imgs[0]

    print(f"Generating caption for: {target.name}")
    try:
        caption = generate_caption(str(target))
        print("\n--- [Generated Caption] ---")
        print(caption)
        print("---------------------------\n")
    except Exception as err:
        print(f"Error: {err}")
