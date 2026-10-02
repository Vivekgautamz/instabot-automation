# 📸 Instagram Auto Poster (Ollama AI + Meta Graph API)

An automated Python pipeline that detects new images, analyzes them using local **Ollama Vision AI** (`llama3.2-vision` or `llava`), generates engaging captions with targeted hashtags, publishes them to **Instagram** using the official **Meta Graph API**, and archives processed files while preventing duplicates.

---

## ⚡ Workflow

```
📁 images/ (Drop .jpg/.png)
     ↓
🐍 Python detects image & computes SHA-256 hash (storage.py)
     ↓
🤖 Ollama Vision analyzes image content, style & mood (ai_caption.py)
     ↓
✍️ High-performing caption & trending hashtags generated
     ↓
📱 Meta Instagram Graph API creates media container & publishes (instagram.py)
     ↓
📁 Image moved to posted/ & recorded in SQLite (main.py)
```

---

## 📦 Project Structure

```
c:\vivek\instagram/
├── images/               # Drop new images to post here
├── posted/               # Automatically moved here after publishing
├── main.py               # Main CLI automation and runner
├── ai_caption.py         # Ollama vision integration (llama3.2-vision / llava)
├── instagram.py          # Meta Instagram Graph API client
├── storage.py            # SQLite database tracking to prevent duplicate posts
├── requirements.txt      # Python dependencies
├── .env.example          # Environment variable template
├── .gitignore            # Git ignore file
└── README.md             # Setup guide and instructions
```

---

## 🚀 Quick Start

### 1. Install Dependencies

In your terminal or PowerShell, run:

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```
*(On Windows PowerShell: `Copy-Item .env.example .env`)*

---

## 🤖 1. Ollama AI Setup

This project uses local AI for privacy and zero API costs.

1. **Install Ollama**: Download from [ollama.com](https://ollama.com) and install it.
2. **Download a Vision Model**:
   ```bash
   ollama pull llama3.2-vision
   ```
   *(Alternative lightweight model: `ollama pull llava`)*
3. **Verify Ollama is Running**:
   Open a browser to `http://localhost:11434` or run:
   ```bash
   python main.py --status
   ```

---

## 🔑 2. Meta & Instagram Setup (Step-by-Step)

The official Instagram Graph API requires an **Instagram Professional Account** (Creator or Business) linked to a **Facebook Page**.

### Step 2.1: Convert Instagram Account to Professional
1. Open Instagram on your phone → Go to **Profile** → **Settings and privacy**.
2. Tap **Account type and tools** → **Switch to professional account**.
3. Choose **Creator** or **Business** (free).

### Step 2.2: Link Instagram to a Facebook Page
1. Create a Facebook Page (if you don't already have one) at [facebook.com/pages/create](https://www.facebook.com/pages/create).
2. Go to your Page's **Settings** → **Linked Accounts** → **Instagram**.
3. Click **Connect Account** and log in to your Instagram account.

### Step 2.3: Create a Meta App
1. Go to the [Meta for Developers Portal](https://developers.facebook.com/).
2. Click **My Apps** → **Create App**.
3. Select **Other** as the use case → Next.
4. Select **Business** as the app type → Enter an app name → Click **Create app**.

### Step 2.4: Get Your Access Token & Instagram User ID
1. Open the [Graph API Explorer](https://developers.facebook.com/tools/explorer/).
2. In the top right, select your App.
3. In **User or Page**, select **Get User Access Token**.
4. In **Permissions**, add:
   - `instagram_basic`
   - `instagram_content_publish`
   - `pages_show_list`
   - `pages_read_engagement`
5. Click **Generate Access Token** and approve permissions.
6. Find your Instagram Account ID by querying:
   ```text
   GET me/accounts?fields=instagram_business_account{id,username}
   ```
   The `id` inside `instagram_business_account` is your `IG_USER_ID`.

### Step 2.5: Generate a Long-Lived Token (60 Days)
1. Open the [Meta Access Token Debugger](https://developers.facebook.com/tools/debug/accesstoken/).
2. Paste the short-lived token and click **Debug**.
3. Click **Extend Access Token** at the bottom to receive a 60-day token.
4. Copy `IG_USER_ID` and this token into your `.env` file:
   ```ini
   IG_USER_ID=17841400000000000
   IG_ACCESS_TOKEN=EAA...
   ```

---

## 🌐 3. Image URL Requirement

Meta's Graph API requires an image URL that is publicly accessible over HTTPS.

You have three easy options:

* **Option A: Temporary ngrok Tunnel (Recommended for Local Dev)**
  Expose your local `images/` directory:
  ```bash
  # In terminal 1:
  python -m http.server 8080 --directory images
  
  # In terminal 2:
  ngrok http 8080
  ```
  Copy the HTTPS ngrok forwarding URL (e.g., `https://xyz.ngrok-free.app`) and set:
  ```ini
  PUBLIC_BASE_URL=https://xyz.ngrok-free.app
  ```

* **Option B: Public Image URL Flag**
  Pass any public image URL directly:
  ```bash
  python main.py --image images/sample.jpg --url https://images.unsplash.com/...
  ```

* **Option C: Free Cloudinary or AWS S3 Bucket**
  Host your images on Cloudinary or S3 and point `PUBLIC_BASE_URL` to your bucket base URL.

---

## 💻 4. Running the Auto Poster

### Diagnostic Check
Check connectivity to Ollama and Instagram API:
```bash
python main.py --status
```

### Dry Run (Test AI Captions Without Posting)
Test image analysis and caption generation without sending to Instagram:
```bash
python main.py --dry-run
```

### Custom Tone / Style
Choose between `engaging`, `aesthetic`, `witty`, `minimalist`, or `informative`:
```bash
python main.py --dry-run --style aesthetic
```

### Post a Single Image
```bash
python main.py --image images/photo.jpg
```

### Automatic Folder Watcher (Daemon Mode)
Continuously watch `images/` every 60 seconds:
```bash
python main.py --watch --interval 60
```

### View Post History
```bash
python main.py --history
```

---

## 🛡️ Duplicate Prevention

Every image processed is hashed using **SHA-256** and recorded in `posts.db`. Even if you rename an image or re-add it to `images/`, the system recognizes it has already been published and will safely skip it.
