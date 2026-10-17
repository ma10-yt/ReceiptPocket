# ReceiptPocket

A local-first AI receipt organizer for freelancers and small business owners.

## Features

- Upload receipt images (JPG, JPEG, PNG)
- Extract text using local Tesseract OCR
- Use AI (Ollama with qwen2.5:1.5b-instruct) to extract structured data:
  - Merchant name
  - Transaction date
  - Total amount
  - Expense category
- Review and edit extracted information before saving
- Store expenses locally in SQLite database
- Save receipt images locally
- View expenses with filtering and search
- Monthly totals and category summaries
- Export expenses as CSV
- Fully offline capable after initial setup
- Privacy-focused: all processing happens locally

## Privacy & Data Handling

- All OCR, AI inference, and database operations run locally on your machine
- Communicates only with Ollama running on localhost (127.0.0.1:11434)
- No external APIs, cloud services, or account requirements
- No usage tracking or telemetry
- Data stored in `data/receiptpocket.db` and images in `data/receipts/`
- Initial setup requires internet to install dependencies and download the Ollama model
- After setup, the application works completely offline

## Installation & Setup

### Prerequisites

1. **Python 3.8+** installed
2. **Ollama** installed and running
3. **Tesseract OCR** installed

### Step-by-Step Setup (Windows PowerShell)

1. **Clone or create the project directory**
   ```powershell
   mkdir ReceiptPocket
   cd ReceiptPocket
   ```

2. **Create a virtual environment (recommended)**
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

3. **Install Python dependencies**
   ```powershell
   pip install -r requirements.txt
   ```

4. **Install Ollama**
   - Download from https://ollama.com/download
   - Install and start the Ollama service

5. **Pull the required AI model**
   ```powershell
   ollama pull qwen2.5:1.5b-instruct
   ```

6. **Install Tesseract OCR**
   - Download from https://github.com/UB-Mannheim/tesseract/wiki
   - Install and note the installation directory (e.g., `C:\Program Files\Tesseract-OCR`)
   - Add Tesseract to your PATH or set the environment variable:
     ```powershell
     $env:TESSERACT_CMD = "C:\Program Files\Tesseract-OCR\tesseract.exe"
     ```
     (Add this to your system PATH permanently for convenience)

7. **Run the application**
   ```powershell
   streamlit run app.py
   ```
   The app will open in your browser at http://127.0.0.1:8501

### Running Without Virtual Environment

If you prefer not to use a virtual environment:
```powershell
pip install -r requirements.txt
streamlit run app.py
```

## Project Structure

- `app.py`: Main Streamlit application
- `requirements.txt`: Python dependencies
- `README.md`: This file
- `.gitignore`: Files and directories to exclude from Git
- `.streamlit/config.toml`: Streamlit configuration (disables usage tracking, sets localhost binding)
- `data/`: Directory containing SQLite database and receipt images (created automatically)

## How It Works

1. **Upload**: Select a receipt image file
2. **OCR**: Text is extracted locally using Tesseract
3. **AI Processing**: The extracted text is sent to Ollama running locally to identify merchant, date, amount, and category
4. **Review**: You can verify and correct the extracted information
5. **Save**: Data is stored in the local SQLite database and the image is saved in the `data/receipts` folder
6. **View**: Browse, search, and filter your saved expenses
7. **Export**: Download your expense records as a CSV file

## Troubleshooting

- **Ollama connection errors**: Ensure Ollama is running (`ollama serve`) and the model is pulled
- **Tesseract not found**: Verify Tesseract is installed and in your PATH, or set `TESSERACT_CMD` environment variable
- **Missing dependencies**: Run `pip install -r requirements.txt` again
- **Database issues**: The `data` folder and database are created automatically on first run

## Notes

- The application creates a `data` folder in the same directory as `app.py`
- Receipt images are saved with unique filenames to avoid overwriting
- Amounts and dates are validated before saving
- If AI or OCR fails, you can still enter receipt details manually
- Never share your `data` folder as it contains sensitive financial information

## License

This project is for personal and business use. Feel free to modify and adapt it to your needs.

## Disclaimer

This software is provided "as is" without warranty of any kind. The developer is not liable for any damages arising from its use.