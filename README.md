# 🧾 ReceiptPocket

### Your expenses, privately managed.

**ReceiptPocket is a local-first, AI-powered receipt and expense manager built with Python.** It uses local OCR and an open-weight language model to extract information from receipt images, helping freelancers and small business owners organize expenses without sending their receipts to a cloud AI service.

Upload a receipt, review the extracted details, save the expense locally, and keep track of your spending from one dashboard.

> Built for the [Hacktoberfest Open-Source AI Challenge — Week 2: Side Hustle](https://dev.to/challenges/hacktoberfest-week2-2026-10-12).

---

## ✨ Features

- **Local AI receipt extraction** — Uses Tesseract OCR and Qwen2.5 through Ollama to extract merchant names, transaction dates, amounts, and expense categories from receipt images.
- **Privacy-first storage** — Stores expense records and receipt images on your computer using SQLite and local files.
- **Editable extraction results** — Review and correct AI-extracted details before saving an expense.
- **Manual expense entry** — Add expenses manually when a receipt is unavailable or automatic extraction fails.
- **Expense dashboard** — View spending summaries, recent expenses, and category breakdowns.
- **Expense history** — Search, filter, and inspect saved expenses and their associated receipt images.
- **Multi-currency support** — Configure a home currency, retain original receipt amounts, and convert supported foreign-currency expenses using recorded exchange-rate information.
- **CSV export** — Export expense records for further analysis in spreadsheet applications.
- **Local-first architecture** — Core OCR, AI inference, and expense storage run on your computer.

## 🔒 Privacy by design

Your receipts can contain sensitive personal and financial information. ReceiptPocket is designed to keep that information under your control.

| Component | How it works |
|---|---|
| OCR | Tesseract processes receipt images locally. |
| AI extraction | Qwen2.5 runs locally through Ollama. |
| Expense storage | SQLite stores records on your computer. |
| Receipt images | Saved in the local project data directory. |
| Currency conversion | Uses exchange-rate reference data when needed. |

Receipt images, OCR text, and expense records are not sent to a hosted AI service by the receipt-processing workflow.

**A note about internet access:** You need an internet connection to install dependencies and download the AI model. Refreshing an exchange rate may also require internet access. ReceiptPocket can use locally available exchange rates or manual rates where supported. When requesting an exchange rate, the app needs the currency pair and relevant date; it does not need to upload your receipt or merchant information to the rate provider.

For privacy, the local database, receipt files, virtual environment, and development backups are excluded from Git.

## 🛠️ Technology stack

| Technology | Purpose |
|---|---|
| Python | Application logic |
| Streamlit | User interface and dashboard |
| Tesseract OCR | Local text extraction from receipt images |
| Ollama | Local model runtime |
| Qwen2.5 1.5B Instruct | Open-weight language model for structured extraction |
| SQLite | Local expense database |
| Pillow | Image handling |
| Babel | Currency and locale-aware number formatting |
| Frankfurter API | Exchange-rate reference data |

## 🚀 Getting started

These instructions are for Windows and PowerShell.

### 1. Prerequisites

Install the following:

- **Python:** [Download Python](https://www.python.org/downloads/)
- **Ollama:** [Download Ollama for Windows](https://ollama.com/download/windows)
- **Tesseract OCR:** [Windows installation instructions](https://github.com/UB-Mannheim/tesseract/wiki)
- **Git:** [Download Git](https://git-scm.com/downloads)

After installing Tesseract, make sure its executable is accessible. A common installation path is:

`C:\Program Files\Tesseract-OCR\tesseract.exe`

ReceiptPocket can be configured to use this path directly if Tesseract is not available through `PATH`.

### 2. Clone the repository

Replace `YOUR_USERNAME` with your GitHub username.

```powershell
git clone https://github.com/YOUR_USERNAME/ReceiptPocket.git
cd ReceiptPocket
```

### 3. Create a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks virtual-environment activation, you can use the environment's Python executable directly in the following commands.

### 4. Install Python dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 5. Download the AI model

Ensure Ollama is installed and running. Then open a PowerShell terminal and run:

```powershell
ollama pull qwen2.5:1.5b-instruct
```

This downloads the model locally. The first download requires an internet connection and sufficient storage space.

Verify the model is available:

```powershell
ollama list
```

If Ollama is not running, launch it through the Windows application. Alternatively, run `ollama serve` in a separate terminal if needed.

### 6. Verify Tesseract

Open a new PowerShell terminal and run:

```powershell
tesseract --version
```

If the command is not recognized, either add the installation directory to your Windows `PATH` or configure the application to use the full executable path.

### 7. Run ReceiptPocket

From the project directory:

```powershell
.\.venv\Scripts\streamlit.exe run app.py --server.address 127.0.0.1
```

Open the local URL displayed by Streamlit, normally:

`http://127.0.0.1:8501`

Keep Ollama running while using AI extraction.

## 📖 How to use it

1. **Open Overview** to view your expense summaries and recent activity.
2. **Upload a receipt** in JPG, JPEG, or PNG format.
3. **Extract details** using local OCR and AI.
4. **Review the results** and correct the merchant, date, amount, category, or currency when necessary.
5. **Save the expense** to your local SQLite database.
6. **View Expenses** to search, filter, and inspect saved records.
7. **Export Data** to download expenses as a CSV file.

You can also enter expenses manually if OCR or AI extraction is unavailable.

### Working with multiple currencies

ReceiptPocket distinguishes the original receipt amount from the converted amount used for reporting.

Before saving a foreign-currency expense, check the detected currency and review the proposed conversion. Exchange-rate reference values can vary from the rate actually charged by a bank or card provider.

If a currency is ambiguous, a required rate is unavailable, or a record's original currency is unknown, verify the information rather than assuming a currency or inventing a conversion. Historical expenses created before currency tracking was introduced may require classification before they can be included in home-currency totals.

## 🗂️ Project structure

```text
ReceiptPocket/
├── .streamlit/
│   └── config.toml
├── app.py
├── requirements.txt
├── README.md
├── LICENSE
├── .gitignore
└── data/                 # Created locally; ignored by Git
    ├── receiptpocket.db
    └── receipts/
```

The `data/` directory is generated locally when the application initializes. Your actual database, receipt images, and backups should remain on your computer and must not be committed to the repository.

## 🧪 Testing

The project has test scripts covering expense persistence, application features, currency behavior, and the receipt-processing pipeline.

Run the test scripts from your project directory using your virtual environment:

```powershell
.\.venv\Scripts\python.exe -m py_compile app.py
```

If you have the corresponding test files in your local development workspace, run them individually as well:

```powershell
.\.venv\Scripts\python.exe path\to\test_multi_currency.py
.\.venv\Scripts\python.exe path\to\test_receiptpocket.py
.\.venv\Scripts\python.exe path\to\test_features.py
.\.venv\Scripts\python.exe path\to\test_pipeline.py
```

Replace the placeholder paths with the actual locations of your test files. The tests may require Tesseract and Ollama to be installed and running for integration checks.

## 🔐 Data and backups

ReceiptPocket stores expense information locally. The default project database is:

`data/receiptpocket.db`

Back up the database and its associated receipt images before performing migrations, changing the application schema, or moving the project to another computer.

The Git ignore rules exclude local data and development files. **Before contributing or pushing changes, verify that databases, receipt images, credentials, and private backups are not staged or tracked.**

## 🛣️ Future improvements

Possible areas for future development include:

- Desktop packaging for easier installation.
- More flexible receipt layouts and improved extraction accuracy.
- Better duplicate-receipt detection.
- Additional expense reporting and export options.
- Simpler backup and restore workflows.
- Further improvements to multi-currency handling and offline operation.

## 🤝 Contributing

Contributions, bug reports, and suggestions are welcome.

1. Fork the repository.
2. Create a branch for your change.
3. Test your changes locally.
4. Open a pull request describing the problem and solution.

Please do not include real receipts, expense databases, private financial information, or credentials in issues and pull requests.

## 📄 License

ReceiptPocket is distributed under the MIT License. See [LICENSE](LICENSE) for details.

## 💡 Why open-source AI?

ReceiptPocket explores how open-weight AI can help people automate everyday tasks without making cloud AI services a mandatory part of the workflow.

Running OCR and AI inference locally can reduce exposure of sensitive receipt information, avoid per-request charges from a hosted AI inference provider, and give users more control over their software and data.

The objective is simple: make expense organization easier while keeping the core receipt-processing workflow on the user's own device.

---

**Built with Python, Streamlit, Tesseract OCR, Ollama, Qwen2.5, and SQLite.**

#devchallenge #hf26challenge
